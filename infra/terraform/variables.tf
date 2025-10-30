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
