"""Tests for Supabase JWT verification with local JWKS fixtures.

These tests use locally generated RSA key pairs to test JWT validation
without requiring external network calls to Supabase.
"""

from __future__ import annotations

import os
import time
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import PublicFormat
from fastapi import HTTPException
from jwt import PyJWKClient

from heimdex_common.auth import RequestContext, _verify_supabase_jwt, verify_jwt
from heimdex_common.config import reset_config


@pytest.fixture
def rsa_keypair() -> tuple[Any, Any]:
    """Generate an RSA key pair for testing."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    return private_key, public_key


@pytest.fixture
def jwks_config(rsa_keypair: tuple[Any, Any]) -> Generator[dict[str, str], None, None]:
    """Configure environment for Supabase JWT testing with local JWKS."""
    private_key, public_key = rsa_keypair

    # Set environment variables for Supabase auth
    os.environ["AUTH_PROVIDER"] = "supabase"
    os.environ["HEIMDEX_ENV"] = "local"
    os.environ["SUPABASE_JWKS_URL"] = "https://test.supabase.co/auth/v1/jwks"
    os.environ["AUTH_ISSUER"] = "https://test.supabase.co/auth/v1"
    os.environ["AUTH_AUDIENCE"] = "heimdex"

    reset_config()

    # Serialize keys for JWT encoding
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=PublicFormat.SubjectPublicKeyInfo,
    )

    yield {
        "private_key": private_pem,
        "public_key": public_pem,
        "key_object": private_key,
    }

    # Cleanup
    for key in [
        "AUTH_PROVIDER",
        "HEIMDEX_ENV",
        "SUPABASE_JWKS_URL",
        "AUTH_ISSUER",
        "AUTH_AUDIENCE",
    ]:
        os.environ.pop(key, None)
    reset_config()


class TestSupabaseJWTVerification:
    """Test Supabase JWT verification with local JWKS mock."""

    def create_test_token(
        self,
        jwks_config: dict[str, str],
        user_id: str = "user-123",
        org_id: str = "550e8400-e29b-41d4-a716-446655440000",
        role: str | None = "user",
        exp_minutes: int = 60,
        iss: str | None = "https://test.supabase.co/auth/v1",
        aud: str | None = "heimdex",
        include_kid: bool = True,
    ) -> str:
        """Create a test JWT token signed with the test RSA key."""
        payload: dict[str, Any] = {
            "sub": user_id,
            "app_metadata": {"org_id": org_id},
            "iat": int(time.time()),
            "exp": int(time.time()) + (exp_minutes * 60),
        }

        if role:
            payload["role"] = role
        if iss:
            payload["iss"] = iss
        if aud:
            payload["aud"] = aud

        headers = {}
        if include_kid:
            headers["kid"] = "test-key-id"

        return jwt.encode(
            payload,
            jwks_config["private_key"],
            algorithm="RS256",
            headers=headers,
        )

    def test_verify_valid_supabase_jwt(self, jwks_config: dict[str, str]) -> None:
        """Test verification of a valid Supabase JWT with RS256."""
        token = self.create_test_token(jwks_config)

        # Mock PyJWKClient to return our test public key
        mock_signing_key = Mock()
        mock_signing_key.key = jwks_config["public_key"]

        with patch("heimdex_common.auth._get_jwks_client") as mock_get_client:
            mock_client = Mock(spec=PyJWKClient)
            mock_client.get_signing_key_from_jwt.return_value = mock_signing_key
            mock_get_client.return_value = mock_client

            payload = _verify_supabase_jwt(token)

            assert payload["sub"] == "user-123"
            assert payload["app_metadata"]["org_id"] == "550e8400-e29b-41d4-a716-446655440000"
            assert payload["role"] == "user"
            assert payload["iss"] == "https://test.supabase.co/auth/v1"
            assert payload["aud"] == "heimdex"

    def test_verify_jwt_with_wrong_issuer(self, jwks_config: dict[str, str]) -> None:
        """Test rejection of JWT with wrong issuer claim."""
        token = self.create_test_token(jwks_config, iss="https://wrong-issuer.supabase.co/auth/v1")

        mock_signing_key = Mock()
        mock_signing_key.key = jwks_config["public_key"]

        with patch("heimdex_common.auth._get_jwks_client") as mock_get_client:
            mock_client = Mock(spec=PyJWKClient)
            mock_client.get_signing_key_from_jwt.return_value = mock_signing_key
            mock_get_client.return_value = mock_client

            with pytest.raises(HTTPException) as exc_info:
                _verify_supabase_jwt(token)

            assert exc_info.value.status_code == 401
            assert "issuer" in exc_info.value.detail.lower()

    def test_verify_jwt_with_wrong_audience(self, jwks_config: dict[str, str]) -> None:
        """Test rejection of JWT with wrong audience claim."""
        token = self.create_test_token(jwks_config, aud="wrong-audience")

        mock_signing_key = Mock()
        mock_signing_key.key = jwks_config["public_key"]

        with patch("heimdex_common.auth._get_jwks_client") as mock_get_client:
            mock_client = Mock(spec=PyJWKClient)
            mock_client.get_signing_key_from_jwt.return_value = mock_signing_key
            mock_get_client.return_value = mock_client

            with pytest.raises(HTTPException) as exc_info:
                _verify_supabase_jwt(token)

            assert exc_info.value.status_code == 401
            assert "audience" in exc_info.value.detail.lower()

    def test_verify_expired_jwt(self, jwks_config: dict[str, str]) -> None:
        """Test rejection of expired JWT."""
        token = self.create_test_token(jwks_config, exp_minutes=-1)  # Already expired

        mock_signing_key = Mock()
        mock_signing_key.key = jwks_config["public_key"]

        with patch("heimdex_common.auth._get_jwks_client") as mock_get_client:
            mock_client = Mock(spec=PyJWKClient)
            mock_client.get_signing_key_from_jwt.return_value = mock_signing_key
            mock_get_client.return_value = mock_client

            with pytest.raises(HTTPException) as exc_info:
                _verify_supabase_jwt(token)

            assert exc_info.value.status_code == 401
            assert "expired" in exc_info.value.detail.lower()

    def test_verify_jwt_with_invalid_signature(self, jwks_config: dict[str, str]) -> None:
        """Test rejection of JWT with invalid signature (wrong key)."""
        # Create a completely different key pair
        wrong_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        wrong_private_pem = wrong_private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

        # Sign token with wrong key
        payload = {
            "sub": "user-123",
            "app_metadata": {"org_id": "550e8400-e29b-41d4-a716-446655440000"},
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
            "iss": "https://test.supabase.co/auth/v1",
            "aud": "heimdex",
        }
        token = jwt.encode(
            payload, wrong_private_pem, algorithm="RS256", headers={"kid": "test-key-id"}
        )

        # Try to verify with correct public key
        mock_signing_key = Mock()
        mock_signing_key.key = jwks_config["public_key"]

        with patch("heimdex_common.auth._get_jwks_client") as mock_get_client:
            mock_client = Mock(spec=PyJWKClient)
            mock_client.get_signing_key_from_jwt.return_value = mock_signing_key
            mock_get_client.return_value = mock_client

            with pytest.raises(HTTPException) as exc_info:
                _verify_supabase_jwt(token)

            assert exc_info.value.status_code == 401
            # Token with wrong key can fail as either signature error or malformed
            error_detail = exc_info.value.detail.lower()
            assert any(
                keyword in error_detail
                for keyword in ["signature", "malformed", "invalid", "tampered"]
            )

    def test_verify_jwt_missing_kid_header(self, jwks_config: dict[str, str]) -> None:
        """Test rejection of JWT missing 'kid' header."""
        token = self.create_test_token(jwks_config, include_kid=False)

        with patch("heimdex_common.auth._get_jwks_client") as mock_get_client:
            mock_client = Mock(spec=PyJWKClient)
            # PyJWKClient raises an error when kid is missing
            mock_client.get_signing_key_from_jwt.side_effect = jwt.PyJWKClientError(
                "Unable to find a signing key that matches"
            )
            mock_get_client.return_value = mock_client

            with pytest.raises(HTTPException) as exc_info:
                _verify_supabase_jwt(token)

            assert exc_info.value.status_code == 401
            detail = exc_info.value.detail.lower()
            assert "kid" in detail or "unable to verify" in detail

    def test_verify_jwt_malformed_token(self, jwks_config: dict[str, str]) -> None:
        """Test rejection of malformed JWT."""
        token = "not.a.valid.jwt.token"

        mock_signing_key = Mock()
        mock_signing_key.key = jwks_config["public_key"]

        with patch("heimdex_common.auth._get_jwks_client") as mock_get_client:
            mock_client = Mock(spec=PyJWKClient)
            mock_client.get_signing_key_from_jwt.return_value = mock_signing_key
            mock_get_client.return_value = mock_client

            with pytest.raises(HTTPException) as exc_info:
                _verify_supabase_jwt(token)

            assert exc_info.value.status_code == 401
            detail = exc_info.value.detail.lower()
            assert "malformed" in detail or "invalid" in detail

    def test_full_verify_jwt_supabase_mode(self, jwks_config: dict[str, str]) -> None:
        """Test full JWT verification flow in Supabase mode."""
        token = self.create_test_token(jwks_config)

        mock_signing_key = Mock()
        mock_signing_key.key = jwks_config["public_key"]

        with patch("heimdex_common.auth._get_jwks_client") as mock_get_client:
            mock_client = Mock(spec=PyJWKClient)
            mock_client.get_signing_key_from_jwt.return_value = mock_signing_key
            mock_get_client.return_value = mock_client

            # Mock HTTPBearer credentials
            mock_credentials = MagicMock()
            mock_credentials.credentials = token

            ctx = verify_jwt(credentials=mock_credentials)

            assert isinstance(ctx, RequestContext)
            assert ctx.user_id == "user-123"
            assert ctx.org_id == "550e8400-e29b-41d4-a716-446655440000"
            assert ctx.role == "user"


class TestDevAuthEnvironmentRestrictions:
    """Test that dev auth is properly restricted to local environment."""

    def test_dev_auth_allowed_in_local_env(self) -> None:
        """Test that dev auth works in local environment."""
        os.environ["AUTH_PROVIDER"] = "dev"
        os.environ["HEIMDEX_ENV"] = "local"
        os.environ["DEV_JWT_SECRET"] = "test-secret"  # pragma: allowlist secret

        reset_config()

        # Should not raise an error
        from heimdex_common.config import get_config

        config = get_config()
        assert config.auth_provider == "dev"
        assert config.environment == "local"

        # Cleanup
        for key in ["AUTH_PROVIDER", "HEIMDEX_ENV", "DEV_JWT_SECRET"]:
            os.environ.pop(key, None)
        reset_config()

    def test_dev_auth_rejected_in_dev_env(self) -> None:
        """Test that dev auth is rejected in 'dev' environment."""
        os.environ["AUTH_PROVIDER"] = "dev"
        os.environ["HEIMDEX_ENV"] = "dev"
        os.environ["DEV_JWT_SECRET"] = "test-secret"  # pragma: allowlist secret

        with pytest.raises(ValueError) as exc_info:
            reset_config()
            from heimdex_common.config import get_config

            get_config()

        assert "only allowed when HEIMDEX_ENV=local" in str(exc_info.value)

        # Cleanup
        for key in ["AUTH_PROVIDER", "HEIMDEX_ENV", "DEV_JWT_SECRET"]:
            os.environ.pop(key, None)
        reset_config()

    def test_dev_auth_rejected_in_staging_env(self) -> None:
        """Test that dev auth is rejected in 'staging' environment."""
        os.environ["AUTH_PROVIDER"] = "dev"
        os.environ["HEIMDEX_ENV"] = "staging"
        os.environ["DEV_JWT_SECRET"] = "test-secret"  # pragma: allowlist secret

        with pytest.raises(ValueError) as exc_info:
            reset_config()
            from heimdex_common.config import get_config

            get_config()

        assert "only allowed when HEIMDEX_ENV=local" in str(exc_info.value)

        # Cleanup
        for key in ["AUTH_PROVIDER", "HEIMDEX_ENV", "DEV_JWT_SECRET"]:
            os.environ.pop(key, None)
        reset_config()

    def test_dev_auth_rejected_in_prod_env(self) -> None:
        """Test that dev auth is rejected in 'prod' environment."""
        os.environ["AUTH_PROVIDER"] = "dev"
        os.environ["HEIMDEX_ENV"] = "prod"
        os.environ["DEV_JWT_SECRET"] = "test-secret"  # pragma: allowlist secret

        with pytest.raises(ValueError) as exc_info:
            reset_config()
            from heimdex_common.config import get_config

            get_config()

        assert "only allowed when HEIMDEX_ENV=local" in str(exc_info.value)

        # Cleanup
        for key in ["AUTH_PROVIDER", "HEIMDEX_ENV", "DEV_JWT_SECRET"]:
            os.environ.pop(key, None)
        reset_config()


class TestProductionFailFast:
    """Test that production environment enforces proper auth configuration."""

    def test_prod_requires_supabase_auth(self) -> None:
        """Test that production environment requires Supabase auth."""
        os.environ["AUTH_PROVIDER"] = "dev"
        os.environ["HEIMDEX_ENV"] = "prod"

        with pytest.raises(ValueError) as exc_info:
            reset_config()
            from heimdex_common.config import get_config

            get_config()

        error_msg = str(exc_info.value).lower()
        assert "auth_provider=dev" in error_msg or "dev" in error_msg
        assert "prod" in error_msg
        assert "supabase" in error_msg

        # Cleanup
        for key in ["AUTH_PROVIDER", "HEIMDEX_ENV"]:
            os.environ.pop(key, None)
        reset_config()

    def test_prod_with_supabase_requires_jwks_url(self) -> None:
        """Test that production with Supabase requires JWKS URL."""
        os.environ["AUTH_PROVIDER"] = "supabase"
        os.environ["HEIMDEX_ENV"] = "prod"
        # Missing SUPABASE_JWKS_URL and AUTH_ISSUER

        with pytest.raises(ValueError) as exc_info:
            reset_config()
            from heimdex_common.config import get_config

            get_config()

        assert "SUPABASE_JWKS_URL" in str(exc_info.value)

        # Cleanup
        for key in ["AUTH_PROVIDER", "HEIMDEX_ENV"]:
            os.environ.pop(key, None)
        reset_config()

    def test_prod_with_complete_supabase_config_succeeds(self) -> None:
        """Test that production with complete Supabase config succeeds."""
        os.environ["AUTH_PROVIDER"] = "supabase"
        os.environ["HEIMDEX_ENV"] = "prod"
        os.environ["SUPABASE_JWKS_URL"] = "https://test.supabase.co/auth/v1/jwks"
        os.environ["AUTH_ISSUER"] = "https://test.supabase.co/auth/v1"
        os.environ["AUTH_AUDIENCE"] = "heimdex"

        reset_config()

        # Should not raise an error
        from heimdex_common.config import get_config

        config = get_config()
        assert config.auth_provider == "supabase"
        assert config.environment == "prod"

        # Cleanup
        for key in [
            "AUTH_PROVIDER",
            "HEIMDEX_ENV",
            "SUPABASE_JWKS_URL",
            "AUTH_ISSUER",
            "AUTH_AUDIENCE",
        ]:
            os.environ.pop(key, None)
        reset_config()
