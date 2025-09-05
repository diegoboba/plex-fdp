try:
    import functions_framework
    CLOUD_FUNCTIONS_AVAILABLE = True
except ImportError:
    CLOUD_FUNCTIONS_AVAILABLE = False
    print("⚠️  functions_framework not available - running in local mode")

from .etl.streaming_extractor import StreamingDataExtractor
from .cloud.bigquery import BigQueryManager
from datetime import datetime
import sys

def run_streaming_etl_pipeline(lookback_days: int = 3, force_full_refresh: bool = False, 
                              chunk_size: int = None, single_table: str = None,
                              mysql_timeout: int = None):
    """Optimized ETL pipeline that loads data directly to BigQuery in chunks
    
    Args:
        lookback_days: Number of days to look back for incremental processing
        force_full_refresh: Force full refresh for all tables
        chunk_size: Override default chunk size (rows per chunk)
        single_table: Process only this specific table (format: database.table, e.g., 'plex.factcabecera')
        mysql_timeout: MySQL query timeout in seconds (default: 300 for data, 5 for counts)
    """
    try:
        print(f"Starting streaming ETL pipeline at {datetime.now()}")
        if chunk_size:
            print(f"Using custom chunk size: {chunk_size:,} rows")
        if single_table:
            print(f"Processing single table: {single_table}")
        if mysql_timeout:
            print(f"Using MySQL timeout: {mysql_timeout} seconds")
        
        # Initialize components with timeout if provided
        streaming_extractor = StreamingDataExtractor(mysql_timeout=mysql_timeout)
        bq_manager = BigQueryManager()
        
        # Step 1: Extract and load data directly to BigQuery (streaming)
        print("Step 1: Extracting and loading data to BigQuery (streaming)...")
        
        if single_table:
            # Process single table only
            load_results = streaming_extractor.extract_single_table(
                table_spec=single_table,
                lookback_days=lookback_days,
                force_full_refresh=force_full_refresh,
                override_chunk_size=chunk_size,
                mysql_timeout=mysql_timeout
            )
        else:
            # Process all tables
            load_results = streaming_extractor.extract_all_data_streaming(
                lookback_days=lookback_days, 
                force_full_refresh=force_full_refresh,
                override_chunk_size=chunk_size,
                mysql_timeout=mysql_timeout
            )
        
        if not load_results or sum(load_results.values()) == 0:
            print("No data extracted/loaded. Exiting.")
            return {"status": "success", "message": "No data to process"}
        
        # NOTA: Analytical views removidas - ver PLAN.md para implementación futura
        
        print(f"Streaming ETL pipeline completed successfully at {datetime.now()}")
        return {
            "status": "success", 
            "message": f"Loaded {sum(load_results.values()):,} total rows across {len(load_results)} tables",
            "tables_processed": len(load_results),
            "total_rows_loaded": sum(load_results.values()),
            "table_details": load_results,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        print(f"Streaming ETL pipeline failed: {str(e)}")
        return {
            "status": "error", 
            "message": str(e),
            "timestamp": datetime.now().isoformat()
        }

if CLOUD_FUNCTIONS_AVAILABLE:
    @functions_framework.http
    def streaming_etl_cloud_function(request):
        """Cloud Function entry point for HTTP triggers (streaming version)"""
        try:
            # Parse request data
            request_json = request.get_json(silent=True)
            lookback_days = 3
            force_full_refresh = False
            
            if request_json:
                lookback_days = request_json.get('lookback_days', 3)
                force_full_refresh = request_json.get('force_full_refresh', False)
            
            # Run the streaming ETL pipeline
            result = run_streaming_etl_pipeline(lookback_days=lookback_days, force_full_refresh=force_full_refresh)
            
            return result, 200 if result['status'] == 'success' else 500
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"Cloud Function error: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }, 500

    @functions_framework.cloud_event
    def streaming_etl_scheduled_function(cloud_event):
        """Cloud Function entry point for scheduled triggers (streaming version)"""
        try:
            print(f"Scheduled streaming ETL triggered at {datetime.now()}")
            
            # Run incremental ETL by default for scheduled runs (3 days lookback)
            result = run_streaming_etl_pipeline(lookback_days=3, force_full_refresh=False)
            
            print(f"Scheduled streaming ETL result: {result}")
            return result
            
        except Exception as e:
            error_msg = f"Scheduled streaming ETL failed: {str(e)}"
            print(error_msg)
            return {
                "status": "error",
                "message": error_msg,
                "timestamp": datetime.now().isoformat()
            }

def run_local_streaming():
    """Function to run streaming ETL locally for testing"""
    print("Running streaming ETL locally...")
    result = run_streaming_etl_pipeline(lookback_days=3, force_full_refresh=False)  # Incremental by default
    print(f"Local streaming ETL result: {result}")
    return result

if __name__ == "__main__":
    # Run locally when script is executed directly
    import argparse
    
    parser = argparse.ArgumentParser(description='Run streaming ETL pipeline')
    parser.add_argument('--lookback_days', type=int, default=3, help='Number of days to look back for incremental processing')
    parser.add_argument('--force_full_refresh', action='store_true', help='Force full refresh for all tables')
    parser.add_argument('--chunk_size', type=int, help='Override default chunk size (rows per chunk). Example: 10000, 50000, 100000')
    parser.add_argument('--table', type=str, help='Process only this specific table (format: database.table, e.g., plex.factcabecera or quantio.productos)')
    parser.add_argument('--mysql_timeout', type=int, help='MySQL query timeout in seconds (default: 300 for data queries, 5 for counts). Example: 600 for 10 minutes')
    
    args = parser.parse_args()
    
    if args.table:
        # Validate table format
        if '.' not in args.table:
            print(f"❌ Error: Table must be in format 'database.table' (e.g., 'plex.factcabecera')")
            print(f"   You provided: '{args.table}'")
            sys.exit(1)
        db, table = args.table.split('.', 1)
        if db not in ['plex', 'quantio']:
            print(f"❌ Error: Database must be 'plex' or 'quantio', got '{db}'")
            sys.exit(1)
    
    print(f"Running streaming ETL locally:")
    print(f"  - lookback_days: {args.lookback_days}")
    print(f"  - force_full_refresh: {args.force_full_refresh}")
    print(f"  - chunk_size: {args.chunk_size}")
    print(f"  - table: {args.table or 'ALL TABLES'}")
    print(f"  - mysql_timeout: {args.mysql_timeout or 'default (300s data, 5s count)'}")
    
    result = run_streaming_etl_pipeline(
        lookback_days=args.lookback_days, 
        force_full_refresh=args.force_full_refresh,
        chunk_size=args.chunk_size,
        single_table=args.table,
        mysql_timeout=args.mysql_timeout
    )
    print(f"Local streaming ETL result: {result}")