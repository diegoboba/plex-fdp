#!/bin/bash

# ============================================
# FULL REFRESH ETL - Staging + Atomic Swap
# ============================================
# Strategy:
#   1. Load all tables into a staging dataset (plex_analytics_staging)
#   2. Copy each table to the real dataset (plex_analytics) using bq cp
#   3. Delete the staging dataset
#
# Why staging?
#   - Avoids hitting BigQuery's 1,500 load_job_per_table.long quota
#     (staging tables are NEW, so their counter starts at 0)
#   - bq cp uses COPY jobs (different quota, not load jobs)
#   - If ETL fails mid-way, production data is untouched (atomic)
#
# Usage:
#   ./scripts/full_refresh.sh              # Full refresh all tables
#   ./scripts/full_refresh.sh --table_group heavy_transactions  # Single group

set -e

# Set working directory
cd /Users/bobalabs/code/plex-fdp

# Set environment variables
export GOOGLE_APPLICATION_CREDENTIALS="/Users/bobalabs/code/plex-fdp/etl-service-account-key.json"
export GCP_PROJECT_ID="plex-etl-project"

# Staging dataset - load here first, then copy to real dataset
STAGING_DATASET="plex_analytics_staging"
REAL_DATASET="plex_analytics"
PROJECT_ID="${GCP_PROJECT_ID}"

# Create log directory if it doesn't exist
mkdir -p logs

# Generate timestamp for log file
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_FILE="logs/full_refresh_${TIMESTAMP}.log"

# Use Python from virtual environment
PYTHON_VENV="/Users/bobalabs/code/plex-fdp/plex-env/bin/python"

# Pass through any extra args (e.g., --table_group heavy_transactions)
EXTRA_ARGS="$@"

echo "============================================" | tee -a "$LOG_FILE"
echo "FULL REFRESH ETL - $(date)" | tee -a "$LOG_FILE"
echo "============================================" | tee -a "$LOG_FILE"
echo "Staging dataset: ${STAGING_DATASET}" | tee -a "$LOG_FILE"
echo "Target dataset:  ${REAL_DATASET}" | tee -a "$LOG_FILE"
echo "Extra args:      ${EXTRA_ARGS:-none}" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

# ---- Step 1: Create staging dataset ----
echo "Step 1: Creating staging dataset ${STAGING_DATASET}..." | tee -a "$LOG_FILE"
bq --project_id="${PROJECT_ID}" mk --dataset --location=US "${PROJECT_ID}:${STAGING_DATASET}" 2>/dev/null \
    && echo "  Created ${STAGING_DATASET}" | tee -a "$LOG_FILE" \
    || echo "  ${STAGING_DATASET} already exists" | tee -a "$LOG_FILE"

# ---- Step 2: Run ETL loading into staging dataset ----
echo "" | tee -a "$LOG_FILE"
echo "Step 2: Running full refresh ETL into staging dataset..." | tee -a "$LOG_FILE"
echo "  Start: $(date)" | tee -a "$LOG_FILE"

export BIGQUERY_DATASET="${STAGING_DATASET}"

"$PYTHON_VENV" -m src.main_streaming \
    --force_full_refresh \
    --chunk_size 250000 \
    --mysql_timeout 3000 \
    $EXTRA_ARGS \
    >> "$LOG_FILE" 2>&1

ETL_EXIT_CODE=$?

if [ $ETL_EXIT_CODE -ne 0 ]; then
    echo "" | tee -a "$LOG_FILE"
    echo "ETL FAILED (exit code: ${ETL_EXIT_CODE}) at $(date)" | tee -a "$LOG_FILE"
    echo "Staging dataset ${STAGING_DATASET} left intact for debugging." | tee -a "$LOG_FILE"
    echo "To clean up manually: bq rm -r -f ${PROJECT_ID}:${STAGING_DATASET}" | tee -a "$LOG_FILE"
    exit 1
fi

echo "  ETL completed at $(date)" | tee -a "$LOG_FILE"

