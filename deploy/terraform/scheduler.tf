# ============================================
# CLOUD SCHEDULER - TERRAFORM CONFIGURATION
# ============================================

# Service Account para Cloud Scheduler
resource "google_service_account" "etl_scheduler" {
  account_id   = "etl-scheduler"
  display_name = "ETL Scheduler Service Account"
  description  = "Service account for Cloud Scheduler to trigger ETL functions"
}

# IAM binding para invocar Cloud Functions
resource "google_project_iam_member" "scheduler_invoker" {
  project = var.project_id
  role    = "roles/cloudfunctions.invoker"
  member  = "serviceAccount:${google_service_account.etl_scheduler.email}"
}

# Cloud Scheduler Job - 12:00 AM (Medianoche)
resource "google_cloud_scheduler_job" "etl_midnight" {
  name        = "etl-midnight"
  description = "ETL execution at midnight (12:00 AM)"
  schedule    = "0 0 * * *"
  time_zone   = "America/Argentina/Buenos_Aires"
  region      = var.region

  http_target {
    uri         = "https://${var.region}-${var.project_id}.cloudfunctions.net/${var.function_name}"
    http_method = "POST"
    
    headers = {
      "Content-Type" = "application/json"
    }
    
    body = base64encode(jsonencode({
      incremental = true
      trigger     = "midnight"
    }))

    oidc_token {
      service_account_email = google_service_account.etl_scheduler.email
    }
  }

  depends_on = [google_service_account.etl_scheduler]
}

# Cloud Scheduler Job - 12:00 PM (Mediodía)
resource "google_cloud_scheduler_job" "etl_noon" {
  name        = "etl-noon"
  description = "ETL execution at noon (12:00 PM)"
  schedule    = "0 12 * * *"
  time_zone   = "America/Argentina/Buenos_Aires"
  region      = var.region

  http_target {
    uri         = "https://${var.region}-${var.project_id}.cloudfunctions.net/${var.function_name}"
    http_method = "POST"
    
    headers = {
      "Content-Type" = "application/json"
    }
    
    body = base64encode(jsonencode({
      incremental = true
      trigger     = "noon"
    }))

    oidc_token {
      service_account_email = google_service_account.etl_scheduler.email
    }
  }

  depends_on = [google_service_account.etl_scheduler]
}

# Cloud Scheduler Job - Carga completa semanal (Domingos 2:00 AM)
resource "google_cloud_scheduler_job" "etl_weekly_full" {
  name        = "etl-weekly-full"
  description = "Full ETL execution weekly on Sundays at 2:00 AM"
  schedule    = "0 2 * * 0"
  time_zone   = "America/Argentina/Buenos_Aires"
  region      = var.region

  http_target {
    uri         = "https://${var.region}-${var.project_id}.cloudfunctions.net/${var.function_name}"
    http_method = "POST"
    
    headers = {
      "Content-Type" = "application/json"
    }
    
    body = base64encode(jsonencode({
      incremental = false
      trigger     = "weekly-full"
    }))

    oidc_token {
      service_account_email = google_service_account.etl_scheduler.email
    }
  }

  depends_on = [google_service_account.etl_scheduler]
}