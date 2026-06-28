variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "region" {
  description = "GCP region — europe-west1 for EU data residency"
  type        = string
  default     = "europe-west1"
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be dev, staging, or prod."
  }
}

variable "pubsub_retention_seconds" {
  description = "How long Pub/Sub retains undelivered messages (seconds)"
  type        = number
  default     = 3600

  validation {
    condition     = var.pubsub_retention_seconds >= 600 && var.pubsub_retention_seconds <= 604800
    error_message = "retention must be between 600s (10min) and 604800s (7 days)."
  }
}

variable "bq_location" {
  description = "BigQuery dataset location"
  type        = string
  default     = "EU"
}

variable "alert_email" {
  description = "Email for budget and monitoring alerts (optional)"
  type        = string
  default     = ""
}
