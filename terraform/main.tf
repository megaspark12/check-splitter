# ============================================
# Check Splitter — Terraform Infrastructure
# ============================================
# Provisions all GCP resources for production deployment

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.5"
    }
  }

  # ====== Remote Backend (GCS) ======
  # To enable remote state storage:
  #   1. Run: terraform apply -var='create_tfstate_bucket=true'
  #   2. Run: make tf-enable-remote-state
  #      (or manually: terraform output tfstate_bucket, then uncomment below
  #       with the bucket name, then terraform init -migrate-state)
  #   3. Commit the uncommented backend block.
  #
  # backend "gcs" {
  #   bucket = "<YOUR_TFSTATE_BUCKET_NAME>"
  #   prefix = "terraform/state"
  # }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}

# ====== Enable Required APIs ======

resource "google_project_service" "apis" {
  for_each = toset([
    "run.googleapis.com",
    "sqladmin.googleapis.com",
    "secretmanager.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "vpcaccess.googleapis.com",
    "compute.googleapis.com",
    "storage.googleapis.com",
    "iam.googleapis.com",
  ])

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

# ====== Random suffix for unique resource names ======

resource "random_id" "suffix" {
  byte_length = 4
}

# ====== Artifact Registry ======

resource "google_artifact_registry_repository" "app" {
  depends_on = [google_project_service.apis]

  location      = var.region
  repository_id = "check-splitter"
  description   = "Docker images for Check Splitter"
  format        = "DOCKER"

  cleanup_policies {
    id     = "keep-recent"
    action = "KEEP"

    most_recent_versions {
      keep_count = 5
    }
  }
}

# ====== Cloud SQL (PostgreSQL) ======

resource "google_sql_database_instance" "main" {
  depends_on = [
    google_project_service.apis,
    google_service_networking_connection.private_vpc,
  ]

  name             = "check-splitter-${random_id.suffix.hex}"
  database_version = "POSTGRES_15"
  region           = var.region

  settings {
    tier              = var.db_tier
    availability_type = var.db_ha ? "REGIONAL" : "ZONAL"
    disk_size         = var.db_disk_size_gb
    disk_autoresize   = true

    database_flags {
      name  = "max_connections"
      value = "100"
    }

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
      start_time                     = "03:00"  # 3 AM UTC
    }

    ip_configuration {
      ipv4_enabled    = false  # No public IP
      private_network = google_compute_network.vpc.id
    }

    maintenance_window {
      day          = 7  # Sunday
      hour         = 4  # 4 AM UTC
      update_track = "stable"
    }
  }

  deletion_protection = var.deletion_protection
}

resource "google_sql_database" "app" {
  name     = "check_splitter"
  instance = google_sql_database_instance.main.name
}

resource "random_password" "db_password" {
  length  = 32
  special = false
}

resource "google_sql_user" "app" {
  name     = "app"
  instance = google_sql_database_instance.main.name
  password = random_password.db_password.result
}

# ====== VPC Network ======

resource "google_compute_network" "vpc" {
  depends_on = [google_project_service.apis]

  name                    = "check-splitter-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "main" {
  name          = "check-splitter-subnet"
  ip_cidr_range = "10.0.0.0/24"
  region        = var.region
  network       = google_compute_network.vpc.id
}

resource "google_compute_global_address" "private_ip" {
  name          = "check-splitter-private-ip"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.vpc.id
}

resource "google_service_networking_connection" "private_vpc" {
  network                 = google_compute_network.vpc.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_ip.name]
}

# VPC Connector for Cloud Run → Cloud SQL
resource "google_vpc_access_connector" "connector" {
  depends_on = [google_project_service.apis]

  name          = "check-splitter-conn"
  region        = var.region
  network       = google_compute_network.vpc.name
  ip_cidr_range = "10.8.0.0/28"
  min_instances = 2
  max_instances = 3

  machine_type = "e2-micro"
}

# ====== Cloud Storage (Receipt Images) ======

