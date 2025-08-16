#!/bin/bash
# ============================================
# CONFIGURACIÓN DE GOOGLE SECRET MANAGER
# ============================================

PROJECT_ID="your-project-id"  # CAMBIAR POR TU PROJECT ID

echo "🔐 Configurando Google Secret Manager para MySQL..."

# 1. Habilitar Secret Manager API
echo "Habilitando Secret Manager API..."
gcloud services enable secretmanager.googleapis.com --project=$PROJECT_ID

# 2. Crear Service Account para acceder a secrets
echo "Creando Service Account para ETL..."
gcloud iam service-accounts create etl-service-account \
    --display-name="ETL Service Account" \
    --description="Service account for ETL process to access secrets and resources" \
    --project=$PROJECT_ID

# Service Account Email
SA_EMAIL="etl-service-account@${PROJECT_ID}.iam.gserviceaccount.com"

# 3. Asignar permisos necesarios
echo "Asignando permisos al Service Account..."

# Secret Manager permissions
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/secretmanager.secretAccessor"

# Cloud Storage permissions
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/storage.admin"

# BigQuery permissions
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/bigquery.admin"

# Cloud Functions permissions (if needed)
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/cloudfunctions.invoker"

echo "✅ Service Account configurado: $SA_EMAIL"

# 4. Crear secrets usando gcloud (ejemplo)
echo "📝 Ejemplo de cómo crear secrets manualmente:"
echo ""
echo "# Para Plex:"
echo "gcloud secrets create mysql-plex-config --project=$PROJECT_ID"
echo "echo '{\"host\":\"your-host\",\"port\":\"3306\",\"user\":\"your-user\",\"password\":\"your-password\",\"database\":\"plex\"}' | gcloud secrets versions add mysql-plex-config --data-file=- --project=$PROJECT_ID"
echo ""
echo "# Para Quantio:"
echo "gcloud secrets create mysql-quantio-config --project=$PROJECT_ID"
echo "echo '{\"host\":\"your-host\",\"port\":\"3306\",\"user\":\"your-user\",\"password\":\"your-password\",\"database\":\"quantio\"}' | gcloud secrets versions add mysql-quantio-config --data-file=- --project=$PROJECT_ID"
echo ""
echo "O ejecuta: python setup_secrets.py"

# 5. Crear key para service account (para desarrollo local)
echo "🔑 Creando clave de service account para desarrollo local..."
gcloud iam service-accounts keys create etl-service-account-key.json \
    --iam-account=$SA_EMAIL \
    --project=$PROJECT_ID

echo ""
echo "✅ Configuración completada!"
echo ""
echo "📋 Próximos pasos:"
echo "1. Ejecutar: python setup_secrets.py (para configurar secrets interactivamente)"
echo "2. Configurar variable de entorno: export GCP_PROJECT_ID=$PROJECT_ID"
echo "3. Para desarrollo local: export GOOGLE_APPLICATION_CREDENTIALS=./etl-service-account-key.json"
echo "4. Probar conexiones: python database_connector.py"