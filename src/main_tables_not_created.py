#!/usr/bin/env python3
"""
ETL for tables not yet created in BigQuery
Discovers all MySQL tables and processes only those missing in BigQuery
"""

try:
    import functions_framework
    CLOUD_FUNCTIONS_AVAILABLE = True
except ImportError:
    CLOUD_FUNCTIONS_AVAILABLE = False
    print("⚠️  functions_framework not available - running in local mode")

from etl.streaming_extractor import StreamingDataExtractor
from cloud.bigquery import BigQueryManager
from database.connector import DatabaseConnector
from utils.config import Config
from datetime import datetime
from google.cloud.exceptions import NotFound

def get_mysql_tables(database_name: str) -> list:
    """Get all tables from MySQL database"""
    db_connector = DatabaseConnector()
    try:
        connection = db_connector.get_mysql_connection(database_name)
        
        with connection.cursor() as cursor:
            cursor.execute("SHOW TABLES")
            results = cursor.fetchall()
            
            if results:
                # Get the column name (varies by MySQL version)
                column_key = list(results[0].keys())[0]
                tables = [row[column_key] for row in results]
            else:
                tables = []
        
        connection.close()
        print(f"📊 Found {len(tables)} tables in MySQL {database_name}")
        return tables
        
    except Exception as e:
        print(f"❌ Error getting MySQL tables from {database_name}: {e}")
        return []

def get_bigquery_tables(dataset_id: str) -> list:
    """Get all tables from BigQuery dataset"""
    bq_manager = BigQueryManager()
    try:
        dataset_ref = bq_manager.client.dataset(dataset_id)
        tables = list(bq_manager.client.list_tables(dataset_ref))
        table_names = [table.table_id for table in tables]
        
        print(f"📊 Found {len(table_names)} tables in BigQuery {dataset_id}")
        return table_names
        
    except NotFound:
        print(f"⚠️  BigQuery dataset {dataset_id} not found - will create tables in new dataset")
        return []
    except Exception as e:
        print(f"❌ Error getting BigQuery tables from {dataset_id}: {e}")
        return []

def filter_tables_to_process(mysql_tables: list, bigquery_tables: list, database_name: str) -> list:
    """Filter MySQL tables to find those not yet in BigQuery"""
    
    # Define table prefix mapping
    table_prefix = {
        'plex': 'plex_',
        'quantio': 'quantio_'
    }
    
    prefix = table_prefix.get(database_name, f"{database_name}_")
    
    # Find tables that don't exist in BigQuery
    missing_tables = []
    
    for mysql_table in mysql_tables:
        expected_bq_name = f"{prefix}{mysql_table}"
        
        if expected_bq_name not in bigquery_tables:
            missing_tables.append(mysql_table)
        else:
            print(f"✅ Table {mysql_table} already exists in BigQuery as {expected_bq_name}")
    
    print(f"🔍 Found {len(missing_tables)} tables to process: {missing_tables}")
    return missing_tables

def process_missing_tables(database_name: str, missing_tables: list) -> dict:
    """Process all missing tables using streaming ETL"""
    
    streaming_extractor = StreamingDataExtractor()
    results = {}
    
    # Define table prefix for BigQuery
    table_prefix = {
        'plex': 'plex_',
        'quantio': 'quantio_'
    }
    
    prefix = table_prefix.get(database_name, f"{database_name}_")
    
    print(f"\n🚀 Starting ETL for {len(missing_tables)} missing tables from {database_name}")
    
    for i, table_name in enumerate(missing_tables, 1):
        print(f"\n--- Processing table {i}/{len(missing_tables)}: {table_name} ---")
        
        bq_table_name = f"{prefix}{table_name}"
        
        try:
            # Process table with full extraction (since it's new)
            rows_loaded = streaming_extractor.extract_and_load_table_streaming(
                database_name=database_name,
                table_name=table_name,
                bq_table_name=bq_table_name,
                query=None,  # Full table extraction
                chunk_size=100000,
                truncate_target=True  # New table, so truncate is safe
            )
            
            results[bq_table_name] = rows_loaded
            print(f"✅ Completed {table_name}: {rows_loaded:,} rows loaded")
            
        except Exception as e:
            print(f"❌ Failed to process {table_name}: {str(e)}")
            results[bq_table_name] = 0
            # Continue with next table instead of stopping
            continue
    
    return results

