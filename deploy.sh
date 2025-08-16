#!/bin/bash
# Deploy ETL to Google Cloud Functions

set -e

echo "🚀 Deploying ETL Pipeline to Google Cloud Functions..."

# Configuration
PROJECT_ID=${GCP_PROJECT_ID:-"plex-etl-project"}
FUNCTION_NAME="plex-etl-pipeline"
REGION="us-central1"
MEMORY="2GB"
TIMEOUT="3600s"  # 1 hour
RUNTIME="python311"

# Check if we're authenticated
echo "📋 Checking authentication..."
gcloud auth list --filter=status:ACTIVE --format="value(account)" | head -1
if [ $? -ne 0 ]; then
    echo "❌ Please run: gcloud auth login"
    exit 1
fi

# Set project
echo "📂 Setting project: $PROJECT_ID"
gcloud config set project $PROJECT_ID

# Enable required APIs
echo "🔧 Enabling required APIs..."
gcloud services enable cloudfunctions.googleapis.com
gcloud services enable cloudscheduler.googleapis.com
gcloud services enable eventarc.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable artifactregistry.googleapis.com

# Create deployment package
echo "📦 Creating deployment package..."
rm -rf deploy_package
mkdir deploy_package

# Copy source files
cp -r src/* deploy_package/
cp requirements-cloud.txt deploy_package/requirements.txt
cp src/main.py deploy_package/

# Create .gcloudignore
cat > deploy_package/.gcloudignore << EOF
__pycache__/
*.pyc
*.pyo
*.pyd
.Python
env/
venv/
.env
.git/
.gitignore
README.md
*.md
tests/
.pytest_cache/
.coverage
.vscode/
.idea/
*.log
etl-service-account-key.json
EOF

echo "📁 Deployment package created in deploy_package/"

# Deploy Cloud Function (HTTP trigger)
echo "🚀 Deploying HTTP-triggered Cloud Function..."
cd deploy_package

gcloud functions deploy $FUNCTION_NAME \
    --runtime=$RUNTIME \
    --trigger-http \
    --allow-unauthenticated \
    --entry-point=etl_cloud_function \
    --memory=$MEMORY \
    --timeout=$TIMEOUT \
    --region=$REGION \
    --set-env-vars="GCP_PROJECT_ID=$PROJECT_ID,GCS_BUCKET_NAME=plex-etl-data-bobix,BIGQUERY_DATASET=plex_analytics,ENVIRONMENT=production" \
    --max-instances=1 \
    --min-instances=0

cd ..

# Get function URL
FUNCTION_URL=$(gcloud functions describe $FUNCTION_NAME --region=$REGION --format="value(httpsTrigger.url)")
echo "✅ Function deployed successfully!"
echo "📋 Function URL: $FUNCTION_URL"

# Test the function
echo "🧪 Testing the function..."
curl -X POST $FUNCTION_URL \
    -H "Content-Type: application/json" \
    -d '{"incremental": true}' \
    --max-time 30 || echo "⚠️  Function test may take longer (timeout expected for full ETL)"

echo ""
echo "🎉 Deployment completed!"
echo ""
echo "📋 Summary:"
echo "  - Function name: $FUNCTION_NAME"
echo "  - Region: $REGION"
echo "  - Memory: $MEMORY"
echo "  - Timeout: $TIMEOUT"
echo "  - URL: $FUNCTION_URL"
echo ""
echo "💡 Next steps:"
echo "  1. Test manually: curl -X POST $FUNCTION_URL -H 'Content-Type: application/json' -d '{\"incremental\": true}'"
echo "  2. Set up Cloud Scheduler: ./setup_scheduler.sh"
echo "  3. Monitor logs: gcloud functions logs read $FUNCTION_NAME --region=$REGION"