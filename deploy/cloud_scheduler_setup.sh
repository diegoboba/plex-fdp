#!/bin/bash
# ============================================
# CONFIGURACIÓN DE CLOUD SCHEDULER
# ============================================

# Variables - AJUSTAR SEGÚN TU PROYECTO
PROJECT_ID="your-project-id"
REGION="us-central1"
FUNCTION_NAME="plex-etl-function"
SERVICE_ACCOUNT="etl-scheduler@${PROJECT_ID}.iam.gserviceaccount.com"

echo "Configurando Cloud Scheduler para ETL cada 12 horas..."

# 1. Habilitar API de Cloud Scheduler
gcloud services enable cloudscheduler.googleapis.com --project=$PROJECT_ID

# 2. Crear Service Account para el scheduler (si no existe)
echo "Creando service account para scheduler..."
gcloud iam service-accounts create etl-scheduler \
    --display-name="ETL Scheduler Service Account" \
    --project=$PROJECT_ID

# Dar permisos al service account
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/cloudfunctions.invoker"

# 3. Job ETL - 12:00 AM (medianoche)
echo "Creando job para 12:00 AM..."
gcloud scheduler jobs create http etl-midnight \
    --location=$REGION \
    --schedule="0 0 * * *" \
    --time-zone="America/Argentina/Buenos_Aires" \
    --uri="https://${REGION}-${PROJECT_ID}.cloudfunctions.net/${FUNCTION_NAME}" \
    --http-method=POST \
    --headers="Content-Type=application/json" \
    --message-body='{"incremental": true, "trigger": "midnight"}' \
    --oidc-service-account-email=$SERVICE_ACCOUNT \
    --description="ETL execution at midnight (12:00 AM)"

# 4. Job ETL - 12:00 PM (mediodía)  
echo "Creando job para 12:00 PM..."
gcloud scheduler jobs create http etl-noon \
    --location=$REGION \
    --schedule="0 12 * * *" \
    --time-zone="America/Argentina/Buenos_Aires" \
    --uri="https://${REGION}-${PROJECT_ID}.cloudfunctions.net/${FUNCTION_NAME}" \
    --http-method=POST \
    --headers="Content-Type=application/json" \
    --message-body='{"incremental": true, "trigger": "noon"}' \
    --oidc-service-account-email=$SERVICE_ACCOUNT \
    --description="ETL execution at noon (12:00 PM)"

# 5. Job semanal completo - Domingos 2:00 AM
echo "Creando job semanal completo..."
gcloud scheduler jobs create http etl-weekly-full \
    --location=$REGION \
    --schedule="0 2 * * 0" \
    --time-zone="America/Argentina/Buenos_Aires" \
    --uri="https://${REGION}-${PROJECT_ID}.cloudfunctions.net/${FUNCTION_NAME}" \
    --http-method=POST \
    --headers="Content-Type=application/json" \
    --message-body='{"incremental": false, "trigger": "weekly-full"}' \
    --oidc-service-account-email=$SERVICE_ACCOUNT \
    --description="Full ETL execution weekly on Sundays at 2:00 AM"

echo "Cloud Scheduler configurado exitosamente!"
echo ""
echo "Jobs creados:"
echo "- etl-midnight: Diario a las 12:00 AM"
echo "- etl-noon: Diario a las 12:00 PM" 
echo "- etl-weekly-full: Domingos 2:00 AM (carga completa)"
echo ""
echo "Para verificar los jobs:"
echo "gcloud scheduler jobs list --location=$REGION"