variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region for resources"
  type        = string
  default     = "us-central1"
}

variable "artifact_repo" {
  description = "Artifact Registry repository name"
  type        = string
  default     = "heimdex"
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)"
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be dev, staging, or prod"
  }
}

variable "enable_cloudsql" {
  description = "Enable Cloud SQL PostgreSQL instance (disabled by default for cost)"
  type        = bool
  default     = false
}

variable "enable_redis" {
  description = "Enable Memorystore Redis instance (disabled by default for cost)"
  type        = bool
  default     = false
}

variable "enable_vpc_connector" {
  description = "Enable VPC Connector for serverless access to private resources"
  type        = bool
  default     = false
}

variable "dev_jwt_secret" {
  description = "JWT secret for dev auth mode (stored in Secret Manager)"
  type        = string
  default     = "local-dev-secret"
  sensitive   = true
}

variable "api_image_tag" {
  description = "Docker image tag for API service"
  type        = string
  default     = "latest"
}

variable "worker_image_tag" {
  description = "Docker image tag for Worker service"
  type        = string
  default     = "latest"
}

variable "api_min_instances" {
  description = "Minimum number of API instances (0 for scale-to-zero)"
  type        = number
  default     = 0
}

variable "worker_min_instances" {
  description = "Minimum number of Worker instances (0 for scale-to-zero)"
  type        = number
  default     = 0
}

variable "api_max_instances" {
  description = "Maximum number of API instances"
  type        = number
  default     = 10
}

variable "worker_max_instances" {
  description = "Maximum number of Worker instances"
  type        = number
  default     = 5
}

variable "api_cpu_limit" {
  description = "CPU limit for API service (e.g., '1', '2', '4')"
  type        = string
  default     = "1"
}

variable "api_memory_limit" {
  description = "Memory limit for API service (e.g., '512Mi', '1Gi', '2Gi')"
  type        = string
  default     = "512Mi"
}

variable "worker_cpu_limit" {
  description = "CPU limit for Worker service (e.g., '1', '2', '4')"
  type        = string
  default     = "1"
}

variable "worker_memory_limit" {
  description = "Memory limit for Worker service (e.g., '512Mi', '1Gi', '2Gi')"
  type        = string
  default     = "1Gi"
}

variable "auth_provider" {
  description = "Authentication provider (dev for local/staging, supabase for production)"
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "supabase"], var.auth_provider)
    error_message = "auth_provider must be 'dev' or 'supabase'"
  }

  validation {
    condition     = !(var.environment == "prod" && var.auth_provider == "dev")
    error_message = "Production environment (prod) requires auth_provider='supabase' for security. dev auth is not allowed in production."
  }
}

variable "supabase_project_url" {
  description = "Supabase project URL (required when auth_provider=supabase)"
  type        = string
  default     = null
}

variable "supabase_jwks_url" {
  description = "Supabase JWKS URL for JWT verification (required when auth_provider=supabase)"
  type        = string
  default     = null
}

variable "auth_issuer" {
  description = "Expected JWT issuer claim (required when auth_provider=supabase)"
  type        = string
  default     = null
}

variable "auth_audience" {
  description = "Expected JWT audience claim (optional but recommended when auth_provider=supabase)"
  type        = string
  default     = null
}
