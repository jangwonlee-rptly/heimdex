# Deployment Guide

This guide covers deploying Heimdex to Google Cloud Platform using Terraform and GitHub Actions.

## Prerequisites

- GCP project with billing enabled
- `gcloud` CLI installed and authenticated
- Terraform >= 1.5
- GitHub repository with Actions enabled
- Domain (optional, for custom URLs)

## Architecture

```
GitHub Actions (CI/CD)
  ↓ (Workload Identity)
  ↓
Google Cloud Platform
  ├── Artifact Registry (Docker images)
  ├── Secret Manager (credentials)
  ├── Cloud Run (API + Worker)
  └── IAM (service accounts, roles)

External (not managed by Terraform yet):
  ├── PostgreSQL (Supabase or Cloud SQL)
  └── Redis (Upstash or Memorystore)
```

## Step 1: Initial GCP Setup

### 1.1 Create GCP Project

```bash
export PROJECT_ID="heimdex-prod"
export REGION="us-central1"

gcloud projects create $PROJECT_ID
gcloud config set project $PROJECT_ID

# Enable billing (required)
gcloud billing accounts list
gcloud billing projects link $PROJECT_ID \
  --billing-account=YOUR_BILLING_ACCOUNT_ID
```

### 1.2 Enable Required APIs

```bash
gcloud services enable \
  artifactregistry.googleapis.com \
  cloudresourcemanager.googleapis.com \
  compute.googleapis.com \
  iam.googleapis.com \
  run.googleapis.com \
  secretmanager.googleapis.com
```

## Step 2: Configure Terraform

### 2.1 Set Up Terraform Variables

```bash
cd infra/terraform

# Copy example variables
cp terraform.tfvars.example terraform.tfvars

# Edit with your values
nano terraform.tfvars
```

**terraform.tfvars**:
```hcl
project_id   = "heimdex-prod"
region       = "us-central1"
environment  = "prod"

# Image tags (updated by CI/CD)
api_image_tag    = "latest"
worker_image_tag = "latest"

# Scaling
api_min_instances    = 1  # Keep 1 instance warm in prod
worker_min_instances = 0  # Scale-to-zero for worker

# Secrets (use strong values in production!)
dev_jwt_secret = "CHANGE-ME-STRONG-SECRET-HERE"

# Cost optimization (enable when ready)
enable_cloudsql      = false  # Use external PostgreSQL for now
enable_redis         = false  # Use external Redis for now
enable_vpc_connector = false  # Only if using private VPC
```

### 2.2 Initialize Terraform

```bash
terraform init
terraform validate
```

### 2.3 Plan and Apply

```bash
# Review plan
terraform plan -out=tfplan

# Apply (creates all infrastructure)
terraform apply tfplan
```

**Created Resources**:
- Artifact Registry repository
- Service accounts (API, Worker, CI)
- Secret Manager secrets
- Cloud Run services (placeholder images)
- IAM bindings

**Outputs**:
```
artifact_registry_url = "us-central1-docker.pkg.dev/heimdex-prod/heimdex"
api_cloud_run_url     = "https://heimdex-api-prod-xxx.run.app"
ci_service_account_email = "heimdex-ci-prod@heimdex-prod.iam.gserviceaccount.com"
```

## Step 3: Set Up Workload Identity Federation

Workload Identity Federation (WIF) allows GitHub Actions to authenticate to GCP without long-lived service account keys.

### 3.1 Create Workload Identity Pool

```bash
export PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
export POOL_NAME="github-actions-pool"
export PROVIDER_NAME="github-provider"
export REPO="your-github-username/heimdex"

# Create pool
gcloud iam workload-identity-pools create $POOL_NAME \
  --project=$PROJECT_ID \
  --location=global \
  --display-name="GitHub Actions Pool"

# Create provider
gcloud iam workload-identity-pools providers create-oidc $PROVIDER_NAME \
  --project=$PROJECT_ID \
  --location=global \
  --workload-identity-pool=$POOL_NAME \
  --display-name="GitHub Provider" \
  --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository" \
  --issuer-uri="https://token.actions.githubusercontent.com"
```

### 3.2 Grant Service Account Impersonation

