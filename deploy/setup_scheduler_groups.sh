#!/bin/bash
# ============================================
# CLOUD SCHEDULER - HTTP TRIGGER (no Pub/Sub)
# ============================================
# Splits ETL into 5 groups. Cloud Scheduler calls the Cloud Function
# HTTP endpoint directly, avoiding Pub/Sub ack deadline redelivery.
#
# Groups (Mon-Sat, incremental; transactional groups lookback_days=5, catalogs/quantio=2):
#   Sunday catch-up jobs (lookback_days=8) exist separately: plex-etl-{heavy,medium,operational}-catchup
#   heavy_transactions  - factcabecera, factlineas, asientos, asientos_detalle
#   medium_transactions - factpagos, factcostos, factcoberturas, rec*, etc.
#   operational         - app*, pedidos, compras, clientes
#   catalogs            - stock, master data
#   quantio             - all 22 quantio tables
#
# Schedule: Mon-Sat only (Sunday reserved for full refresh - TBD)
#
# Usage:
#   ./deploy/setup_scheduler_groups.sh          # Create all jobs
#   ./deploy/setup_scheduler_groups.sh --delete  # Delete all jobs first, then create

set -e

PROJECT_ID="${GCP_PROJECT_ID:-plex-etl-project}"
REGION="us-central1"
TIMEZONE="America/Argentina/Buenos_Aires"
FUNCTION_URL="https://plex-etl-streaming-daily-uc6frd6lcq-uc.a.run.app"
SERVICE_ACCOUNT="etl-service-account@plex-etl-project.iam.gserviceaccount.com"

echo "🔧 Setting up Cloud Scheduler jobs (HTTP trigger) for project: $PROJECT_ID"

# ---- Step 0: Increase Cloud Run timeout to 3600s (1 hour) ----
echo ""
echo "⏱️  Updating Cloud Run service timeout to 3600s..."
gcloud run services update plex-etl-streaming-daily \
    --region=$REGION \
    --project=$PROJECT_ID \
    --timeout=3600 \
    --quiet 2>/dev/null && echo "   ✅ Cloud Run timeout updated to 3600s" \
    || echo "   ⚠️  Could not update Cloud Run timeout (may need manual update)"

# ---- Step 1: Optionally delete old jobs ----
if [ "$1" = "--delete" ]; then
    echo ""
    echo "🗑️  Deleting existing scheduler jobs..."
    for JOB in plex-etl-daily-incremental plex-etl-weekly-full-refresh \
                plex-etl-heavy-transactions plex-etl-medium-transactions \
                plex-etl-operational plex-etl-catalogs plex-etl-quantio; do
        gcloud scheduler jobs delete $JOB \
            --location=$REGION --project=$PROJECT_ID --quiet 2>/dev/null \
            && echo "   Deleted $JOB" || echo "   $JOB not found (skipping)"
    done
fi

# ---- Step 2: Create group scheduler jobs (HTTP trigger) ----
echo ""
echo "📅 Creating scheduler jobs (HTTP → Cloud Function)..."

# Group 1: Heavy transactions - 1:00 AM Argentina
echo "   Creating plex-etl-heavy-transactions (1:00 AM)..."
gcloud scheduler jobs create http plex-etl-heavy-transactions \
    --location=$REGION \
    --project=$PROJECT_ID \
    --schedule="0 1 * * 1-6" \
    --time-zone=$TIMEZONE \
    --uri="${FUNCTION_URL}" \
    --http-method=POST \
    --headers="Content-Type=application/json" \
    --message-body='{"lookback_days": 5, "force_full_refresh": false, "table_group": "heavy_transactions"}' \
    --oidc-service-account-email="${SERVICE_ACCOUNT}" \
    --attempt-deadline=1800s \
    --max-retry-attempts=3 \
    --min-backoff=60s \
    --description="ETL Group 1: factcabecera, factlineas, asientos, asientos_detalle (Mon-Sat)" \
    2>/dev/null && echo "   ✅ Created" || \
