terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }

  # Uncomment for team use — stores state in GCS with locking
  # backend "gcs" {
  #   bucket = "your-project-tfstate"
  #   prefix = "orly-live/state"
  # }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

locals {
  labels = {
    project     = "orly-live"
    environment = var.environment
    managed-by  = "terraform"
  }
}

resource "google_bigquery_dataset" "paris_orly" {
  dataset_id    = "paris_orly"
  friendly_name = "Orly Live — Raw Data"
  description   = "Raw flight data for Paris Orly Airport (LFPO) via FlightRadar24"
  location      = var.bq_location
  labels        = local.labels

  # Prevent accidental deletion of the dataset and all its tables
  delete_contents_on_destroy = false
}

resource "google_bigquery_table" "raw_flights" {
  dataset_id          = google_bigquery_dataset.paris_orly.dataset_id
  table_id            = "raw_flights"
  deletion_protection = false
  description         = "Departures and arrivals from FlightRadar24 airport endpoint — one row per flight per poll"
  labels              = local.labels

  time_partitioning {
    type                     = "HOUR"
    field                    = "snapshot_time"
    # Subtlety: expiration_ms on partitions reduces storage cost
    # on historical data we no longer need for the live board
    expiration_ms = 604800000  # 7 days
  }

  # Cluster on the two most common filter columns
  # Ordering matters: put the highest-cardinality column last
  clustering = ["flight_type", "airline_icao"]

  schema = jsonencode([
    { name = "flight_number",      type = "STRING",    mode = "NULLABLE" },
    { name = "flight_type",        type = "STRING",    mode = "NULLABLE", description = "departure or arrival" },
    { name = "airline_name",       type = "STRING",    mode = "NULLABLE" },
    { name = "airline_icao",       type = "STRING",    mode = "NULLABLE" },
    { name = "airline_iata",       type = "STRING",    mode = "NULLABLE" },
    { name = "aircraft_code",      type = "STRING",    mode = "NULLABLE" },
    { name = "registration",       type = "STRING",    mode = "NULLABLE" },
    { name = "origin_iata",        type = "STRING",    mode = "NULLABLE" },
    { name = "origin_terminal",    type = "STRING",    mode = "NULLABLE" },
    { name = "origin_gate",        type = "STRING",    mode = "NULLABLE" },
    { name = "destination_iata",   type = "STRING",    mode = "NULLABLE" },
    { name = "dest_terminal",      type = "STRING",    mode = "NULLABLE" },
    { name = "dest_gate",          type = "STRING",    mode = "NULLABLE" },
    { name = "scheduled_departure",type = "TIMESTAMP", mode = "NULLABLE" },
    { name = "scheduled_arrival",  type = "TIMESTAMP", mode = "NULLABLE" },
    { name = "real_departure",     type = "TIMESTAMP", mode = "NULLABLE" },
    { name = "real_arrival",       type = "TIMESTAMP", mode = "NULLABLE" },
    { name = "estimated_departure",type = "TIMESTAMP", mode = "NULLABLE" },
    { name = "estimated_arrival",  type = "TIMESTAMP", mode = "NULLABLE" },
    { name = "status",             type = "STRING",    mode = "NULLABLE" },
    { name = "snapshot_time",      type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "pub_sub_message_id", type = "STRING",    mode = "NULLABLE" },
  ])
}

resource "google_bigquery_table" "flight_events" {
  dataset_id          = google_bigquery_dataset.paris_orly.dataset_id
  table_id            = "flight_events"
  deletion_protection = false
  description         = "Status change events: departed, landed, delayed, cancelled"
  labels              = local.labels

  time_partitioning {
    type          = "DAY"
    field         = "event_time"
    expiration_ms = 2592000000  # 30 days
  }

  clustering = ["event_type", "airline_icao"]

  schema = jsonencode([
    { name = "event_id",         type = "STRING",    mode = "REQUIRED" },
    { name = "flight_number",    type = "STRING",    mode = "NULLABLE" },
    { name = "flight_type",      type = "STRING",    mode = "NULLABLE" },
    { name = "airline_icao",     type = "STRING",    mode = "NULLABLE" },
    { name = "airline_name",     type = "STRING",    mode = "NULLABLE" },
    { name = "aircraft_code",    type = "STRING",    mode = "NULLABLE" },
    { name = "origin_iata",      type = "STRING",    mode = "NULLABLE" },
    { name = "destination_iata", type = "STRING",    mode = "NULLABLE" },
    { name = "event_type",       type = "STRING",    mode = "REQUIRED" },
    { name = "status_before",    type = "STRING",    mode = "NULLABLE" },
    { name = "status_after",     type = "STRING",    mode = "NULLABLE" },
    { name = "event_time",       type = "TIMESTAMP", mode = "REQUIRED" },
  ])
}

resource "google_pubsub_topic" "orly_flights" {
  name   = "orly-flights"
  labels = local.labels

  message_retention_duration = "${var.pubsub_retention_seconds}s"

  message_storage_policy {
    allowed_persistence_regions = ["europe-west1"]
  }
}

resource "google_pubsub_topic" "orly_flights_dlq" {
  name   = "orly-flights-dlq"
  labels = local.labels
}

resource "google_pubsub_subscription" "orly_flights_sub" {
  name   = "orly-flights-sub"
  topic  = google_pubsub_topic.orly_flights.name
  labels = local.labels

  ack_deadline_seconds       = 30
  message_retention_duration = "600s"

  retry_policy {
    minimum_backoff = "5s"
    maximum_backoff = "60s"
  }

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.orly_flights_dlq.id
    max_delivery_attempts = 3
  }

  expiration_policy {
    ttl = ""  # Never expire — keep subscription active
  }

  depends_on = [google_pubsub_topic.orly_flights_dlq]
}

resource "google_service_account" "orly_app" {
  account_id   = "orly-live-app"
  display_name = "Orly Live App"
  description  = "Least-privilege SA for poller, consumer and dashboard"
}

resource "google_project_iam_member" "app_pubsub_publisher" {
  project = var.project_id
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${google_service_account.orly_app.email}"
}

resource "google_project_iam_member" "app_pubsub_subscriber" {
  project = var.project_id
  role    = "roles/pubsub.subscriber"
  member  = "serviceAccount:${google_service_account.orly_app.email}"
}

resource "google_project_iam_member" "app_bq_editor" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${google_service_account.orly_app.email}"
}

resource "google_project_iam_member" "app_bq_jobs" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.orly_app.email}"
}
