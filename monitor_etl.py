#!/usr/bin/env python3
"""
Monitor ETL progress - verifica el estado del proceso
"""

import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def check_gcs_uploads():
    """Verifica archivos subidos a GCS"""
    try:
        from cloud.storage import StorageManager
        storage = StorageManager()
        
        print("📁 Checking Google Cloud Storage...")
        
        # List recent files in bucket
        from google.cloud import storage as gcs
        client = gcs.Client()
        bucket_name = os.getenv('GCS_BUCKET_NAME', 'plex-etl-data-bobix')
        bucket = client.bucket(bucket_name)
        
        files = list(bucket.list_blobs(prefix=f"{datetime.now().strftime('%Y/%m/%d')}"))
        
        if files:
            print(f"✅ Found {len(files)} files uploaded today:")
            for blob in files[-5:]:  # Show last 5
                size_mb = blob.size / (1024*1024) if blob.size else 0
                print(f"  - {blob.name} ({size_mb:.1f}MB) - {blob.time_created}")
        else:
            print("⏳ No files uploaded yet today")
            
    except Exception as e:
        print(f"❌ Error checking GCS: {e}")

def check_bigquery_tables():
    """Verifica tablas en BigQuery"""
    try:
        from cloud.bigquery import BigQueryManager
        bq = BigQueryManager()
        
        print("\n🏗️ Checking BigQuery tables...")
        
        from google.cloud import bigquery
        client = bigquery.Client()
        dataset_id = os.getenv('BIGQUERY_DATASET', 'plex_analytics')
        
        tables = list(client.list_tables(dataset_id))
        
        if tables:
            print(f"✅ Found {len(tables)} tables in {dataset_id}:")
            for table in tables:
                # Get table info
                table_ref = client.get_table(table.reference)
                print(f"  - {table.table_id}: {table_ref.num_rows:,} rows ({table_ref.modified})")
        else:
            print("⏳ No tables found yet")
            
    except Exception as e:
        print(f"❌ Error checking BigQuery: {e}")

def check_running_processes():
    """Verifica procesos ETL en ejecución"""
    import subprocess
    
    print("\n🔍 Checking running ETL processes...")
    
    try:
        # Check for python processes with main_local.py
        result = subprocess.run(['pgrep', '-f', 'main_local.py'], 
                              capture_output=True, text=True)
        
        if result.returncode == 0:
            pids = result.stdout.strip().split('\n')
            print(f"🏃 Found {len(pids)} ETL processes running:")
            for pid in pids:
                if pid:
                    print(f"  - PID: {pid}")
        else:
            print("⏸️ No ETL processes currently running")
            
    except Exception as e:
        print(f"❌ Error checking processes: {e}")

def main():
    """Monitor completo del ETL"""
    print(f"🔍 ETL Progress Monitor - {datetime.now()}")
    print("="*50)
    
    check_running_processes()
    check_gcs_uploads()
    check_bigquery_tables()
    
    print("\n" + "="*50)
    print("💡 Commands:")
    print("- Monitor logs: tail -f etl_progress.log")
    print("- Kill ETL: pkill -f main_local.py")
    print("- Run incremental: python3 run_incremental.py")

if __name__ == "__main__":
    main()