gcloud scheduler jobs update http plex-etl-heavy-transactions \
    --location=$REGION \
    --project=$PROJECT_ID \
    --schedule="0 1 * * 1-6" \
    --time-zone=$TIMEZONE \
    --uri="${FUNCTION_URL}" \
    --http-method=POST \
    --headers="Content-Type=application/json" \
    --message-body='{"lookback_days": 5, "force_full_refresh": false, "table_group": "heavy_transactions"}' \
    --oidc-service-account-email="${SERVICE_ACCOUNT}" \
    --attempt-deadline=1800s \
    --max-retry-attempts=3 \
    --min-backoff=60s \
    --description="ETL Group 1: factcabecera, factlineas, asientos, asientos_detalle (Mon-Sat)" \
    2>/dev/null && echo "   ✅ Updated"

# Group 2: Medium transactions - 1:20 AM Argentina
echo "   Creating plex-etl-medium-transactions (1:20 AM)..."
gcloud scheduler jobs create http plex-etl-medium-transactions \
    --location=$REGION \
    --project=$PROJECT_ID \
    --schedule="20 1 * * 1-6" \
    --time-zone=$TIMEZONE \
    --uri="${FUNCTION_URL}" \
    --http-method=POST \
    --headers="Content-Type=application/json" \
    --message-body='{"lookback_days": 5, "force_full_refresh": false, "table_group": "medium_transactions"}' \
    --oidc-service-account-email="${SERVICE_ACCOUNT}" \
    --attempt-deadline=1800s \
    --max-retry-attempts=3 \
    --min-backoff=60s \
    --description="ETL Group 2: factpagos, factcostos, factcoberturas, reccabecera, reclineas (Mon-Sat)" \
    2>/dev/null && echo "   ✅ Created" || \
gcloud scheduler jobs update http plex-etl-medium-transactions \
    --location=$REGION \
    --project=$PROJECT_ID \
    --schedule="20 1 * * 1-6" \
    --time-zone=$TIMEZONE \
    --uri="${FUNCTION_URL}" \
    --http-method=POST \
    --headers="Content-Type=application/json" \
    --message-body='{"lookback_days": 5, "force_full_refresh": false, "table_group": "medium_transactions"}' \
    --oidc-service-account-email="${SERVICE_ACCOUNT}" \
    --attempt-deadline=1800s \
    --max-retry-attempts=3 \
    --min-backoff=60s \
    --description="ETL Group 2: factpagos, factcostos, factcoberturas, reccabecera, reclineas (Mon-Sat)" \
    2>/dev/null && echo "   ✅ Updated"

# Group 3: Operational - 1:40 AM Argentina
echo "   Creating plex-etl-operational (1:40 AM)..."
gcloud scheduler jobs create http plex-etl-operational \
    --location=$REGION \
    --project=$PROJECT_ID \
    --schedule="40 1 * * 1-6" \
    --time-zone=$TIMEZONE \
    --uri="${FUNCTION_URL}" \
    --http-method=POST \
    --headers="Content-Type=application/json" \
    --message-body='{"lookback_days": 5, "force_full_refresh": false, "table_group": "operational"}' \
    --oidc-service-account-email="${SERVICE_ACCOUNT}" \
    --attempt-deadline=1800s \
    --max-retry-attempts=3 \
    --min-backoff=60s \
    --description="ETL Group 3: app pedidos, pedidos, compras, clientes (Mon-Sat)" \
    2>/dev/null && echo "   ✅ Created" || \
gcloud scheduler jobs update http plex-etl-operational \
    --location=$REGION \
    --project=$PROJECT_ID \
    --schedule="40 1 * * 1-6" \
    --time-zone=$TIMEZONE \
    --uri="${FUNCTION_URL}" \
    --http-method=POST \
    --headers="Content-Type=application/json" \
    --message-body='{"lookback_days": 5, "force_full_refresh": false, "table_group": "operational"}' \
    --oidc-service-account-email="${SERVICE_ACCOUNT}" \
    --attempt-deadline=1800s \
    --max-retry-attempts=3 \
    --min-backoff=60s \
    --description="ETL Group 3: app pedidos, pedidos, compras, clientes (Mon-Sat)" \
    2>/dev/null && echo "   ✅ Updated"

