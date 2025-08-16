#!/usr/bin/env python3
"""
ETL incremental optimizado - solo últimas 12 horas
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from etl.extractor import DataExtractor
from cloud.storage import StorageManager
from cloud.bigquery import BigQueryManager
from datetime import datetime

def run_incremental_etl():
    """ETL incremental rápido - solo datos nuevos"""
    print(f"🚀 Starting INCREMENTAL ETL at {datetime.now()}")
    print("📊 Extracting only data from last 12 hours...")
    
    try:
        # Initialize components
        extractor = DataExtractor()
        storage_manager = StorageManager()
        bq_manager = BigQueryManager()
        
        # Extract only incremental data (last 12 hours)
        print("⏱️ Extracting incremental data...")
        start_time = datetime.now()
        
        extracted_data = extractor.extract_all_data(incremental=True)
        
        extract_time = datetime.now()
        print(f"✅ Data extraction completed in {(extract_time - start_time).total_seconds():.1f}s")
        
        if not extracted_data:
            print("ℹ️ No new data to process")
            return
        
        # Show summary
        total_rows = sum(len(df) for df in extracted_data.values())
        print(f"📈 Total incremental rows: {total_rows:,}")
        
        for table, df in extracted_data.items():
            print(f"  - {table}: {len(df):,} rows")
        
        # Upload to Cloud Storage
        print("☁️ Uploading to Cloud Storage...")
        uploaded_files = storage_manager.upload_all_data(extracted_data, file_format='csv')
        
        upload_time = datetime.now()
        print(f"✅ Upload completed in {(upload_time - extract_time).total_seconds():.1f}s")
        
        # Update BigQuery
        print("🏗️ Updating BigQuery tables...")
        bq_manager.create_all_external_tables(uploaded_files)
        
        bq_time = datetime.now()
        total_time = (bq_time - start_time).total_seconds()
        
        print(f"🎉 Incremental ETL completed successfully!")
        print(f"⏱️ Total time: {total_time:.1f}s ({total_time/60:.1f} minutes)")
        print(f"📊 Processing speed: {total_rows/(total_time/60):.0f} rows/minute")
        
    except Exception as e:
        print(f"❌ Incremental ETL failed: {e}")
        raise

if __name__ == "__main__":
    run_incremental_etl()