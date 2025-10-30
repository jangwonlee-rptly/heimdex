output "artifact_registry_repository" {
  description = "Artifact Registry repository for Docker images"
  value       = google_artifact_registry_repository.heimdex.name
}

output "artifact_registry_url" {
  description = "Full URL for pushing Docker images"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${var.artifact_repo}"
}

output "api_service_account_email" {
  description = "Email of the API service account"
  value       = google_service_account.api.email
}

output "worker_service_account_email" {
  description = "Email of the Worker service account"
  value       = google_service_account.worker.email
}

output "ci_service_account_email" {
  description = "Email of the CI/CD service account"
  value       = google_service_account.ci.email
}

output "api_cloud_run_url" {
  description = "URL of the API Cloud Run service"
  value       = google_cloud_run_v2_service.api.uri
}

output "worker_cloud_run_url" {
  description = "URL of the Worker Cloud Run service"
  value       = google_cloud_run_v2_service.worker.uri
}

output "secret_dev_jwt_id" {
  description = "ID of the dev JWT secret in Secret Manager"
  value       = google_secret_manager_secret.dev_jwt_secret.secret_id
}