# Group 4: Catalogs & master data - 2:00 AM Argentina
echo "   Creating plex-etl-catalogs (2:00 AM)..."
gcloud scheduler jobs create http plex-etl-catalogs \
    --location=$REGION \
    --project=$PROJECT_ID \
    --schedule="0 2 * * 1-6" \
    --time-zone=$TIMEZONE \
    --uri="${FUNCTION_URL}" \
    --http-method=POST \
    --headers="Content-Type=application/json" \
    --message-body='{"lookback_days": 2, "force_full_refresh": false, "table_group": "catalogs"}' \
    --oidc-service-account-email="${SERVICE_ACCOUNT}" \
    --attempt-deadline=1800s \
    --max-retry-attempts=0 \
    --description="ETL Group 4: plex master data, stock, medicamentos (Mon-Sat)" \
    2>/dev/null && echo "   ✅ Created" || \
gcloud scheduler jobs update http plex-etl-catalogs \
    --location=$REGION \
    --project=$PROJECT_ID \
    --schedule="0 2 * * 1-6" \
    --time-zone=$TIMEZONE \
    --uri="${FUNCTION_URL}" \
    --http-method=POST \
    --headers="Content-Type=application/json" \
    --message-body='{"lookback_days": 2, "force_full_refresh": false, "table_group": "catalogs"}' \
    --oidc-service-account-email="${SERVICE_ACCOUNT}" \
    --attempt-deadline=1800s \
    --max-retry-attempts=0 \
    --description="ETL Group 4: plex master data, stock, medicamentos (Mon-Sat)" \
    2>/dev/null && echo "   ✅ Updated"

# Group 5: Quantio - 2:20 AM Argentina
echo "   Creating plex-etl-quantio (2:20 AM)..."
gcloud scheduler jobs create http plex-etl-quantio \
    --location=$REGION \
    --project=$PROJECT_ID \
    --schedule="20 2 * * 1-6" \
    --time-zone=$TIMEZONE \
    --uri="${FUNCTION_URL}" \
    --http-method=POST \
    --headers="Content-Type=application/json" \
    --message-body='{"lookback_days": 2, "force_full_refresh": false, "table_group": "quantio"}' \
    --oidc-service-account-email="${SERVICE_ACCOUNT}" \
    --attempt-deadline=1800s \
    --max-retry-attempts=0 \
    --description="ETL Group 5: all Quantio tables, 22 tables (Mon-Sat)" \
    2>/dev/null && echo "   ✅ Created" || \
gcloud scheduler jobs update http plex-etl-quantio \
    --location=$REGION \
    --project=$PROJECT_ID \
    --schedule="20 2 * * 1-6" \
    --time-zone=$TIMEZONE \
    --uri="${FUNCTION_URL}" \
    --http-method=POST \
    --headers="Content-Type=application/json" \
    --message-body='{"lookback_days": 2, "force_full_refresh": false, "table_group": "quantio"}' \
    --oidc-service-account-email="${SERVICE_ACCOUNT}" \
    --attempt-deadline=1800s \
    --max-retry-attempts=0 \
    --description="ETL Group 5: all Quantio tables, 22 tables (Mon-Sat)" \
    2>/dev/null && echo "   ✅ Updated"

# ---- Step 3: Disable old monolithic job ----
echo ""
echo "⏸️  Pausing old monolithic job (plex-etl-daily-incremental)..."
gcloud scheduler jobs pause plex-etl-daily-incremental \
    --location=$REGION --project=$PROJECT_ID 2>/dev/null \
    && echo "   ✅ Paused plex-etl-daily-incremental" \
    || echo "   ⚠️  Job not found (already deleted?)"