```bash
export CI_SA="heimdex-ci-prod@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud iam service-accounts add-iam-policy-binding $CI_SA \
  --project=$PROJECT_ID \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_NAME}/attribute.repository/${REPO}"
```

### 3.3 Get Workload Identity Provider

```bash
gcloud iam workload-identity-pools providers describe $PROVIDER_NAME \
  --project=$PROJECT_ID \
  --location=global \
  --workload-identity-pool=$POOL_NAME \
  --format='value(name)'
```

**Output** (save for GitHub secrets):
```
projects/123456789/locations/global/workloadIdentityPools/github-actions-pool/providers/github-provider
```

## Step 4: Configure GitHub Secrets

Add the following secrets to your GitHub repository (Settings → Secrets and variables → Actions):

| Secret Name | Value | Description |
|-------------|-------|-------------|
| `GCP_PROJECT_ID` | `heimdex-prod` | GCP project ID |
| `WIF_PROVIDER` | `projects/.../providers/github-provider` | Workload Identity Provider (from step 3.3) |
| `WIF_SERVICE_ACCOUNT` | `heimdex-ci-prod@...iam.gserviceaccount.com` | CI service account email |
| `DEV_JWT_SECRET` | Strong random string | JWT secret for dev mode (32+ chars) |

**Generate strong secret**:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

## Step 5: Build and Push Images

### 5.1 Manual Build (First Time)

```bash
# Authenticate to Artifact Registry
gcloud auth configure-docker ${REGION}-docker.pkg.dev

# Build API image
docker build -t ${REGION}-docker.pkg.dev/${PROJECT_ID}/heimdex/api:latest \
  -f apps/api/Dockerfile .

# Build Worker image
docker build -t ${REGION}-docker.pkg.dev/${PROJECT_ID}/heimdex/worker:latest \
  -f apps/worker/Dockerfile .

# Push images
docker push ${REGION}-docker.pkg.dev/${PROJECT_ID}/heimdex/api:latest
docker push ${REGION}-docker.pkg.dev/${PROJECT_ID}/heimdex/worker:latest
```

### 5.2 Automated Build via GitHub Actions

Trigger the build workflow manually:

1. Go to **Actions** tab in GitHub
2. Select **Build and Push** workflow
3. Click **Run workflow**
4. Select environment (dev/staging/prod)
5. Optionally specify a tag (defaults to git SHA)

The workflow will:
- Build Docker images
- Scan for vulnerabilities (fails on CRITICAL/HIGH)
- Push to Artifact Registry
- Output image digests

## Step 6: Configure External Services

Heimdex requires PostgreSQL and Redis. You can use:

### Option A: Supabase (Recommended for MVP)

**PostgreSQL**:
1. Create Supabase project at https://supabase.com
2. Get connection string from Settings → Database
3. Add to Cloud Run via Secret Manager:

```bash
echo -n "postgresql://user:pass@host:5432/db" | \
  gcloud secrets create postgres-url --data-file=-

# Grant API/Worker access
for SA in api worker; do
  gcloud secrets add-iam-policy-binding postgres-url \
    --member="serviceAccount:heimdex-${SA}-prod@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"
done
```

