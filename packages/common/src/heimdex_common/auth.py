"""
Authentication and Authorization Middleware.

This module provides JWT-based authentication for Heimdex services,
supporting both Supabase (RS256 with JWKS) and dev mode (HS256).

The middleware extracts user identity and organization scope from JWT tokens
and enforces tenant isolation across all API requests.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from .config import get_config

# HTTP Bearer token extractor
security = HTTPBearer()

# JWKS client cache (lazy-loaded per config)
_jwks_client: PyJWKClient | None = None


@dataclass
class RequestContext:
    """
    Authenticated request context with user and organization identity.

    Attributes:
        user_id: Unique identifier for the authenticated user (from JWT sub claim)
        org_id: Organization ID for tenant isolation (from custom claim)
        role: User role if present (e.g., "admin", "user")
    """

    user_id: str
    org_id: str
    role: str | None = None


def _get_jwks_client() -> PyJWKClient:
    """
    Get or create the JWKS client for Supabase token verification.

    Returns:
        PyJWKClient: Cached JWKS client instance

    Raises:
        ValueError: If SUPABASE_JWKS_URL is not configured
    """
    global _jwks_client
    if _jwks_client is None:
        config = get_config()
        if not config.supabase_jwks_url:
            raise ValueError("SUPABASE_JWKS_URL not configured for Supabase auth")
        _jwks_client = PyJWKClient(config.supabase_jwks_url)
    return _jwks_client


def _verify_dev_jwt(token: str) -> dict[str, Any]:
    """
    Verify JWT token in dev mode using HS256.

    Args:
        token: JWT token string

    Returns:
        dict: Decoded JWT payload

    Raises:
        HTTPException: If token is invalid or expired
    """
    config = get_config()

    try:
        payload = jwt.decode(
            token,
            config.dev_jwt_secret,
            algorithms=["HS256"],
            options={"verify_exp": True},
        )
        return dict(payload)
    except jwt.ExpiredSignatureError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        ) from e
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {e!s}",
        ) from e


def _verify_supabase_jwt(token: str) -> dict[str, Any]:
    """
    Verify JWT token from Supabase using RS256 and JWKS.

    Args:
        token: JWT token string

    Returns:
        dict: Decoded JWT payload

    Raises:
        HTTPException: If token is invalid, expired, or has wrong aud/iss claims
    """
    config = get_config()

    try:
        jwks_client = _get_jwks_client()
        signing_key = jwks_client.get_signing_key_from_jwt(token)

        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=config.auth_audience,
            issuer=config.auth_issuer,
            options={"verify_exp": True, "verify_aud": True, "verify_iss": True},
        )
        return dict(payload)
    except jwt.ExpiredSignatureError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        ) from e
    except jwt.InvalidAudienceError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid audience claim (expected: {config.auth_audience})",
        ) from e
    except jwt.InvalidIssuerError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid issuer claim (expected: {config.auth_issuer})",
        ) from e
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {e!s}",
        ) from e


def _extract_org_id(payload: dict[str, Any]) -> str:
    """
    Extract organization ID from JWT payload.

    Checks multiple possible claim locations:
    1. app_metadata.org_id (Supabase custom claim)
    2. https://heimdex.io/org_id (custom namespace claim)
    3. org_id (direct claim)

    Args:
        payload: Decoded JWT payload

    Returns:
        str: Organization ID

    Raises:
        HTTPException: If org_id claim is missing
    """
    # Try app_metadata.org_id first (Supabase pattern)
    if "app_metadata" in payload and "org_id" in payload["app_metadata"]:
        return str(payload["app_metadata"]["org_id"])

    # Try namespaced claim
    if "https://heimdex.io/org_id" in payload:
        return str(payload["https://heimdex.io/org_id"])

    # Try direct claim
    if "org_id" in payload:
        return str(payload["org_id"])

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing org_id claim in token (required for tenant isolation)",
    )


def verify_jwt(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
) -> RequestContext:
    """
    FastAPI dependency that verifies JWT and extracts request context.

    This is the main entrypoint for auth middleware. It:
    1. Extracts Bearer token from Authorization header
    2. Verifies signature and claims (dev or Supabase mode)
    3. Extracts user_id, org_id, and role
    4. Returns RequestContext for use in route handlers

    Args:
        credentials: HTTP Authorization credentials from request

    Returns:
        RequestContext: Authenticated request context with user/org identity

    Raises:
        HTTPException: If token is missing, invalid, or missing required claims
    """
    config = get_config()
    token = credentials.credentials

    # Verify token based on provider
    if config.auth_provider == "dev":
        payload = _verify_dev_jwt(token)
    else:  # supabase
        payload = _verify_supabase_jwt(token)

    # Extract user_id from 'sub' claim
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing sub claim in token",
        )

    # Extract org_id from custom claim
    org_id = _extract_org_id(payload)

    # Extract optional role
    role = payload.get("role")

    return RequestContext(user_id=user_id, org_id=org_id, role=role)


def create_dev_token(
    user_id: str,
    org_id: str,
    role: str | None = None,
    exp_minutes: int = 60,
) -> str:
    """
    Create a dev mode JWT token for testing.

    Args:
        user_id: User identifier
        org_id: Organization identifier
        role: Optional user role
        exp_minutes: Token expiration in minutes (default: 60)

    Returns:
        str: Signed JWT token

    Note:
        This function should only be used in dev/test environments.
    """
    config = get_config()

    payload = {
        "sub": user_id,
        "org_id": org_id,
        "iat": int(time.time()),
        "exp": int(time.time()) + (exp_minutes * 60),
    }

    if role:
        payload["role"] = role

    return jwt.encode(payload, config.dev_jwt_secret, algorithm="HS256")
