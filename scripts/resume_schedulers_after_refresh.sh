#!/bin/bash
# Waits for a running full_refresh.sh to exit, then re-enables the paused
# weekday Cloud Scheduler jobs.
#
# The schedulers are paused while a local full refresh runs so the two don't
# compete for MySQL connections (the ETL user cannot KILL connections, so a
# saturated server just has to be waited out).
#
# Schedulers are resumed regardless of whether the refresh succeeded: leaving
# them paused is the worse failure: a skipped nightly run orphans a day of
# sales permanently (see CLAUDE.md Problem 10). A failed refresh is repaired
# by the next incremental run's lookback window.
#
# Usage: ./scripts/resume_schedulers_after_refresh.sh <pid> <refresh_log>

set -u

GCLOUD=/Users/bobalabs/google-cloud-sdk/bin/gcloud
PROJECT=plex-etl-project
REGION=us-central1
JOBS=(heavy-transactions medium-transactions operational catalogs quantio)

REFRESH_PID="${1:?usage: $0 <pid> <refresh_log>}"
REFRESH_LOG="${2:?usage: $0 <pid> <refresh_log>}"
OUT="logs/resume_schedulers_$(date +%Y%m%d_%H%M%S).log"

echo "Watching full refresh PID ${REFRESH_PID} (log: ${REFRESH_LOG})" | tee -a "$OUT"

while kill -0 "$REFRESH_PID" 2>/dev/null; do
    sleep 60
done

echo "Full refresh PID ${REFRESH_PID} exited at $(date)" | tee -a "$OUT"

if grep -q "FULL REFRESH COMPLETED" "$REFRESH_LOG" 2>/dev/null; then
    echo "  Refresh reached completion banner" | tee -a "$OUT"
    grep -E "Copy results|Tables copied" "$REFRESH_LOG" | tail -2 | tee -a "$OUT"
else
    echo "  WARNING: no completion banner found. Refresh likely failed." | tee -a "$OUT"
    echo "  Staging dataset plex_analytics_staging was left intact for debugging." | tee -a "$OUT"
    tail -15 "$REFRESH_LOG" 2>/dev/null | tee -a "$OUT"
fi

echo "" | tee -a "$OUT"
echo "Resuming schedulers..." | tee -a "$OUT"
for j in "${JOBS[@]}"; do
    if "$GCLOUD" scheduler jobs resume "plex-etl-$j" \
        --project="$PROJECT" --location="$REGION" --quiet >/dev/null 2>&1; then
        echo "  resumed: plex-etl-$j" | tee -a "$OUT"
    else
        echo "  ERROR resuming plex-etl-$j -- DO THIS BY HAND" | tee -a "$OUT"
    fi
done

echo "" | tee -a "$OUT"
"$GCLOUD" scheduler jobs list --project="$PROJECT" --location="$REGION" \
    --format="table(name.basename(),schedule,state)" 2>&1 | tee -a "$OUT"