**Redis**: Use Upstash (https://upstash.com) or similar

### Option B: Cloud SQL + Memorystore

Enable in Terraform:
```hcl
enable_cloudsql = true
enable_redis    = true
enable_vpc_connector = true  # Required for private access
```

**Cost Warning**: Cloud SQL (~$10-50/month) + Memorystore (~$30/month)

## Step 7: Update Cloud Run Environment

Add secrets to Cloud Run services:

```bash
# Update API service
gcloud run services update heimdex-api-prod \
  --region=$REGION \
  --update-env-vars="HEIMDEX_ENV=prod,AUTH_PROVIDER=dev" \
  --update-secrets="PGHOST=postgres-url:latest,REDIS_URL=redis-url:latest,DEV_JWT_SECRET=dev-jwt-secret-prod:latest"

# Update Worker service
gcloud run services update heimdex-worker-prod \
  --region=$REGION \
  --update-env-vars="HEIMDEX_ENV=prod" \
  --update-secrets="PGHOST=postgres-url:latest,REDIS_URL=redis-url:latest"
```

## Step 8: Run Database Migrations

```bash
# From local machine (requires VPN or public access to DB)
cd packages/common

# Set connection string
export PGHOST=your-postgres-host
export PGUSER=postgres
export PGPASSWORD=your-password
export PGDATABASE=heimdex

# Run migrations
alembic upgrade head
```

**For Cloud SQL**: Use Cloud SQL Proxy for secure access

## Step 9: Verify Deployment

### 9.1 Check Service Health

```bash
# Get API URL
export API_URL=$(gcloud run services describe heimdex-api-prod \
  --region=$REGION --format='value(status.url)')

# Check liveness
curl $API_URL/healthz | jq

# Check readiness (will fail if DB/Redis not configured)
curl $API_URL/readyz | jq
```

### 9.2 Test Authenticated Request

```bash
# Generate dev token (for testing only!)
export TOKEN=$(python3 -c "
from heimdex_common.auth import create_dev_token
print(create_dev_token('test-user', 'test-org'))
")

# Create job
curl -X POST $API_URL/jobs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"type": "mock_process"}' | jq
```

## Step 10: Set Up Custom Domain (Optional)

### 10.1 Map Domain to Cloud Run

```bash
gcloud run domain-mappings create \
  --service=heimdex-api-prod \
  --domain=api.heimdex.example.com \
  --region=$REGION
```

### 10.2 Configure DNS

Add the provided DNS records to your domain registrar.

## Monitoring and Logging

### Cloud Logging

View logs:
```bash
# API logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=heimdex-api-prod" \
  --limit=50 --format=json

# Filter by level
gcloud logging read "resource.type=cloud_run_revision AND jsonPayload.level=ERROR" \
  --limit=50
```

### Cloud Monitoring

Create alerts for:
- High error rates (>5% HTTP 5xx)
- Cold starts (>500ms startup)
- Memory usage (>80%)

## Cost Optimization

### Free Tier Limits

Cloud Run free tier per month:
- 2 million requests
- 360,000 GB-seconds memory
- 180,000 vCPU-seconds

**Estimate** (scale-to-zero with low traffic):
- API: ~$5/month
- Worker: ~$2/month
- Artifact Registry: ~$1/month
- **Total**: ~$8/month

### Cost Reduction Tips

1. **Scale-to-zero**: Set `min_instances=0` for dev/staging
2. **Right-size resources**: Start with 512MB RAM, 1 vCPU
3. **Use external DB**: Supabase free tier > Cloud SQL
4. **Delete old images**: Set retention policy on Artifact Registry

## Rollback

### To Previous Image

```bash
# List revisions
gcloud run revisions list --service=heimdex-api-prod --region=$REGION

# Route 100% traffic to previous revision
gcloud run services update-traffic heimdex-api-prod \
  --region=$REGION \
  --to-revisions=heimdex-api-prod-00002-abc=100
```

### Terraform Rollback

```bash
# Revert terraform.tfstate to previous version
git checkout HEAD~1 infra/terraform/terraform.tfstate

# Apply previous state
terraform apply
```

## Troubleshooting

### "Permission denied" errors

**Cause**: Service account lacks required IAM roles

**Solution**: Check IAM bindings in Terraform

### Images not updating

**Cause**: Cloud Run caches images

**Solution**: Use explicit tags (not `latest`) or redeploy:
```bash
gcloud run services update heimdex-api-prod --region=$REGION
```

### Database connection failures

**Cause**: Incorrect connection string or network access

**Solution**:
1. Check `PGHOST` secret value
2. Verify database allows connections from Cloud Run IPs
3. Use Cloud SQL Proxy if using Cloud SQL

## Next Steps

- [ ] Enable Cloud SQL and migrate from Supabase
- [ ] Set up Cloud Armor for DDoS protection
- [ ] Configure Cloud CDN for static assets
- [ ] Implement multi-region deployment
- [ ] Set up automated backups

## References

- [Cloud Run Documentation](https://cloud.google.com/run/docs)
- [Workload Identity Federation](https://cloud.google.com/iam/docs/workload-identity-federation)
- [Terraform Google Provider](https://registry.terraform.io/providers/hashicorp/google/latest/docs)
