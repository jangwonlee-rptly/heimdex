# Enable required APIs
resource "google_project_service" "apis" {
  for_each = toset([
    "artifactregistry.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "compute.googleapis.com",
    "iam.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
  ])

  service            = each.key
  disable_on_destroy = false
}

# Artifact Registry for Docker images
resource "google_artifact_registry_repository" "heimdex" {
  location      = var.region
  repository_id = var.artifact_repo
  description   = "Docker images for Heimdex services"
  format        = "DOCKER"

  depends_on = [google_project_service.apis]
}

# Service Accounts
resource "google_service_account" "api" {
  account_id   = "heimdex-api-${var.environment}"
  display_name = "Heimdex API Service Account (${var.environment})"
  description  = "Service account for API Cloud Run service with least-privilege access"
}

resource "google_service_account" "worker" {
  account_id   = "heimdex-worker-${var.environment}"
  display_name = "Heimdex Worker Service Account (${var.environment})"
  description  = "Service account for Worker Cloud Run service with least-privilege access"
}

resource "google_service_account" "ci" {
  account_id   = "heimdex-ci-${var.environment}"
  display_name = "Heimdex CI/CD Service Account (${var.environment})"
  description  = "Service account for GitHub Actions with Workload Identity Federation"
}

# Secret Manager secrets
resource "google_secret_manager_secret" "dev_jwt_secret" {
  secret_id = "dev-jwt-secret-${var.environment}"

  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "dev_jwt_secret" {
  secret      = google_secret_manager_secret.dev_jwt_secret.id
  secret_data = var.dev_jwt_secret
}

# IAM: API service account → Secret Manager reader (scoped)
resource "google_secret_manager_secret_iam_member" "api_dev_jwt_secret" {
  secret_id = google_secret_manager_secret.dev_jwt_secret.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.api.email}"
}

# IAM: CI service account → Artifact Registry writer
resource "google_artifact_registry_repository_iam_member" "ci_writer" {
  location   = google_artifact_registry_repository.heimdex.location
  repository = google_artifact_registry_repository.heimdex.name
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.ci.email}"
}

# IAM: CI service account → Cloud Run admin (for deployments)
resource "google_project_iam_member" "ci_run_admin" {
  project = var.project_id
  role    = "roles/run.admin"
  member  = "serviceAccount:${google_service_account.ci.email}"
}

# IAM: CI service account → Service Account User (to deploy as API/Worker SAs)
resource "google_project_iam_member" "ci_sa_user" {
  project = var.project_id
  role    = "roles/iam.serviceAccountUser"
  member  = "serviceAccount:${google_service_account.ci.email}"
}

# Cloud Run: API Service
resource "google_cloud_run_v2_service" "api" {
  name     = "heimdex-api-${var.environment}"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"

  template {
    service_account = google_service_account.api.email

    scaling {
      min_instance_count = var.api_min_instances
      max_instance_count = 10
    }

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/${var.artifact_repo}/api:${var.api_image_tag}"

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
        cpu_idle          = true
        startup_cpu_boost = false
      }

      env {
        name  = "HEIMDEX_ENV"
        value = var.environment
      }

      env {
        name  = "AUTH_PROVIDER"
        value = "dev"
      }

      env {
        name = "DEV_JWT_SECRET"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.dev_jwt_secret.secret_id
            version = "latest"
          }
        }
      }

      # Placeholder env vars (override via Secret Manager in production)
      env {
        name  = "PGHOST"
        value = "localhost"
      }

      env {
        name  = "REDIS_URL"
        value = "redis://localhost:6379/0"
      }

      startup_probe {
        http_get {
          path = "/healthz"
        }
        initial_delay_seconds = 5
        timeout_seconds       = 2
        period_seconds        = 3
        failure_threshold     = 3
      }

      liveness_probe {
        http_get {
          path = "/healthz"
        }
        initial_delay_seconds = 10
        timeout_seconds       = 2
        period_seconds        = 10
        failure_threshold     = 3
      }
    }

    # Security context
    containers {
      name = "api"
    }
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  depends_on = [
    google_project_service.apis,
    google_secret_manager_secret_version.dev_jwt_secret,
  ]
}

# Cloud Run: Worker Service
resource "google_cloud_run_v2_service" "worker" {
  name     = "heimdex-worker-${var.environment}"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_ONLY"

  template {
    service_account = google_service_account.worker.email

    scaling {
      min_instance_count = var.worker_min_instances
      max_instance_count = 5
    }

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/${var.artifact_repo}/worker:${var.worker_image_tag}"

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
        cpu_idle          = false
        startup_cpu_boost = false
      }

      env {
        name  = "HEIMDEX_ENV"
        value = var.environment
      }

      # Placeholder env vars
      env {
        name  = "PGHOST"
        value = "localhost"
      }

      env {
        name  = "REDIS_URL"
        value = "redis://localhost:6379/0"
      }
    }
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  depends_on = [google_project_service.apis]
}
