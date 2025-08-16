#!/usr/bin/env python3
"""
Test ETL pipeline con muestras pequeñas
"""

import os
import sys

# Configurar PYTHONPATH
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from database.connector import DatabaseConnector
from etl.extractor import DataExtractor
from cloud.storage import StorageManager
from cloud.bigquery import BigQueryManager

def test_small_extraction():
    """Test extracción con samples pequeños"""
    print("🔍 Testing small data extraction...")
    
    project_id = os.getenv('GCP_PROJECT_ID', 'plex-etl-project')
    db = DatabaseConnector(project_id)
    
    # Test con queries limitadas
    test_queries = {
        'plex_sucursales': "SELECT * FROM sucursales LIMIT 5",
        'plex_medicamentos': "SELECT * FROM medicamentos LIMIT 10", 
        'quantio_productos': "SELECT * FROM productos LIMIT 10"
    }
    
    extracted_data = {}
    
    for table_name, query in test_queries.items():
        try:
            database = table_name.split('_')[0]  # plex o quantio
            table = table_name.split('_', 1)[1]   # nombre de tabla
            
            print(f"  📊 Extracting {table_name}...")
            df = db.extract_table_data(database, table, query)
            extracted_data[table_name] = df
            print(f"    ✅ {len(df)} rows extracted")
            
        except Exception as e:
            print(f"    ❌ Failed: {e}")
    
    return extracted_data

def test_storage_upload(data):
    """Test upload to Cloud Storage"""
    print("\n☁️ Testing Cloud Storage upload...")
    
    try:
        storage = StorageManager()
        uploaded_files = storage.upload_all_data(data, file_format='csv')
        
        print(f"✅ {len(uploaded_files)} files uploaded:")
        for table, path in uploaded_files.items():
            print(f"  - {table}: {path}")
            
        return uploaded_files
        
    except Exception as e:
        print(f"❌ Storage upload failed: {e}")
        return {}

def test_bigquery_setup(uploaded_files):
    """Test BigQuery external tables"""
    print("\n🏗️ Testing BigQuery setup...")
    
    try:
        bq = BigQueryManager()
        
        # Crear dataset si no existe
        bq.create_dataset_if_not_exists()
        
        # Crear external tables
        bq.create_all_external_tables(uploaded_files)
        
        print("✅ BigQuery setup completed")
        return True
        
    except Exception as e:
        print(f"❌ BigQuery setup failed: {e}")
        return False

def main():
    """Test completo del pipeline"""
    print("🧪 Testing ETL Pipeline with small samples...\n")
    
    # Step 1: Extract small samples
    data = test_small_extraction()
    if not data:
        print("❌ No data extracted. Stopping.")
        return
    
    # Step 2: Upload to Storage
    uploaded_files = test_storage_upload(data)
    if not uploaded_files:
        print("❌ Upload failed. Stopping.")
        return
    
    # Step 3: Setup BigQuery
    bq_success = test_bigquery_setup(uploaded_files)
    if not bq_success:
        print("❌ BigQuery setup failed. Stopping.")
        return
    
    print("\n🎉 ETL Pipeline test completed successfully!")
    print("\n📋 Next steps:")
    print("1. Check BigQuery console for external tables")
    print("2. Run full ETL: cd src && python main.py")
    print("3. Deploy to Cloud Functions")

if __name__ == "__main__":
    main()