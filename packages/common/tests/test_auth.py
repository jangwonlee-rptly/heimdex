"""Tests for authentication middleware."""

from __future__ import annotations

import os
import time
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock

import jwt
import pytest
from fastapi import HTTPException

from heimdex_common.auth import (
    RequestContext,
    _extract_org_id,
    _verify_dev_jwt,
    create_dev_token,
    verify_jwt,
)
from heimdex_common.config import reset_config


@pytest.fixture(autouse=True)
def reset_config_for_tests() -> Generator[None, None, None]:
    """Reset config before and after each test."""
    reset_config()
    yield
    reset_config()


@pytest.fixture
def dev_auth_config() -> Generator[None, None, None]:
    """Configure environment for dev auth mode."""
    os.environ["AUTH_PROVIDER"] = "dev"
    os.environ["DEV_JWT_SECRET"] = "test-secret"
    os.environ["HEIMDEX_ENV"] = "local"
    reset_config()
    yield
    # Cleanup
    for key in ["AUTH_PROVIDER", "DEV_JWT_SECRET", "HEIMDEX_ENV"]:
        os.environ.pop(key, None)


class TestDevJWTVerification:
    """Test dev mode JWT verification."""

    def test_verify_valid_dev_jwt(self, dev_auth_config: Any) -> None:
        """Test verification of a valid dev JWT."""
        token = create_dev_token(
            user_id="user-123",
            org_id="550e8400-e29b-41d4-a716-446655440000",
            role="admin",
        )

        payload = _verify_dev_jwt(token)

        assert payload["sub"] == "user-123"
        assert payload["org_id"] == "550e8400-e29b-41d4-a716-446655440000"
        assert payload["role"] == "admin"

    def test_verify_expired_dev_jwt(self, dev_auth_config: Any) -> None:
        """Test verification of an expired dev JWT."""
        # Create token that expires immediately
        token = create_dev_token(
            user_id="user-123",
            org_id="550e8400-e29b-41d4-a716-446655440000",
            exp_minutes=-1,  # Already expired
        )

        with pytest.raises(HTTPException) as exc_info:
            _verify_dev_jwt(token)

        assert exc_info.value.status_code == 401
        assert "expired" in exc_info.value.detail.lower()

    def test_verify_invalid_signature_dev_jwt(self, dev_auth_config: Any) -> None:
        """Test verification of a JWT with invalid signature."""
        # Create token with wrong secret
        token = jwt.encode(
            {
                "sub": "user-123",
                "org_id": "550e8400-e29b-41d4-a716-446655440000",
                "exp": int(time.time()) + 3600,
            },
            "wrong-secret",
            algorithm="HS256",
        )

        with pytest.raises(HTTPException) as exc_info:
            _verify_dev_jwt(token)

        assert exc_info.value.status_code == 401
        assert "invalid" in exc_info.value.detail.lower()


class TestOrgIdExtraction:
    """Test organization ID extraction from JWT payloads."""

    def test_extract_org_id_from_app_metadata(self) -> None:
        """Test extraction from app_metadata.org_id (Supabase pattern)."""
        uuid_org = "550e8400-e29b-41d4-a716-446655440000"
        payload = {
            "sub": "user-123",
            "app_metadata": {"org_id": uuid_org},
        }

        org_id = _extract_org_id(payload)

        assert org_id == uuid_org

    def test_extract_org_id_from_namespaced_claim(self) -> None:
        """Test extraction from namespaced custom claim."""
        uuid_org = "550e8400-e29b-41d4-a716-446655440001"
        payload = {
            "sub": "user-123",
            "https://heimdex.io/org_id": uuid_org,
        }

        org_id = _extract_org_id(payload)

        assert org_id == uuid_org

    def test_extract_org_id_from_direct_claim(self) -> None:
        """Test extraction from direct org_id claim."""
        uuid_org = "550e8400-e29b-41d4-a716-446655440002"
        payload = {
            "sub": "user-123",
            "org_id": uuid_org,
        }

        org_id = _extract_org_id(payload)

        assert org_id == uuid_org

    def test_extract_org_id_missing(self) -> None:
        """Test extraction fails when org_id is missing."""
        payload = {
            "sub": "user-123",
        }

        with pytest.raises(HTTPException) as exc_info:
            _extract_org_id(payload)

        assert exc_info.value.status_code == 401
        assert "org_id" in exc_info.value.detail.lower()

    def test_extract_org_id_precedence(self) -> None:
        """Test that app_metadata takes precedence over other claims."""
        uuid_app = "550e8400-e29b-41d4-a716-446655440000"
        uuid_ns = "550e8400-e29b-41d4-a716-446655440001"
        uuid_direct = "550e8400-e29b-41d4-a716-446655440002"
        payload = {
            "sub": "user-123",
            "app_metadata": {"org_id": uuid_app},
            "https://heimdex.io/org_id": uuid_ns,
            "org_id": uuid_direct,
        }

        org_id = _extract_org_id(payload)

        # app_metadata should win
        assert org_id == uuid_app


