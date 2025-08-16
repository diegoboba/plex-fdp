try:
    import functions_framework
    CLOUD_FUNCTIONS_AVAILABLE = True
except ImportError:
    CLOUD_FUNCTIONS_AVAILABLE = False
    print("⚠️  functions_framework not available - running in local mode")

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

if CLOUD_FUNCTIONS_AVAILABLE:
    @functions_framework.http
    def etl_cloud_function(request):
        """Cloud Function entry point for HTTP triggers"""
        try:
            # Parse request data
            request_json = request.get_json(silent=True)
            incremental = True
            
            if request_json and 'incremental' in request_json:
                incremental = request_json['incremental']
            
            # Run the ETL pipeline
            result = run_etl_pipeline(incremental=incremental)
            
            return result, 200 if result['status'] == 'success' else 500
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"Cloud Function error: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }, 500

    @functions_framework.cloud_event
    def etl_scheduled_function(cloud_event):
        """Cloud Function entry point for scheduled triggers (Cloud Scheduler)"""
        try:
            print(f"Scheduled ETL triggered at {datetime.now()}")
            
            # Run incremental ETL by default for scheduled runs
            result = run_etl_pipeline(incremental=True)
            
            print(f"Scheduled ETL result: {result}")
            return result
            
        except Exception as e:
            error_msg = f"Scheduled ETL failed: {str(e)}"
            print(error_msg)
            return {
                "status": "error",
                "message": error_msg,
                "timestamp": datetime.now().isoformat()
            }

def run_local():
    """Function to run ETL locally for testing"""
    print("Running ETL locally...")
    result = run_etl_pipeline(incremental=False)  # Full extraction for testing
    print(f"Local ETL result: {result}")
    return result

if __name__ == "__main__":
    # Run locally when script is executed directly
    run_local()