resource "google_storage_bucket" "receipts" {
  depends_on = [google_project_service.apis]

  name     = "check-splitter-receipts-${random_id.suffix.hex}"
  location = var.region

  uniform_bucket_level_access = true

  lifecycle_rule {
    condition {
      age = 30  # Auto-delete after 30 days
    }
    action {
      type = "Delete"
    }
  }

  cors {
    origin          = var.cors_origins
    method          = ["GET", "PUT"]
    response_header = ["Content-Type"]
    max_age_seconds = 3600
  }
}

# ====== Secret Manager ======

resource "google_secret_manager_secret" "gemini_key" {
  depends_on = [google_project_service.apis]

  secret_id = "gemini-api-key"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "gemini_key" {
  secret      = google_secret_manager_secret.gemini_key.id
  secret_data = var.gemini_api_key
}

resource "google_secret_manager_secret" "secret_key" {
  depends_on = [google_project_service.apis]

  secret_id = "app-secret-key"

  replication {
    auto {}
  }
}

resource "random_password" "secret_key" {
  length  = 64
  special = false
}

resource "google_secret_manager_secret_version" "secret_key" {
  secret      = google_secret_manager_secret.secret_key.id
  secret_data = random_password.secret_key.result
}

resource "google_secret_manager_secret" "db_password" {
  depends_on = [google_project_service.apis]

  secret_id = "db-password"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "db_password" {
  secret      = google_secret_manager_secret.db_password.id
  secret_data = random_password.db_password.result
}

# ====== Service Account for Cloud Run ======

resource "google_service_account" "cloud_run" {
  account_id   = "check-splitter-run"
  display_name = "Check Splitter Cloud Run"
}

# Grant Cloud Run SA access to secrets
resource "google_secret_manager_secret_iam_member" "gemini_key_access" {
  secret_id = google_secret_manager_secret.gemini_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.cloud_run.email}"
}

resource "google_secret_manager_secret_iam_member" "secret_key_access" {
  secret_id = google_secret_manager_secret.secret_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.cloud_run.email}"
}

resource "google_secret_manager_secret_iam_member" "db_password_access" {
  secret_id = google_secret_manager_secret.db_password.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.cloud_run.email}"
}

# Grant Cloud Run SA access to Cloud SQL
resource "google_project_iam_member" "cloud_sql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.cloud_run.email}"
}

# Grant Cloud Run SA access to GCS bucket
resource "google_storage_bucket_iam_member" "receipts_access" {
  bucket = google_storage_bucket.receipts.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.cloud_run.email}"
}

# ====== Cloud Run Service ======

resource "google_cloud_run_v2_service" "app" {
  depends_on = [
    google_project_service.apis,
    google_secret_manager_secret_version.gemini_key,
    google_secret_manager_secret_version.secret_key,
    google_secret_manager_secret_version.db_password,
  ]

  name     = "check-splitter"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.cloud_run.email

    scaling {
      min_instance_count = var.min_instances
      max_instance_count = var.max_instances
    }

    vpc_access {
      connector = google_vpc_access_connector.connector.id
      egress    = "PRIVATE_RANGES_ONLY"
    }

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/check-splitter/app:latest"

      ports {
        container_port = 8000
      }

      resources {
        limits = {
          cpu    = var.cpu
          memory = var.memory
        }
      }

      # Plain environment variables
      env {
        name  = "ENVIRONMENT"
        value = "production"
      }
      env {
        name  = "WORKERS"
        value = tostring(var.workers)
      }
      env {
        name  = "RUN_MIGRATIONS"
        value = "true"
      }
      env {
        name  = "STORAGE_BACKEND"
        value = "gcs"
      }
      env {
        name  = "GCS_BUCKET_NAME"
        value = google_storage_bucket.receipts.name
      }
      env {
        name  = "INSTANCE_CONNECTION_NAME"
        value = google_sql_database_instance.main.connection_name
      }
      env {
        name  = "DB_USER"
        value = google_sql_user.app.name
      }
      env {
        name  = "DB_NAME"
        value = google_sql_database.app.name
      }
      env {
        name  = "LOG_FORMAT"
        value = "json"
      }
      env {
        name  = "LOG_LEVEL"
        value = var.log_level
      }
      env {
        name = "CORS_ORIGINS"
        value = join(",", var.cors_origins)
      }
      env {
        name  = "GEMINI_MODEL"
        value = var.gemini_model
      }
      env {
        name  = "GEMINI_DAILY_LIMIT"
        value = tostring(var.gemini_daily_limit)
      }

      # Secrets from Secret Manager
      env {
        name = "GEMINI_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.gemini_key.secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "SECRET_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.secret_key.secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "DB_PASS"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.db_password.secret_id
            version = "latest"
          }
        }
      }

      # Startup probe
      startup_probe {
        http_get {
          path = "/health"
        }
        initial_delay_seconds = 5
        period_seconds        = 5
        failure_threshold     = 10
      }

      # Liveness probe
      liveness_probe {
        http_get {
          path = "/health"
        }
        period_seconds    = 30
        failure_threshold = 3
      }
    }

    # Cloud SQL connection
    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.main.connection_name]
      }
    }
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }
}

