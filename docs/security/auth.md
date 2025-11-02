# Authentication & Authorization

Heimdex uses JWT-based authentication with support for two modes: **Supabase** (production) and **dev** (local development).

## Overview

All API requests (except `/healthz` and `/readyz`) require a valid JWT token in the `Authorization` header:

```
Authorization: Bearer <jwt-token>
```

The authentication middleware:

1. Verifies the JWT signature and claims
2. Extracts user identity (`user_id`) and organization scope (`org_id`)
3. Injects a `RequestContext` into route handlers
4. Enforces tenant isolation across all requests

## Authentication Modes

### Dev Mode (Local Development)

**Purpose**: Simplified auth for local development and testing

**Configuration**:

```bash
AUTH_PROVIDER=dev
DEV_JWT_SECRET=local-dev-secret
```

**Token Format**: HS256-signed JWT

```json
{
  "sub": "user-123",
  "org_id": "org-456",
  "role": "user",
  "iat": 1234567890,
  "exp": 1234571490
}
```

**Creating Dev Tokens**:

```python
from heimdex_common.auth import create_dev_token

token = create_dev_token(
    user_id="user-123",
    org_id="org-456",
    role="admin",
    exp_minutes=60,
)
```

**Example Request**:
  Solution: Use a Token with Valid UUID org_id

  The error you're seeing is because your $TOKEN environment variable contains an old token with an
  invalid org_id (like "org-123" instead of a proper UUID).

  Generate a fresh token:

  ```
  docker exec deploy-api-1 python3 -c "
  from heimdex_common.auth import create_dev_token
  import uuid

  # Generate token with valid UUID org_id
  org_id = str(uuid.uuid4())
  token = create_dev_token(user_id='test-user-1', org_id=org_id, role='user')
  print(f'export TOKEN=\"{token}\"')
  "

  curl -X POST http://localhost:8000/jobs \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer $TOKEN" \
     -d '{"type":"mock_process"}' | jq

  ```

  Then copy the export TOKEN="..." line and run it in your terminal.

```bash
TOKEN=$(python -c "
from heimdex_common.auth import create_dev_token
print(create_dev_token('user-123', 'org-456'))
")

curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/jobs
```

**Security**: Dev mode is **automatically disabled** in production (`HEIMDEX_ENV=prod`). Attempting to use it will cause the service to fail startup.

### Supabase Mode (Production)

**Purpose**: Production-grade auth with Supabase

**Configuration**:

```bash
AUTH_PROVIDER=supabase
SUPABASE_JWKS_URL=https://<project>.supabase.co/auth/v1/jwks
AUTH_AUDIENCE=heimdex
AUTH_ISSUER=https://<project>.supabase.co/
```

**Token Format**: RS256-signed JWT from Supabase Auth

**Required Claims**:

- `sub`: User ID (from Supabase user)
- `aud`: Must match `AUTH_AUDIENCE`
- `iss`: Must match `AUTH_ISSUER`
- `org_id`: Organization ID (see "Organization Claim" below)

**Verification**:

- Signature verified using Supabase JWKS (public keys)
- Claims validated (aud, iss, exp)
- No secrets stored in app code (JWKS fetched at runtime)

## Organization Claim

The `org_id` claim is used for tenant isolation. The middleware checks multiple locations (in order of precedence):

1. **`app_metadata.org_id`** (Supabase custom user metadata)
2. **`https://heimdex.io/org_id`** (Namespaced custom claim)
3. **`org_id`** (Direct claim)

**Supabase Setup** (recommended):

Add `org_id` to user metadata via SQL trigger or auth hook:

```sql
-- Example: Set org_id when user signs up
CREATE OR REPLACE FUNCTION public.set_org_id()
RETURNS TRIGGER AS $$
BEGIN
  NEW.raw_app_meta_data = jsonb_set(
    COALESCE(NEW.raw_app_meta_data, '{}'::jsonb),
    '{org_id}',
    to_jsonb(NEW.id::text)  -- Or lookup from organizations table
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER on_auth_user_created
  BEFORE INSERT ON auth.users
  FOR EACH ROW
  EXECUTE FUNCTION public.set_org_id();
```

The `org_id` will then appear in JWT tokens as:

```json
{
  "app_metadata": {
    "org_id": "org-uuid-here"
  }
}
```

## Request Context

Authenticated requests receive a `RequestContext` object injected by FastAPI dependency injection:

```python
from fastapi import Depends
from heimdex_common.auth import RequestContext, verify_jwt

@router.post("/jobs")
async def create_job(
    request: JobCreateRequest,
    ctx: RequestContext = Depends(verify_jwt),
):
    # ctx.user_id: str - authenticated user ID
    # ctx.org_id: str - organization ID for tenant isolation
    # ctx.role: str | None - optional role claim

    # Jobs are automatically scoped to the authenticated org
    job = repo.create_job(
        org_id=ctx.org_id,
        requested_by=ctx.user_id,
        ...
    )
```