class TestVerifyJWT:
    """Test full JWT verification flow."""

    def test_verify_jwt_dev_mode_success(self, dev_auth_config: Any) -> None:
        """Test successful JWT verification in dev mode."""
        uuid_org = "550e8400-e29b-41d4-a716-446655440000"
        token = create_dev_token(
            user_id="user-123",
            org_id=uuid_org,
            role="user",
        )

        # Mock HTTPBearer credentials
        mock_credentials = MagicMock()
        mock_credentials.credentials = token

        ctx = verify_jwt(credentials=mock_credentials)

        assert isinstance(ctx, RequestContext)
        assert ctx.user_id == "user-123"
        assert ctx.org_id == uuid_org
        assert ctx.role == "user"

    def test_verify_jwt_missing_sub_claim(self, dev_auth_config: Any) -> None:
        """Test JWT verification fails when sub claim is missing."""
        # Create token without sub claim
        uuid_org = "550e8400-e29b-41d4-a716-446655440000"
        payload = {
            "org_id": uuid_org,
            "exp": int(time.time()) + 3600,
        }
        token = jwt.encode(payload, "test-secret", algorithm="HS256")

        mock_credentials = MagicMock()
        mock_credentials.credentials = token

        with pytest.raises(HTTPException) as exc_info:
            verify_jwt(credentials=mock_credentials)

        assert exc_info.value.status_code == 401
        assert "sub" in exc_info.value.detail.lower()

    def test_verify_jwt_missing_org_id(self, dev_auth_config: Any) -> None:
        """Test JWT verification fails when org_id is missing."""
        payload = {
            "sub": "user-123",
            "exp": int(time.time()) + 3600,
        }
        token = jwt.encode(payload, "test-secret", algorithm="HS256")

        mock_credentials = MagicMock()
        mock_credentials.credentials = token

        with pytest.raises(HTTPException) as exc_info:
            verify_jwt(credentials=mock_credentials)

        assert exc_info.value.status_code == 401
        assert "org_id" in exc_info.value.detail.lower()


class TestConfigValidation:
    """Test configuration validation for auth settings."""

    def test_dev_auth_not_allowed_in_prod(self) -> None:
        """Test that dev auth is rejected in production."""
        os.environ["AUTH_PROVIDER"] = "dev"
        os.environ["HEIMDEX_ENV"] = "prod"

        with pytest.raises(ValueError) as exc_info:
            from heimdex_common.config import get_config

            get_config()

        assert "not allowed in production" in str(exc_info.value).lower()

        # Cleanup
        os.environ.pop("AUTH_PROVIDER", None)
        os.environ.pop("HEIMDEX_ENV", None)
        reset_config()

    def test_supabase_auth_requires_jwks_url(self) -> None:
        """Test that Supabase auth requires JWKS URL."""
        os.environ["AUTH_PROVIDER"] = "supabase"
        os.environ["HEIMDEX_ENV"] = "dev"
        # Missing SUPABASE_JWKS_URL

        with pytest.raises(ValueError) as exc_info:
            from heimdex_common.config import get_config

            get_config()

        assert "SUPABASE_JWKS_URL" in str(exc_info.value)

        # Cleanup
        os.environ.pop("AUTH_PROVIDER", None)
        os.environ.pop("HEIMDEX_ENV", None)
        reset_config()

    def test_supabase_auth_requires_audience(self) -> None:
        """Test that Supabase auth requires audience."""
        os.environ["AUTH_PROVIDER"] = "supabase"
        os.environ["SUPABASE_JWKS_URL"] = "https://example.supabase.co/auth/v1/jwks"
        os.environ["HEIMDEX_ENV"] = "dev"
        # Missing AUTH_AUDIENCE

        with pytest.raises(ValueError) as exc_info:
            from heimdex_common.config import get_config

            get_config()

        assert "AUTH_AUDIENCE" in str(exc_info.value)

        # Cleanup
        for key in ["AUTH_PROVIDER", "SUPABASE_JWKS_URL", "HEIMDEX_ENV"]:
            os.environ.pop(key, None)
        reset_config()


class TestCreateDevToken:
    """Test dev token creation utility."""

    def test_create_dev_token_basic(self, dev_auth_config: Any) -> None:
        """Test creating a basic dev token."""
        uuid_org = "550e8400-e29b-41d4-a716-446655440000"
        token = create_dev_token(user_id="user-123", org_id=uuid_org)

        # Decode and verify
        from heimdex_common.config import get_config

        config = get_config()
        payload = jwt.decode(token, config.dev_jwt_secret, algorithms=["HS256"])

        assert payload["sub"] == "user-123"
        assert payload["org_id"] == uuid_org
        assert "iat" in payload
        assert "exp" in payload

    def test_create_dev_token_with_role(self, dev_auth_config: Any) -> None:
        """Test creating a dev token with role."""
        uuid_org = "550e8400-e29b-41d4-a716-446655440000"
        token = create_dev_token(
            user_id="user-123",
            org_id=uuid_org,
            role="admin",
        )

        from heimdex_common.config import get_config

        config = get_config()
        payload = jwt.decode(token, config.dev_jwt_secret, algorithms=["HS256"])

        assert payload["role"] == "admin"

    def test_create_dev_token_custom_expiry(self, dev_auth_config: Any) -> None:
        """Test creating a dev token with custom expiry."""
        uuid_org = "550e8400-e29b-41d4-a716-446655440000"
        token = create_dev_token(
            user_id="user-123",
            org_id=uuid_org,
            exp_minutes=5,
        )

        from heimdex_common.config import get_config

        config = get_config()
        payload = jwt.decode(token, config.dev_jwt_secret, algorithms=["HS256"])

        # Check expiry is approximately 5 minutes from now
        expected_exp = int(time.time()) + (5 * 60)
        assert abs(payload["exp"] - expected_exp) < 5  # Within 5 seconds tolerance
