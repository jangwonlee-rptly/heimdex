# Security

This document outlines the security posture of Heimdex and best practices for secure deployment.

## Security Principles

Heimdex follows these core security principles:

1. **Least Privilege**: Every component has minimal required permissions
2. **Defense in Depth**: Multiple layers of security controls
3. **Fail Securely**: Errors default to denying access
4. **Zero Trust**: All requests must be authenticated and authorized
5. **Secrets Hygiene**: No secrets in code, containers, or version control

## Authentication & Authorization

### JWT-Based Authentication

**Dev Mode** (local development only):
- HS256 symmetric signing
- Automatically disabled in production
- Short-lived tokens (60 minutes default)

**Supabase Mode** (production):
- RS256 asymmetric signing
- Public key verification via JWKS
- No secrets stored in application
- Audience and issuer validation

See [auth.md](./auth.md) for details.

### Tenant Isolation

**Enforcement**: Every request is scoped to `org_id` from JWT
- Jobs created with authenticated `org_id`
- Cross-tenant access returns HTTP 403
- Database queries filtered by `org_id`

**Future**: Row-level security (RLS) in PostgreSQL for additional layer

## Container Security

### Non-Root Execution

All containers run as non-root user `appuser` (UID 1000):

```dockerfile
USER appuser
```

**Benefits**:
- Limits blast radius of container compromise
- Prevents privilege escalation attacks
- Complies with PCI-DSS, SOC 2 requirements

### Read-Only Root Filesystem

**Cloud Run Configuration**:
```hcl
security_context {
  run_as_non_root = true
  read_only_root_filesystem = true
}
```

**Writable Directories**:
- `/tmp` - Application temporary files
- `/home/appuser` - User home directory (minimal usage)

**Benefits**:
- Prevents malware persistence
- Blocks file-based attacks
- Enables easy rollback (stateless containers)

### Minimal Base Images

**Base**: `python:3.11-slim`
- Debian-based, security-patched
- No unnecessary packages (curl only)
- Regular updates via Dependabot

**Attack Surface**:
- ~100 MB image size
- ~50 installed packages
- No shells (bash, sh) available to appuser

### Vulnerability Scanning

**Automated Scanning**:
```yaml
# .github/workflows/build.yml
- uses: aquasecurity/trivy-action@master
  with:
    severity: 'CRITICAL,HIGH'
    exit-code: '1'  # Fail build on critical vulns
```

**Scan Frequency**:
- On every image build
- Weekly scheduled scans
- On dependency updates

## Secrets Management

### Secret Manager Integration

**Storage**:
```bash
# Never in code or env files
echo -n "secret-value" | gcloud secrets create secret-name --data-file=-
```

**Access**:
```hcl
env {
  name = "DEV_JWT_SECRET"
  value_source {
    secret_key_ref {
      secret  = "dev-jwt-secret-prod"
      version = "latest"
    }
  }
}
```

**Benefits**:
- Automatic rotation support
- Audit logs for access
- Version history
- Encrypted at rest and in transit

### Prohibited Practices

**❌ Never Do**:
```bash
# Hardcoded secrets
JWT_SECRET = "my-secret-key"

# Committed .env files
git add .env

# Secrets in Dockerfiles
ENV SECRET_KEY=abc123

# Secrets in logs
logger.info(f"Using key: {secret}")
```

**✅ Always Do**:
```bash
# Environment variables (from Secret Manager)
JWT_SECRET = os.getenv("DEV_JWT_SECRET")

# Git-ignored .env files
echo ".env" >> .gitignore

# Redacted logging
config.log_summary(redact_secrets=True)
```

## IAM & Access Control

### Service Account Least Privilege

**API Service Account**:
- `roles/secretmanager.secretAccessor` (specific secrets only)
- `roles/cloudsql.client` (if using Cloud SQL)
- **No**: Broad roles like `roles/editor`

**Worker Service Account**:
- `roles/secretmanager.secretAccessor` (specific secrets only)
- `roles/cloudsql.client` (if using Cloud SQL)
- **No**: Ability to modify infrastructure

**CI Service Account**:
- `roles/artifactregistry.writer` (scoped to heimdex repo)
- `roles/run.admin` (for deployments)
- `roles/iam.serviceAccountUser` (to deploy as API/Worker SAs)
- **No**: Ability to delete resources

### Workload Identity Federation

**No Long-Lived Keys**:
```bash
# ❌ Don't create service account keys
gcloud iam service-accounts keys create key.json --iam-account=...

# ✅ Use Workload Identity Federation
gcloud iam workload-identity-pools create-cred-config ...
```

**Benefits**:
- Keys rotate automatically (every 10 minutes)
- No key leakage risk
- GitHub OIDC token authentication
- Audit trail via Cloud Logging

## Network Security

### Cloud Run Ingress Controls

**API Service**: `INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER`
- Accessible via Cloud Load Balancer
- Optional: Restrict to Cloud Armor allowlist

**Worker Service**: `INGRESS_TRAFFIC_INTERNAL_ONLY`
- No public internet access
- Only accessible from VPC

### Future Enhancements

- **Cloud Armor**: WAF, DDoS protection, IP allowlists
- **VPC Service Controls**: Perimeter-based access control
- **Private Service Connect**: Secure DB connections

## Data Security

### Encryption at Rest

**Cloud Run**: Volumes encrypted by default (Google-managed keys)

**PostgreSQL**:
- Supabase: Encrypted by default
- Cloud SQL: Automatic encryption

**Secret Manager**: AES-256 encryption

### Encryption in Transit

