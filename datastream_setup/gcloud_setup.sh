#!/bin/bash
# ============================================
# CONFIGURACIÓN DE DATASTREAM EN GOOGLE CLOUD
# ============================================

# Variables - AJUSTAR SEGÚN TU PROYECTO
PROJECT_ID="your-project-id"
REGION="us-central1"  # o tu región preferida
DATASET_NAME="plex_analytics"

# Plex MySQL connection details
PLEX_MYSQL_HOST="your-plex-mysql-host"
PLEX_MYSQL_PORT="3306"
PLEX_MYSQL_USER="datastream"
PLEX_MYSQL_PASSWORD="your-password"

# Quantio MySQL connection details  
QUANTIO_MYSQL_HOST="your-quantio-mysql-host"
QUANTIO_MYSQL_PORT="3306"
QUANTIO_MYSQL_USER="datastream"
QUANTIO_MYSQL_PASSWORD="your-password"

echo "Setting up Datastream for project: $PROJECT_ID"

# 1. Habilitar APIs necesarias
echo "Enabling required APIs..."
gcloud services enable datastream.googleapis.com --project=$PROJECT_ID
gcloud services enable bigquery.googleapis.com --project=$PROJECT_ID
gcloud services enable compute.googleapis.com --project=$PROJECT_ID

# 2. Crear dataset en BigQuery
echo "Creating BigQuery dataset..."
bq mk --location=$REGION --dataset $PROJECT_ID:$DATASET_NAME

# 3. Crear Connection Profile para Plex MySQL
echo "Creating connection profile for Plex MySQL..."
gcloud datastream connection-profiles create plex-mysql-profile \
    --location=$REGION \
    --type=mysql \
    --mysql-hostname=$PLEX_MYSQL_HOST \
    --mysql-port=$PLEX_MYSQL_PORT \
    --mysql-username=$PLEX_MYSQL_USER \
    --mysql-password=$PLEX_MYSQL_PASSWORD \
    --display-name="Plex MySQL Source"

# 4. Crear Connection Profile para Quantio MySQL
echo "Creating connection profile for Quantio MySQL..."
gcloud datastream connection-profiles create quantio-mysql-profile \
    --location=$REGION \
    --type=mysql \
    --mysql-hostname=$QUANTIO_MYSQL_HOST \
    --mysql-port=$QUANTIO_MYSQL_PORT \
    --mysql-username=$QUANTIO_MYSQL_USER \
    --mysql-password=$QUANTIO_MYSQL_PASSWORD \
    --display-name="Quantio MySQL Source"

# 5. Crear Connection Profile para BigQuery Destination
echo "Creating BigQuery destination profile..."
gcloud datastream connection-profiles create bigquery-destination-profile \
    --location=$REGION \
    --type=bigquery \
    --display-name="BigQuery Destination"

# 6. Crear Stream para Plex
echo "Creating Datastream for Plex..."
gcloud datastream streams create plex-to-bigquery \
    --location=$REGION \
    --display-name="Plex to BigQuery Stream" \
    --source-connection-profile=plex-mysql-profile \
    --destination-connection-profile=bigquery-destination-profile \
    --mysql-source-config-include-objects-mysql-databases=plex \
    --bigquery-destination-config-data-freshness=60 \
    --bigquery-destination-config-source-hierarchy-datasets-dataset-id=$DATASET_NAME

# 7. Crear Stream para Quantio
echo "Creating Datastream for Quantio..."
gcloud datastream streams create quantio-to-bigquery \
    --location=$REGION \
    --display-name="Quantio to BigQuery Stream" \
    --source-connection-profile=quantio-mysql-profile \
    --destination-connection-profile=bigquery-destination-profile \
    --mysql-source-config-include-objects-mysql-databases=quantio \
    --bigquery-destination-config-data-freshness=60 \
    --bigquery-destination-config-source-hierarchy-datasets-dataset-id=$DATASET_NAME

echo "Datastream setup completed!"
echo "Next steps:"
echo "1. Verify the streams in Cloud Console"
echo "2. Start the streams when ready"
echo "3. Monitor data replication"