#!/bin/bash
# Configure Cloud Scheduler for ETL pipeline

set -e

echo "⏰ Setting up Cloud Scheduler for ETL Pipeline..."

# Configuration
PROJECT_ID=${GCP_PROJECT_ID:-"plex-etl-project"}
SCHEDULER_JOB_NAME="plex-etl-schedule"
FUNCTION_NAME="plex-etl-pipeline"
REGION="us-central1"
TIMEZONE="America/Argentina/Buenos_Aires"  # Adjust to your timezone

# Get function URL
FUNCTION_URL=$(gcloud functions describe $FUNCTION_NAME --region=$REGION --format="value(httpsTrigger.url)")

if [ -z "$FUNCTION_URL" ]; then
    echo "❌ Function $FUNCTION_NAME not found in region $REGION"
    echo "Please deploy the function first: ./deploy.sh"
    exit 1
fi

echo "📋 Function URL: $FUNCTION_URL"

# Delete existing job if it exists
echo "🗑️  Removing existing scheduler job (if exists)..."
gcloud scheduler jobs delete $SCHEDULER_JOB_NAME --location=$REGION --quiet || true

# Create scheduler job (every 12 hours at 12 AM and 12 PM)
echo "⏰ Creating scheduler job..."
gcloud scheduler jobs create http $SCHEDULER_JOB_NAME \
    --location=$REGION \
    --schedule="0 0,12 * * *" \
    --time-zone="$TIMEZONE" \
    --uri="$FUNCTION_URL" \
    --http-method=POST \
    --headers="Content-Type=application/json" \
    --message-body='{"incremental": true}' \
    --attempt-deadline=3600s \
    --max-retry-attempts=3 \
    --min-backoff=60s \
    --max-backoff=300s

echo "✅ Scheduler job created successfully!"
echo ""
echo "📋 Schedule details:"
echo "  - Job name: $SCHEDULER_JOB_NAME"
echo "  - Schedule: Every 12 hours (12:00 AM and 12:00 PM)"
echo "  - Timezone: $TIMEZONE"
echo "  - Target: $FUNCTION_URL"
echo "  - Max retries: 3"
echo ""
echo "💡 Management commands:"
echo "  - View jobs: gcloud scheduler jobs list --location=$REGION"
echo "  - Run now: gcloud scheduler jobs run $SCHEDULER_JOB_NAME --location=$REGION"
echo "  - Pause: gcloud scheduler jobs pause $SCHEDULER_JOB_NAME --location=$REGION"
echo "  - Resume: gcloud scheduler jobs resume $SCHEDULER_JOB_NAME --location=$REGION"
echo "  - View logs: gcloud scheduler jobs describe $SCHEDULER_JOB_NAME --location=$REGION"

# Test run (optional)
read -p "🧪 Do you want to test run the scheduler now? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "🚀 Running scheduler job now..."
    gcloud scheduler jobs run $SCHEDULER_JOB_NAME --location=$REGION
    echo "✅ Job triggered! Check function logs for execution status."
    echo "📋 Monitor: gcloud functions logs read $FUNCTION_NAME --region=$REGION --limit=50"
fi

echo ""
echo "🎉 Cloud Scheduler setup completed!"
echo "📈 Your ETL will now run automatically every 12 hours!"