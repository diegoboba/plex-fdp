#!/bin/bash

# ETL Script for Plex/Quantio to BigQuery
# Run daily incremental ETL

# Set working directory
cd /Users/bobalabs/code/plex-fdp

# Set environment variables
export GOOGLE_APPLICATION_CREDENTIALS="/Users/bobalabs/code/plex-fdp/etl-service-account-key.json"
export GCP_PROJECT_ID="plex-etl-project"

# Create log directory if it doesn't exist
mkdir -p logs

# Generate timestamp for log file
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_FILE="logs/etl_cron_${TIMESTAMP}.log"

echo "Starting ETL at $(date)" >> "$LOG_FILE"

# Use Python from virtual environment
PYTHON_VENV="/Users/bobalabs/code/plex-fdp/plex-env/bin/python"

# Run incremental ETL (last 3 days of data)
"$PYTHON_VENV" -m src.main_streaming \
    --lookback_days 5 \
    --mysql_timeout 3000 \
    >> "$LOG_FILE" 2>&1

# Check exit status
if [ $? -eq 0 ]; then
    echo "ETL completed successfully at $(date)" >> "$LOG_FILE"
else
    echo "ETL failed at $(date)" >> "$LOG_FILE"
    # Optional: Send notification on failure
    # osascript -e 'display notification "ETL Job Failed" with title "Plex ETL"'
fi