# ---- Step 3: Copy tables from staging to real dataset ----
echo "" | tee -a "$LOG_FILE"
echo "Step 3: Copying tables from ${STAGING_DATASET} -> ${REAL_DATASET}..." | tee -a "$LOG_FILE"

# List all tables in staging dataset (one per line in temp file)
TABLES_FILE=$(mktemp)
bq ls --max_results=200 "${PROJECT_ID}:${STAGING_DATASET}" 2>/dev/null | tail -n +3 | awk '{print $1}' | grep -v '^$' > "$TABLES_FILE"
TABLE_COUNT=$(wc -l < "$TABLES_FILE" | tr -d ' ')

if [ "$TABLE_COUNT" -eq 0 ]; then
    echo "  WARNING: No tables found in staging dataset!" | tee -a "$LOG_FILE"
    rm -f "$TABLES_FILE"
    exit 1
fi

echo "  Found ${TABLE_COUNT} tables to copy" | tee -a "$LOG_FILE"

COPY_FAILURES=0
COPY_SUCCESS=0

while IFS= read -r TABLE; do
    [ -z "$TABLE" ] && continue
    SRC="${PROJECT_ID}:${STAGING_DATASET}.${TABLE}"
    DST="${PROJECT_ID}:${REAL_DATASET}.${TABLE}"

    echo "  Copying ${TABLE}..." | tee -a "$LOG_FILE"
    if bq cp -f "${SRC}" "${DST}" >> "$LOG_FILE" 2>&1; then
        COPY_SUCCESS=$((COPY_SUCCESS + 1))
    else
        echo "  FAILED to copy ${TABLE}" | tee -a "$LOG_FILE"
        COPY_FAILURES=$((COPY_FAILURES + 1))
    fi
done < "$TABLES_FILE"
rm -f "$TABLES_FILE"

echo "" | tee -a "$LOG_FILE"
echo "Copy results: ${COPY_SUCCESS} succeeded, ${COPY_FAILURES} failed" | tee -a "$LOG_FILE"

# ---- Step 4: Cleanup staging dataset ----
if [ $COPY_FAILURES -eq 0 ]; then
    echo "" | tee -a "$LOG_FILE"
    echo "Step 4: Deleting staging dataset ${STAGING_DATASET}..." | tee -a "$LOG_FILE"
    bq rm -r -f "${PROJECT_ID}:${STAGING_DATASET}" >> "$LOG_FILE" 2>&1 \
        && echo "  Staging dataset deleted" | tee -a "$LOG_FILE" \
        || echo "  WARNING: Could not delete staging dataset" | tee -a "$LOG_FILE"
else
    echo "" | tee -a "$LOG_FILE"
    echo "Step 4: SKIPPING cleanup - ${COPY_FAILURES} copy failures" | tee -a "$LOG_FILE"
    echo "  Staging dataset ${STAGING_DATASET} left for debugging" | tee -a "$LOG_FILE"
    echo "  Fix issues, then clean up: bq rm -r -f ${PROJECT_ID}:${STAGING_DATASET}" | tee -a "$LOG_FILE"
fi

# ---- Summary ----
echo "" | tee -a "$LOG_FILE"
echo "============================================" | tee -a "$LOG_FILE"
echo "FULL REFRESH COMPLETED at $(date)" | tee -a "$LOG_FILE"
echo "  Tables loaded to staging: $(echo "$TABLES" | wc -l | tr -d ' ')" | tee -a "$LOG_FILE"
echo "  Tables copied to ${REAL_DATASET}: ${COPY_SUCCESS}" | tee -a "$LOG_FILE"
echo "  Copy failures: ${COPY_FAILURES}" | tee -a "$LOG_FILE"
echo "  Log file: ${LOG_FILE}" | tee -a "$LOG_FILE"
echo "============================================" | tee -a "$LOG_FILE"

if [ $COPY_FAILURES -gt 0 ]; then
    exit 1
fi
