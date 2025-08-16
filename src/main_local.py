#!/usr/bin/env python3
"""
ETL Pipeline - Versión Local (sin Cloud Functions)
"""

from etl.extractor import DataExtractor
from cloud.storage import StorageManager
from cloud.bigquery import BigQueryManager
from datetime import datetime

def run_etl_pipeline(incremental: bool = True):
    """Main ETL pipeline function"""
    try:
        print(f"Starting ETL pipeline at {datetime.now()}")
        
        # Initialize components
        extractor = DataExtractor()
        storage_manager = StorageManager()
        bq_manager = BigQueryManager()
        
        # Step 1: Extract data from MySQL databases
        print("Step 1: Extracting data from MySQL...")
        extracted_data = extractor.extract_all_data(incremental=incremental)
        
        if not extracted_data:
            print("No data extracted. Exiting.")
            return {"status": "success", "message": "No data to process"}
        
        # Step 2: Upload data to Google Cloud Storage
        print("Step 2: Uploading data to Google Cloud Storage...")
        uploaded_files = storage_manager.upload_all_data(extracted_data, file_format='csv')
        
        if not uploaded_files:
            print("No files uploaded. Exiting.")
            return {"status": "error", "message": "Failed to upload files"}
        
        # Step 3: Create/Update external tables in BigQuery
        print("Step 3: Creating external tables in BigQuery...")
        bq_manager.create_all_external_tables(uploaded_files)
        
        # Step 4: Create/Update analytical views
        print("Step 4: Creating analytical views...")
        bq_manager.create_analytical_views()
        
        # Step 5: Clean up old files (optional)
        print("Step 5: Cleaning up old files...")
        storage_manager.delete_old_files(days_old=30)
        
        print(f"ETL pipeline completed successfully at {datetime.now()}")
        return {
            "status": "success", 
            "message": f"Processed {len(extracted_data)} tables",
            "files_uploaded": len(uploaded_files),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        print(f"ETL pipeline failed: {str(e)}")
        return {
            "status": "error", 
            "message": str(e),
            "timestamp": datetime.now().isoformat()
        }

def run_test_pipeline():
    """Run ETL with small samples for testing"""
    print("🧪 Running ETL with test samples...")
    
    try:
        extractor = DataExtractor()
        storage_manager = StorageManager()
        bq_manager = BigQueryManager()
        
        # Extract small samples
        print("Extracting test samples...")
        
        # Override extractor to get small samples
        from database.connector import DatabaseConnector
        import os
        
        project_id = os.getenv('GCP_PROJECT_ID', 'plex-etl-project')
        db = DatabaseConnector(project_id)
        
        test_data = {}
        
        # Small samples from each database
        test_queries = {
            'plex_sucursales': ('plex', 'sucursales', "SELECT * FROM sucursales LIMIT 5"),
            'plex_medicamentos': ('plex', 'medicamentos', "SELECT * FROM medicamentos LIMIT 10"),
            'quantio_productos': ('quantio', 'productos', "SELECT * FROM productos LIMIT 10")
        }
        
        for table_name, (database, table, query) in test_queries.items():
            try:
                df = db.extract_table_data(database, table, query)
                test_data[table_name] = df
                print(f"  ✅ {table_name}: {len(df)} rows")
            except Exception as e:
                print(f"  ❌ {table_name} failed: {e}")
        
        if not test_data:
            print("No test data extracted")
            return
        
        # Upload to storage
        print("Uploading test data...")
        uploaded_files = storage_manager.upload_all_data(test_data, file_format='csv')
        
        # Create external tables
        print("Creating external tables...")
        bq_manager.create_all_external_tables(uploaded_files)
        
        print("🎉 Test ETL completed successfully!")
        
    except Exception as e:
        print(f"❌ Test ETL failed: {e}")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == 'test':
        run_test_pipeline()
    else:
        print("Choose an option:")
        print("1. Full ETL (incremental)")
        print("2. Full ETL (complete)")
        print("3. Test ETL (samples)")
        
        choice = input("Enter choice (1/2/3): ")
        
        if choice == "1":
            result = run_etl_pipeline(incremental=True)
        elif choice == "2":
            result = run_etl_pipeline(incremental=False)
        elif choice == "3":
            run_test_pipeline()
        else:
            print("Invalid choice")
            
        if choice in ["1", "2"]:
            print(f"\nResult: {result}")