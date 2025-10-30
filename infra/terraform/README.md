# Heimdex Terraform Infrastructure

This directory contains Infrastructure-as-Code for deploying Heimdex to Google Cloud Platform.

## Prerequisites

- [Terraform](https://www.terraform.io/downloads.html) >= 1.5
- [tflint](https://github.com/terraform-linters/tflint) (for linting)
- [tfsec](https://github.com/aquasecurity/tfsec) (for security scanning)
- GCP project with billing enabled
- `gcloud` CLI authenticated

## Quick Start

1. **Copy the example variables file:**
   ```bash
   cp terraform.tfvars.example terraform.tfvars
   ```

2. **Edit `terraform.tfvars` with your values:**
   ```hcl
   project_id = "your-gcp-project-id"
   region     = "us-central1"
   environment = "dev"
   ```

3. **Initialize Terraform:**
   ```bash
   terraform init
   ```

4. **Validate configuration:**
   ```bash
   terraform validate
   tflint
   tfsec .
   ```

5. **Plan changes:**
   ```bash
   terraform plan -out=tfplan
   ```

6. **Apply (manual only):**
   ```bash
   terraform apply tfplan
   ```

## Architecture

The baseline infrastructure includes:

- **Artifact Registry**: Docker image repository
- **Service Accounts**: Separate SAs for API, Worker, and CI/CD with least-privilege IAM
- **Secret Manager**: Secure storage for dev JWT secret
- **Cloud Run**: Serverless containers for API and Worker (with placeholders)
- **IAM Bindings**: Scoped permissions for each service account

## Cost Optimization

By default, expensive resources are **disabled**:

- `enable_cloudsql = false` - Use external PostgreSQL or enable when ready
- `enable_redis = false` - Use external Redis or enable when ready
- `enable_vpc_connector = false` - Only needed for private VPC access
- `api_min_instances = 0` - Scale-to-zero for API
- `worker_min_instances = 0` - Scale-to-zero for Worker

## Security

- **No long-lived keys**: Uses Workload Identity Federation for GitHub Actions
- **Least-privilege IAM**: Each service account has minimal required permissions
- **Secret Manager**: Sensitive data stored securely, not in env vars
- **Container security**: Non-root, read-only filesystem (configured in Dockerfiles)
- **Network isolation**: Worker has internal-only ingress

## Workload Identity Federation

To set up GitHub Actions authentication:

1. Create a Workload Identity Pool and Provider (see `docs/deploy.md`)
2. Grant the CI service account impersonation rights
3. Configure GitHub Actions workflow with OIDC token

## Validation

Run all checks before committing:

```bash
terraform fmt -check
terraform validate
tflint
tfsec .
```

## State Management

Currently uses **local backend** for simplicity. For production:

1. Create a GCS bucket for state:
   ```bash
   gsutil mb -p your-project -l us-central1 gs://your-project-terraform-state
   ```

2. Enable versioning:
   ```bash
   gsutil versioning set on gs://your-project-terraform-state
   ```

3. Update `versions.tf`:
   ```hcl
   backend "gcs" {
     bucket = "your-project-terraform-state"
     prefix = "heimdex/dev"
   }
   ```

## Troubleshooting

### API not enabled
```
Error: Error enabling service: Permission denied
```
**Solution**: Enable required APIs manually or grant `roles/serviceusage.serviceUsageAdmin`

### Container not deployed
The baseline creates Cloud Run services with placeholder images. Actual deployment happens via CI/CD after images are built.

### Terraform state locked
```
Error: Error acquiring the state lock
```
**Solution**: With local backend, delete `.terraform/terraform.tfstate.lock.info`
