# SustainAI Terraform Configuration
# Minimal Cloud Run + GCS + Service Account for demo deployment
#
# Usage:
#   terraform init
#   terraform plan -var="project_id=YOUR_GCP_PROJECT"
#   terraform apply -var="project_id=YOUR_GCP_PROJECT"
#   terraform destroy -var="project_id=YOUR_GCP_PROJECT"
#
# Standing cost after destroy: $0. All resources are deleted.

terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region for deployment"
  type        = string
  default     = "us-central1"
}

variable "image" {
  description = "Container image URI (e.g. gcr.io/PROJECT/sustainai:latest)"
  type        = string
  default     = ""
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# Service account with least privilege
resource "google_service_account" "sustainai" {
  account_id   = "sustainai-runner"
  display_name = "SustainAI Cloud Run Service Account"
}

# Vertex AI user role (invoke only)
resource "google_project_iam_member" "vertex_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.sustainai.email}"
}

# GCS bucket for artifacts
resource "google_storage_bucket" "artifacts" {
  name          = "${var.project_id}-sustainai-artifacts"
  location      = var.region
  force_destroy = true

  uniform_bucket_level_access = true
}

# GCS read/write for the service account (one bucket only)
resource "google_storage_bucket_iam_member" "artifacts_rw" {
  bucket = google_storage_bucket.artifacts.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.sustainai.email}"
}

# Cloud Run service
resource "google_cloud_run_v2_service" "sustainai" {
  name     = "sustainai"
  location = var.region

  template {
    service_account = google_service_account.sustainai.email

    containers {
      image = var.image != "" ? var.image : "gcr.io/${var.project_id}/sustainai:latest"

      ports {
        container_port = 8000
      }

      env {
        name  = "GCP_PROJECT"
        value = var.project_id
      }
      env {
        name  = "VERTEX_LOCATION"
        value = var.region
      }
      env {
        name  = "AGENT_MODE"
        value = "live"
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
      }
    }

    scaling {
      min_instance_count = 0
      max_instance_count = 1
    }
  }
}

# Allow unauthenticated access for demo
resource "google_cloud_run_v2_service_iam_member" "public" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.sustainai.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

output "service_url" {
  value = google_cloud_run_v2_service.sustainai.uri
}

output "bucket_name" {
  value = google_storage_bucket.artifacts.name
}