**HTTPS Only**:
- Cloud Run enforces HTTPS
- TLS 1.2+ required
- HTTP requests automatically redirected

**Database Connections**:
```python
# PostgreSQL: SSL mode required in production
PGSSLMODE=require
```

### Data Redaction

**Logging**:
```python
# Automatic redaction
config.log_summary(redact_secrets=True)

# Output:
# "pguser": "***"
# "redis_url": "redis://***@host:6379/0"
```

**Never Logged**:
- Passwords
- JWT secrets
- API keys
- User tokens

## Dependency Security

### Dependency Pinning

**Strict Version Ranges**:
```toml
[dependencies]
fastapi = ">=0.104.0,<1.0.0"  # Allows patches, not majors
pydantic = ">=2.0.0,<3.0.0"
```

**Lock Files**: `uv.lock` committed to version control

### Automated Updates

**Dependabot Configuration**:
```yaml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/packages/common"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 5
```

**Review Process**:
1. Dependabot opens PR with changelog
2. CI runs tests + security scans
3. Manual review for breaking changes
4. Auto-merge for patches

### Vulnerability Monitoring

**Tools**:
- Trivy (container scanning)
- GitHub Security Advisories
- Dependabot alerts

**Response SLA**:
- **Critical**: Patch within 24 hours
- **High**: Patch within 7 days
- **Medium/Low**: Next release cycle

## Application Security

### Input Validation

**FastAPI Pydantic Models**:
```python
class JobCreateRequest(BaseModel):
    type: str  # Validated against enum
    fail_at_stage: str | None  # Optional, validated type
```

**Benefits**:
- Type safety
- Automatic 422 errors for invalid input
- No SQL injection (using ORM)

### SQL Injection Prevention

**Use SQLAlchemy ORM**:
```python
# ✅ Safe - parameterized query
job = session.query(Job).filter(Job.id == job_id).first()

# ❌ Never do raw SQL with string formatting
session.execute(f"SELECT * FROM jobs WHERE id = '{job_id}'")
```

### XSS Prevention

**API-Only**: No HTML rendering, only JSON responses
- Content-Type: application/json
- No user-generated HTML

### CSRF Protection

**Not Required**: API uses Bearer tokens (not cookies)
- SameSite cookies not used
- Stateless authentication

## Monitoring & Incident Response

### Security Logging

**Audit Events Logged**:
- Authentication attempts (success/failure)
- Authorization failures (403 responses)
- Resource access (job creation, retrieval)
- Configuration changes

**Log Format**: Structured JSON
```json
{
  "ts": "2025-01-15T10:30:00Z",
  "level": "WARNING",
  "msg": "auth_failed",
  "user_id": "unknown",
  "reason": "expired_token",
  "ip": "1.2.3.4"
}
```

### Alerting

**Critical Alerts**:
- High 401/403 error rate (>10% requests)
- Repeated authentication failures (>100/min)
- Unauthorized secret access attempts
- Container vulnerability CRITICAL/HIGH

**Channels**:
- Cloud Monitoring → PagerDuty
- Slack notifications for warnings

### Incident Response Plan

1. **Detection**: Automated alerts or user report
2. **Triage**: Assess severity (P0-P4)
3. **Containment**:
   - Revoke compromised credentials
   - Roll back to last known good version
   - Block malicious IPs
4. **Eradication**: Patch vulnerabilities
5. **Recovery**: Restore service
6. **Post-Mortem**: Document lessons learned

## Compliance & Auditing

### Audit Logs

**Cloud Logging Retention**:
- Default: 30 days
- Recommended: 365 days for production

**Audit Queries**:
```bash
# All authentication events
gcloud logging read "jsonPayload.msg=~'auth_.*'" --limit=100

# Failed authorization (cross-tenant access)
gcloud logging read "jsonPayload.status_code=403" --limit=50

# Secret access
gcloud logging read "protoPayload.serviceName='secretmanager.googleapis.com'" --limit=20
```

### Compliance Readiness

**SOC 2 Type II**:
- [x] Least-privilege IAM
- [x] Encryption at rest/transit
- [x] Audit logging
- [ ] Formal access review process (manual for now)

**PCI-DSS** (if processing payments):
- [x] No cardholder data stored
- [x] Containers run as non-root
- [x] Network segmentation (internal-only worker)

## Security Checklist

### Development

- [ ] No secrets committed to git
- [ ] Pre-commit hooks run security checks
- [ ] Dependencies pinned and up-to-date
- [ ] Unit tests include auth/authz tests

### Deployment

- [ ] Secrets stored in Secret Manager
- [ ] Workload Identity (no SA keys)
- [ ] Containers run as non-root
- [ ] Read-only root filesystem enabled
- [ ] Vulnerability scanning passes (no CRITICAL)

### Production

- [ ] HTTPS enforced
- [ ] Database connections use SSL
- [ ] Monitoring and alerting configured
- [ ] Incident response plan documented
- [ ] Regular security reviews scheduled

## Reporting Security Issues

**Contact**: security@heimdex.example.com (create this)

**Process**:
1. **Do not** open a public GitHub issue
2. Email details to security contact
3. Include:
   - Description of vulnerability
   - Steps to reproduce
   - Impact assessment
4. We will respond within 48 hours
5. Fix will be developed privately
6. Credit given upon disclosure (if desired)

## References

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Cloud Run Security](https://cloud.google.com/run/docs/securing/https)
- [GCP Secret Manager](https://cloud.google.com/secret-manager/docs)
- [Workload Identity](https://cloud.google.com/iam/docs/workload-identity-federation)