## Tenant Isolation

All data access is scoped by `org_id`:

**Creating Resources**:

```python
# Force org_id to authenticated user's organization
job = repo.create_job(org_id=ctx.org_id, ...)
```

**Reading Resources**:

```python
job = repo.get_job_by_id(job_id)

# Enforce tenant boundary
if str(job.org_id) != ctx.org_id:
    raise HTTPException(status_code=403, detail="Access denied")
```

**Cross-Tenant Access**: Returns HTTP 403 Forbidden

## Security Best Practices

### Secrets Management

**❌ Never commit secrets**:

```bash
# DO NOT do this
DEV_JWT_SECRET=super-secret-key  # ❌ Committed to git
```

**✅ Use environment variables**:

```bash
# Local development: .env file (git-ignored)
DEV_JWT_SECRET=local-dev-secret

# Production: Secret Manager
DEV_JWT_SECRET=$(gcloud secrets versions access latest --secret=dev-jwt-secret)
```

### Token Expiry

**Dev mode**: Default 60 minutes (configurable via `exp_minutes`)

**Supabase mode**: Controlled by Supabase (typically 1 hour access token + refresh token)

### HTTPS Only

**Production**: Always use HTTPS to prevent token interception

**Local development**: HTTP is acceptable since tokens are dev-only and short-lived

## Error Responses

### 401 Unauthorized

**Missing token**:

```json
{
  "detail": "Not authenticated"
}
```

**Expired token**:

```json
{
  "detail": "Token has expired"
}
```

**Invalid signature**:

```json
{
  "detail": "Invalid token: Signature verification failed"
}
```

**Missing required claim**:

```json
{
  "detail": "Missing org_id claim in token (required for tenant isolation)"
}
```

### 403 Forbidden

**Cross-tenant access**:

```json
{
  "detail": "Access denied: job belongs to a different organization"
}
```

## Testing

### Unit Tests

```python
from heimdex_common.auth import create_dev_token

def test_cross_tenant_access():
    # Create tokens for different orgs
    token_org_a = create_dev_token("user-1", "org-a")
    token_org_b = create_dev_token("user-2", "org-b")

    # Create job as org-a
    response = client.post(
        "/jobs",
        headers={"Authorization": f"Bearer {token_org_a}"},
        json={"type": "mock_process"},
    )
    job_id = response.json()["job_id"]

    # Try to access as org-b (should fail)
    response = client.get(
        f"/jobs/{job_id}",
        headers={"Authorization": f"Bearer {token_org_b}"},
    )
    assert response.status_code == 403
```

### Integration Tests

```bash
# Create token for test org
export TEST_TOKEN=$(python -c "
from heimdex_common.auth import create_dev_token
print(create_dev_token('test-user', 'test-org'))
")

# Use in requests
curl -H "Authorization: Bearer $TEST_TOKEN" \
     http://localhost:8000/jobs
```

## Troubleshooting

### "AUTH_PROVIDER=dev is not allowed in production"

**Cause**: Attempting to use dev mode in production environment

**Solution**: Set `AUTH_PROVIDER=supabase` and configure Supabase credentials

### "SUPABASE_JWKS_URL not configured for Supabase auth"

**Cause**: Missing Supabase configuration when `AUTH_PROVIDER=supabase`

**Solution**: Set all required Supabase env vars:

```bash
SUPABASE_JWKS_URL=https://<project>.supabase.co/auth/v1/jwks
AUTH_AUDIENCE=heimdex
AUTH_ISSUER=https://<project>.supabase.co/
```

### "Missing org_id claim in token"

**Cause**: JWT doesn't contain `org_id` in any expected location

**Solution**: Configure Supabase to include `org_id` in user metadata (see "Organization Claim" section)

## Migration Path

### Phase 1: Local Development (Current)

- Use dev mode with hardcoded secrets
- Manual token generation for testing

### Phase 2: Supabase Integration (Next)

- Configure Supabase project
- Set up org_id metadata
- Switch production to Supabase mode

### Phase 3: Advanced Features (Future)

- Role-based access control (RBAC)
- API key auth for service-to-service calls
- OAuth2 for third-party integrations

## References

- JWT specification: [RFC 7519](https://tools.ietf.org/html/rfc7519)
- Supabase Auth: [https://supabase.com/docs/guides/auth](https://supabase.com/docs/guides/auth)
- FastAPI security: [https://fastapi.tiangolo.com/tutorial/security/](https://fastapi.tiangolo.com/tutorial/security/)
