# ============================================
# Input Variables
# ============================================

# ====== Required ======

variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "gemini_api_key" {
  description = "Google Gemini API key for receipt OCR"
  type        = string
  sensitive   = true
}

variable "gemini_model" {
  description = "Gemini model name for receipt OCR (e.g., gemini-2.0-flash)"
  type        = string
  default     = "gemini-2.0-flash"
}

variable "gemini_daily_limit" {
  description = "Max Gemini API calls per day (0 = unlimited)"
  type        = number
  default     = 100
}

# ====== Region / Zone ======

variable "region" {
  description = "GCP region for all resources"
  type        = string
  default     = "europe-west1"
}

# ====== Cloud Run ======

variable "min_instances" {
  description = "Minimum Cloud Run instances (0 = scale to zero)"
  type        = number
  default     = 0
}

variable "max_instances" {
  description = "Maximum Cloud Run instances"
  type        = number
  default     = 5
}

variable "cpu" {
  description = "CPU allocation per instance (e.g., '1' or '2')"
  type        = string
  default     = "1"
}

variable "memory" {
  description = "Memory allocation per instance"
  type        = string
  default     = "512Mi"
}

variable "workers" {
  description = "Number of gunicorn workers per instance"
  type        = number
  default     = 2
}

# ====== Cloud SQL ======

variable "db_tier" {
  description = "Cloud SQL machine tier"
  type        = string
  default     = "db-f1-micro"  # Cheapest tier for starting out
}

variable "db_disk_size_gb" {
  description = "Cloud SQL disk size in GB"
  type        = number
  default     = 10
}

variable "db_ha" {
  description = "Enable high availability for Cloud SQL"
  type        = bool
  default     = false
}

# ====== Networking & Security ======

variable "cors_origins" {
  description = "Allowed CORS origins"
  type        = list(string)
  default     = ["*"]
}

variable "domain" {
  description = "Custom domain to map to Cloud Run (leave empty to skip)"
  type        = string
  default     = ""
}

# ====== Logging ======

variable "log_level" {
  description = "Application log level"
  type        = string
  default     = "INFO"
}

# ====== Flags ======

variable "deletion_protection" {
  description = "Prevent accidental deletion of Cloud SQL"
  type        = bool
  default     = true
}

variable "create_tfstate_bucket" {
  description = "Create a GCS bucket for Terraform remote state"
  type        = bool
  default     = false
}