# Allow unauthenticated access (public web app)
resource "google_cloud_run_v2_service_iam_member" "public" {
  name     = google_cloud_run_v2_service.app.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# ====== Optional: Custom Domain Mapping ======

resource "google_cloud_run_domain_mapping" "custom" {
  count    = var.domain != "" ? 1 : 0
  name     = var.domain
  location = var.region

  metadata {
    namespace = var.project_id
  }

  spec {
    route_name = google_cloud_run_v2_service.app.name
  }
}

# ====== Terraform State Bucket (bootstrap) ======

resource "google_storage_bucket" "tfstate" {
  count = var.create_tfstate_bucket ? 1 : 0

  name     = "check-splitter-tfstate-${random_id.suffix.hex}"
  location = var.region

  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      num_newer_versions = 5
    }
    action {
      type = "Delete"
    }
  }
}

# ====== GitHub Actions — Workload Identity Federation ======

resource "google_iam_workload_identity_pool" "github" {
  count = var.github_repo != "" ? 1 : 0

  workload_identity_pool_id = "github-actions"
  display_name              = "GitHub Actions"
  description               = "OIDC pool for GitHub Actions CI/CD"
  project                   = var.project_id
}

resource "google_iam_workload_identity_pool_provider" "github" {
  count = var.github_repo != "" ? 1 : 0

  workload_identity_pool_id          = google_iam_workload_identity_pool.github[0].workload_identity_pool_id
  workload_identity_pool_provider_id = "github-oidc"
  display_name                       = "GitHub OIDC"

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.actor"      = "assertion.actor"
    "attribute.repository" = "assertion.repository"
  }

  attribute_condition = "assertion.repository == '${var.github_repo}'"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

# Deployer service account for GitHub Actions
resource "google_service_account" "github_deployer" {
  count = var.github_repo != "" ? 1 : 0

  account_id   = "github-actions-deployer"
  display_name = "GitHub Actions Deployer"
}

# Allow GitHub Actions to impersonate the deployer SA
resource "google_service_account_iam_member" "github_wif" {
  count = var.github_repo != "" ? 1 : 0

  service_account_id = google_service_account.github_deployer[0].name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github[0].name}/attribute.repository/${var.github_repo}"
}

# Deployer needs to push to Artifact Registry
resource "google_artifact_registry_repository_iam_member" "github_deployer" {
  count = var.github_repo != "" ? 1 : 0

  repository = google_artifact_registry_repository.app.name
  location   = var.region
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.github_deployer[0].email}"
}

# Deployer needs to deploy to Cloud Run
resource "google_project_iam_member" "github_deployer_run" {
  count = var.github_repo != "" ? 1 : 0

  project = var.project_id
  role    = "roles/run.developer"
  member  = "serviceAccount:${google_service_account.github_deployer[0].email}"
}

# Deployer needs to act as the Cloud Run service account
resource "google_service_account_iam_member" "github_deployer_act_as" {
  count = var.github_repo != "" ? 1 : 0

  service_account_id = google_service_account.cloud_run.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.github_deployer[0].email}"
}
