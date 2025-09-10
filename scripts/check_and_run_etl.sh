#!/bin/bash

# Check if ETL ran today and run if missed

cd /Users/bobix/code/plex/plex-fdp

# Check if ETL already ran today
TODAY=$(date +"%Y%m%d")
LAST_RUN_FILE="logs/.last_etl_run"

if [ -f "$LAST_RUN_FILE" ]; then
    LAST_RUN=$(cat "$LAST_RUN_FILE")
else
    LAST_RUN="never"
fi

if [ "$LAST_RUN" != "$TODAY" ]; then
    echo "ETL hasn't run today. Running now..."
    
    # Run the ETL
    /Users/bobix/code/plex/plex-fdp/scripts/run_etl.sh
    
    # Update last run date
    echo "$TODAY" > "$LAST_RUN_FILE"
else
    echo "ETL already ran today ($TODAY)"
fi