def run_missing_tables_etl():
    """Main function to run ETL for missing tables"""
    try:
        print(f"🔍 Starting discovery ETL for missing tables at {datetime.now()}")
        
        config = Config()
        
        # Step 1: Discover tables in both databases
        print("\n=== Step 1: Discovering MySQL tables ===")
        
        # Get tables from both MySQL databases
        plex_tables = get_mysql_tables('plex')
        quantio_tables = get_mysql_tables('quantio') 
        
        # Step 2: Check what's already in BigQuery
        print("\n=== Step 2: Checking BigQuery tables ===")
        bigquery_tables = get_bigquery_tables(config.BIGQUERY_DATASET)
        
        # Step 3: Find missing tables
        print("\n=== Step 3: Finding missing tables ===")
        
        missing_plex = filter_tables_to_process(plex_tables, bigquery_tables, 'plex')
        missing_quantio = filter_tables_to_process(quantio_tables, bigquery_tables, 'quantio')
        
        total_missing = len(missing_plex) + len(missing_quantio)
        
        if total_missing == 0:
            print("🎉 All tables are already created in BigQuery!")
            return {
                "status": "success",
                "message": "No missing tables found",
                "tables_processed": 0,
                "timestamp": datetime.now().isoformat()
            }
        
        print(f"\n📋 Summary:")
        print(f"   - Plex missing tables: {len(missing_plex)}")
        print(f"   - Quantio missing tables: {len(missing_quantio)}")
        print(f"   - Total to process: {total_missing}")
        
        # Step 4: Process missing tables
        print("\n=== Step 4: Processing missing tables ===")
        
        all_results = {}
        
        # Process Plex missing tables
        if missing_plex:
            print(f"\n🔄 Processing {len(missing_plex)} missing Plex tables...")
            plex_results = process_missing_tables('plex', missing_plex)
            all_results.update(plex_results)
        
        # Process Quantio missing tables
        if missing_quantio:
            print(f"\n🔄 Processing {len(missing_quantio)} missing Quantio tables...")
            quantio_results = process_missing_tables('quantio', missing_quantio)
            all_results.update(quantio_results)
        
        # Step 5: Create analytical views if we loaded any data
        if sum(all_results.values()) > 0:
            print("\n=== Step 5: Creating analytical views ===")
            bq_manager = BigQueryManager()
            try:
                bq_manager.create_analytical_views()
                print("✅ Analytical views created successfully")
            except Exception as e:
                print(f"⚠️  Warning: Could not create analytical views: {e}")
        
        # Final summary
        total_rows = sum(all_results.values())
        successful_tables = len([v for v in all_results.values() if v > 0])
        
        print(f"\n🎉 Discovery ETL completed at {datetime.now()}")
        print(f"📊 Summary:")
        print(f"   - Tables processed: {len(all_results)}")
        print(f"   - Successful tables: {successful_tables}")
        print(f"   - Total rows loaded: {total_rows:,}")
        
        return {
            "status": "success",
            "message": f"Processed {successful_tables} new tables with {total_rows:,} total rows",
            "tables_processed": len(all_results),
            "successful_tables": successful_tables,
            "total_rows_loaded": total_rows,
            "table_details": all_results,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        error_msg = f"Discovery ETL failed: {str(e)}"
        print(f"❌ {error_msg}")
        return {
            "status": "error",
            "message": error_msg,
            "timestamp": datetime.now().isoformat()
        }

if CLOUD_FUNCTIONS_AVAILABLE:
    @functions_framework.http
    def missing_tables_etl_cloud_function(request):
        """Cloud Function entry point for missing tables ETL"""
        try:
            result = run_missing_tables_etl()
            return result, 200 if result['status'] == 'success' else 500
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"Cloud Function error: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }, 500

if __name__ == "__main__":
    # Run locally when script is executed directly
    print("🚀 Running Discovery ETL for missing tables...")
    result = run_missing_tables_etl()
    print(f"\n📋 Final result: {result}")