# ---- Sunday catch-up (lookback=8) ----
# The source MySQL consolidates a day's data ~24-48h late, so day D is only complete
# once the D+2 run reads it. A single missed weekday run therefore orphans a day forever.
# These Sunday jobs re-read the whole week to repair any such hole.
for pair in "heavy:heavy_transactions:0 1 * * 0" \
            "medium:medium_transactions:20 1 * * 0" \
            "operational:operational:40 1 * * 0"; do
    IFS=':' read -r short group sched <<< "$pair"
    gcloud scheduler jobs create http "plex-etl-${short}-catchup" \
        --project="$PROJECT_ID" \
        --location="$REGION" \
        --schedule="$sched" \
        --time-zone="America/Argentina/Buenos_Aires" \
        --uri="$FUNCTION_URL" \
        --http-method=POST \
        --oidc-service-account-email="$SERVICE_ACCOUNT" \
        --oidc-token-audience="$FUNCTION_URL" \
        --headers="Content-Type=application/json" \
        --message-body="{\"lookback_days\": 8, \"force_full_refresh\": false, \"table_group\": \"$group\"}" \
        --attempt-deadline=1800s \
        --max-retry-attempts=3 \
        --min-backoff=60s \
        --description="Domingo catch-up lookback=8 para reparar agujeros de la semana" \
    || gcloud scheduler jobs update http "plex-etl-${short}-catchup" \
        --project="$PROJECT_ID" \
        --location="$REGION" \
        --schedule="$sched" \
        --time-zone="America/Argentina/Buenos_Aires" \
        --uri="$FUNCTION_URL" \
        --http-method=POST \
        --oidc-service-account-email="$SERVICE_ACCOUNT" \
        --oidc-token-audience="$FUNCTION_URL" \
        --headers="Content-Type=application/json" \
        --message-body="{\"lookback_days\": 8, \"force_full_refresh\": false, \"table_group\": \"$group\"}" \
        --attempt-deadline=1800s \
        --max-retry-attempts=3 \
        --min-backoff=60s
done

# ---- Summary ----
echo ""
echo "============================================"
echo "✅ Cloud Scheduler setup complete!"
echo "============================================"
echo ""
echo "Trigger: HTTP → ${FUNCTION_URL}"
echo "Auth: OIDC token via ${SERVICE_ACCOUNT}"
echo "Attempt deadline: 3600s (1 hour per group)"
echo ""
echo "Jobs created (all times Argentina, Mon-Sat only):"
echo "  1:00 AM  plex-etl-heavy-transactions   (factcab, factlineas, asientos*)"
echo "  1:20 AM  plex-etl-medium-transactions  (factpagos, factcostos, rec*)"
echo "  1:40 AM  plex-etl-operational          (app*, pedidos, compras, clientes)"
echo "  2:00 AM  plex-etl-catalogs             (plex master data, stock)"
echo "  2:20 AM  plex-etl-quantio              (all 22 quantio tables)"
echo ""
echo "Sunday catch-up (lookback=8, repairs holes from missed weekday runs):"
echo "  1:00 AM  plex-etl-heavy-catchup"
echo "  1:20 AM  plex-etl-medium-catchup"
echo "  1:40 AM  plex-etl-operational-catchup"
echo ""
echo "Cloud Run timeout: 3600s (1 hour per group)"
echo "No Pub/Sub = no redelivery problem"
echo ""
echo "To verify:"
echo "  gcloud scheduler jobs list --location=$REGION --project=$PROJECT_ID"
echo ""
echo "To manually trigger a group:"
echo "  gcloud scheduler jobs run plex-etl-heavy-transactions --location=$REGION --project=$PROJECT_ID"
echo ""
echo "To check logs:"
echo "  gcloud logging read 'resource.labels.service_name=\"plex-etl-streaming-daily\"' --project=$PROJECT_ID --limit=50 --format='table(timestamp,textPayload)' --order=desc"
