"""
Authentication and Authorization Middleware for Heimdex Services.

This module provides robust JWT-based authentication, acting as a critical
security layer for the entire platform. It is designed to be flexible,
supporting multiple authentication providers while enforcing strict tenant
isolation, which is a core security principle of the Heimdex architecture.

Supported Authentication Modes:
- **Supabase (Production)**: Uses RS256 asymmetric cryptography with a JSON Web
  Key Set (JWKS) to verify tokens issued by Supabase. This is the recommended
  mode for production environments, as it allows the API to verify tokens
  without needing access to a shared secret.
- **Development Mode**: Uses HS256 symmetric cryptography with a shared secret.
  This mode is provided for local development and testing, simplifying the
  process of generating valid tokens without a full-fledged authentication
  provider.

Core Responsibilities:
- **Token Extraction**: Retrieves JWTs from the HTTP 'Authorization' header.
- **Token Verification**: Validates the token's signature, expiration time (exp),
  issuer (iss), and audience (aud) claims.
- **Context Creation**: Extracts user identity ('sub' claim) and organization
  scope ('org_id' custom claim) from the token.
- **Tenant Isolation**: Ensures that every authenticated request is scoped to a
  single organization, preventing data leakage between tenants.
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

# HTTP Bearer token extractor, a standard FastAPI utility for parsing
# 'Authorization: Bearer <token>' headers.
security = HTTPBearer()

# A global cache for the JWKS client. This is lazy-loaded to avoid
# making external HTTP requests on module import and is reused across
# requests for efficiency.
_jwks_client: PyJWKClient | None = None


@dataclass
class RequestContext:
    """
    Represents the authenticated context of an incoming request.

    This data class is populated by the `verify_jwt` dependency and provides
    downstream route handlers with strongly-typed access to the authenticated
    user's identity and organizational scope. It is the primary mechanism for
    enforcing tenant isolation at the application layer.

    Attributes:
        user_id (str): The unique identifier for the authenticated user, extracted
            from the standard 'sub' (subject) claim of the JWT.
        org_id (str): The identifier for the organization the user is acting
            within. This value is critical for ensuring that all data access is
            scoped to the correct tenant. It is extracted from a custom claim
    .
        role (str | None): An optional user role, such as 'admin' or 'member',
            which can be used for more granular authorization checks.
            Extracted from the 'role' claim if present.
    """

    user_id: str
    org_id: str
    role: str | None = None


def _get_jwks_client() -> PyJWKClient:
    """
    Retrieves or initializes the JWKS client for Supabase token verification.

    This function implements a lazy-loading pattern for the PyJWKClient. The client
    is responsible for fetching the JSON Web Key Set from Supabase's configured
    URL, which contains the public keys required to verify RS256 JWT signatures.
    The client is cached globally to prevent re-fetching the JWKS on every request.

    Returns:
        PyJWKClient: A cached instance of the JWKS client.

    Raises:
        ValueError: If the application is configured for Supabase authentication
            but the `SUPABASE_JWKS_URL` environment variable is not set.
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
    Verifies a JWT in development mode using a symmetric HS256 key.

    This verification method is used when the 'AUTH_PROVIDER' is set to 'dev'.
    It uses a shared secret (`DEV_JWT_SECRET`) to decode the token. This is
    simpler for local testing but is not suitable for production.

    Args:
        token (str): The JWT token string extracted from the request header.

    Returns:
        dict[str, Any]: The decoded JWT payload as a dictionary.

    Raises:
        HTTPException (401 Unauthorized): If the token has expired or if its
            signature is invalid, indicating it was tampered with or signed
            with the wrong key.
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
    Verifies a JWT from Supabase using an asymmetric RS256 key from JWKS.

    This is the production-grade verification method. It involves several steps:
    1. Fetching the public signing key from the Supabase JWKS endpoint.
    2. Verifying the token's signature against the fetched public key.
    3. Validating standard claims: 'exp' (expiration), 'aud' (audience), and
       'iss' (issuer) to ensure the token is intended for this application.

    Args:
        token (str): The JWT token string from the request.

    Returns:
        dict[str, Any]: The decoded JWT payload.

    Raises:
        HTTPException (401 Unauthorized): If the token is invalid for any reason,
            including signature mismatch, expiration, or incorrect audience/issuer.
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
    Extracts the organization ID from the JWT payload.

    The organization ID is fundamental for enforcing tenant isolation. This
    function searches for the 'org_id' in a prioritized list of possible
    locations within the JWT claims, ensuring compatibility with different
    token structures.

    Search Priority:
    1. `app_metadata.org_id`: A common pattern for custom claims in Supabase.
    2. `https://heimdex.io/org_id`: A namespaced claim, following best practices
       to avoid collisions.
    3. `org_id`: A direct, top-level claim.

    Args:
        payload (dict[str, Any]): The decoded JWT payload.

    Returns:
        str: The extracted organization ID.

    Raises:
        HTTPException (401 Unauthorized): If the 'org_id' claim cannot be
            found in any of the expected locations, as this is a critical
            requirement for secure data access.
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
    A FastAPI dependency that secures routes by verifying the JWT.

    This function serves as the primary authentication middleware for API
    endpoints. By adding it as a dependency to a route, you ensure that the
    request is authenticated and authorized before the route's logic is
    executed.

    Workflow:
    1. The `HTTPBearer` dependency extracts the token from the 'Authorization'
       header.
    2. The token is passed to the appropriate verification function based on the
       configured `AUTH_PROVIDER`.
    3. The user ID ('sub') and organization ID ('org_id') are extracted from
       the verified payload.
    4. A `RequestContext` object is instantiated and returned.

    This returned context can then be injected directly into the route handler's
    parameters, providing a clean and secure way to access user and tenant info.

    Args:
        credentials (HTTPAuthorizationCredentials): The credentials object
            provided by the `HTTPBearer` security dependency.

    Returns:
        RequestContext: An object containing the authenticated user_id, org_id,
            and optional role, ready for use in the application logic.

    Raises:
        HTTPException (401 Unauthorized): If the token is missing, malformed,
            invalid, or does not contain the necessary claims for authentication
            and tenant scoping.
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
    Creates a JWT for testing and development purposes.

    This utility function is essential for local development, enabling the
    creation of valid tokens without needing an external identity provider.
    It signs the token with the `DEV_JWT_SECRET`.

    Args:
        user_id (str): The user identifier to be placed in the 'sub' claim.
        org_id (str): The organization identifier for tenant scoping.
        role (str | None): An optional role to include in the token.
        exp_minutes (int): The token's lifetime in minutes from the current time.
                           Defaults to 60 minutes.

    Returns:
        str: A signed HS256 JWT token as a string.

    Warning:
        This function and the associated 'dev' authentication provider must
        never be used in a production environment due to their reliance on a
        shared secret.
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
