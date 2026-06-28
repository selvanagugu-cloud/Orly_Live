output "bigquery_dataset"    { value = google_bigquery_dataset.paris_orly.dataset_id }
output "pubsub_topic"        { value = google_pubsub_topic.orly_flights.name }
output "pubsub_subscription" { value = google_pubsub_subscription.orly_flights_sub.name }
output "service_account"     { value = google_service_account.orly_app.email }
