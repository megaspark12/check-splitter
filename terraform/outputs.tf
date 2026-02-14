# ============================================
# Outputs
# ============================================

output "cloud_run_url" {
  description = "URL of the deployed Cloud Run service"
  value       = google_cloud_run_v2_service.app.uri
}

output "cloud_sql_connection_name" {
  description = "Cloud SQL instance connection name"
  value       = google_sql_database_instance.main.connection_name
}

output "gcs_bucket_name" {
  description = "GCS bucket name for receipt images"
  value       = google_storage_bucket.receipts.name
}

output "artifact_registry_url" {
  description = "Artifact Registry Docker URL"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/check-splitter"
}

output "service_account_email" {
  description = "Cloud Run service account email"
  value       = google_service_account.cloud_run.email
}

output "db_instance_name" {
  description = "Cloud SQL instance name"
  value       = google_sql_database_instance.main.name
}

output "tfstate_bucket" {
  description = "Terraform state bucket name (if created)"
  value       = var.create_tfstate_bucket ? google_storage_bucket.tfstate[0].name : "N/A (not created)"
}

# ====== GitHub Actions WIF ======

output "wif_provider" {
  description = "Workload Identity Federation provider resource name (set as WIF_PROVIDER secret in GitHub)"
  value       = var.github_repo != "" ? google_iam_workload_identity_pool_provider.github[0].name : "N/A (github_repo not set)"
}

output "wif_service_account" {
  description = "GitHub Actions deployer service account email (set as WIF_SERVICE_ACCOUNT secret in GitHub)"
  value       = var.github_repo != "" ? google_service_account.github_deployer[0].email : "N/A (github_repo not set)"
}
