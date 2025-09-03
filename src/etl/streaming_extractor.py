import pandas as pd
from datetime import datetime, timedelta
from ..database.connector import DatabaseConnector
from ..cloud.bigquery import BigQueryManager
from ..utils.config import Config
from ..utils.schema_mapper import SchemaMapper
from ..utils.mysql_structure_generator import MySQLStructureGenerator
import math
import os
import yaml


class StreamingDataExtractor:
    def __init__(self):
        self.db = DatabaseConnector()
        self.bq_manager = BigQueryManager()
        self.config = Config()
        self.structure_generator = MySQLStructureGenerator()
        self.strategy_config = self._load_incremental_strategy()
    
    def _load_incremental_strategy(self):
        """Load incremental strategy configuration from YAML"""
        config_path = os.path.join(os.path.dirname(__file__), '../../config/incremental_strategy.yaml')
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"⚠️  Could not load incremental strategy config: {e}")
            return {}
    
    def get_mysql_tables(self, database_name: str) -> list:
        """Get all tables from MySQL database"""
        try:
            connection = self.db.get_mysql_connection(database_name)
            
            with connection.cursor() as cursor:
                cursor.execute("SHOW TABLES")
                results = cursor.fetchall()
                
                if results:
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
    
    def get_table_strategy(self, database_name: str, table_name: str) -> dict:
        """Get processing strategy for a specific table from YAML config"""
        try:
            db_config = self.strategy_config.get('databases', {}).get(database_name, {})
            table_config = db_config.get('priority_tables', {}).get(table_name, {})
            
            if not table_config:
                # Default strategy for unconfigured tables
                return {
                    'strategy': 'full_refresh',
                    'refresh_frequency': 'every_run',
                    'chunk_size': 100000,
                    'description': f'Unconfigured table - using default full refresh'
                }
            
            return table_config
        except Exception as e:
            print(f"⚠️  Error getting strategy for {database_name}.{table_name}: {e}")
            return {'strategy': 'full_refresh', 'chunk_size': 100000}
    
    def build_incremental_query(self, database_name: str, table_name: str, table_config: dict, lookback_days: int = 3) -> tuple:
        """Build MySQL query and BigQuery delete condition for incremental processing"""
        strategy = table_config.get('strategy')
        
        if strategy == 'full_refresh':
            return f"SELECT * FROM {table_name}", None
            
        # Get custom query or build standard incremental query
        custom_query = table_config.get('custom_query')
        if custom_query:
            mysql_query = custom_query.format(lookback_days=lookback_days)
        else:
            # Standard incremental query using watermark columns
            watermark_columns = table_config.get('watermark_column', [])
            if not watermark_columns:
                # Fallback to full refresh if no watermark columns
                return f"SELECT * FROM {table_name}", None
                
            conditions = []
            for col in watermark_columns:
                conditions.append(f"{col} >= DATE_SUB(CURRENT_DATE(), INTERVAL {lookback_days} DAY)")
            
            where_clause = " OR ".join(conditions)
            mysql_query = f"SELECT * FROM {table_name} WHERE {where_clause}"
        
        # Build BigQuery delete condition with proper type casting
        delete_condition = table_config.get('delete_condition')
        if delete_condition:
            bq_delete_condition = delete_condition.format(lookback_days=lookback_days)
        else:
            # Standard delete condition using watermark columns with CAST for BigQuery
            watermark_columns = table_config.get('watermark_column', [])
            if watermark_columns:
                conditions = []
                for col in watermark_columns:
                    # Cast to DATE for comparison in BigQuery to avoid TIMESTAMP vs DATE issues
                    conditions.append(f"DATE({col}) >= DATE_SUB(CURRENT_DATE(), INTERVAL {lookback_days} DAY)")
                bq_delete_condition = f"WHERE {' OR '.join(conditions)}"
            else:
                bq_delete_condition = None
        
        return mysql_query, bq_delete_condition
    
    def delete_incremental_data_from_bigquery(self, bq_table_name: str, delete_condition: str):
        """Delete incremental data from BigQuery table before INSERT"""
        if not delete_condition:
            return
            
        delete_query = f"DELETE FROM `{self.config.BIGQUERY_PROJECT}.{self.config.BIGQUERY_DATASET}.{bq_table_name}` {delete_condition}"
        
        try:
            print(f"🗑️  Deleting incremental data from {bq_table_name}")
            print(f"   Query: {delete_query}")
            
            query_job = self.bq_manager.client.query(delete_query)
            query_job.result()  # Wait for completion
            
            print(f"✅ Deleted incremental data from {bq_table_name}")
            
        except Exception as e:
            print(f"❌ Error deleting from {bq_table_name}: {e}")
            raise
    
    def extract_and_load_table_streaming(self, database_name: str, table_name: str, 
                                       bq_table_name: str, query: str = None, 
                                       chunk_size: int = 100000, 
                                       truncate_target: bool = False) -> int:
        """Extract data from MySQL table and load directly to BigQuery in chunks"""
        
        print(f"Starting streaming extraction for {database_name}.{table_name} -> {bq_table_name}")
        
        # Create dataset if it doesn't exist
        self.bq_manager.create_dataset_if_not_exists()
        
        # Get MySQL schema and create BigQuery schema
        print(f"Retrieving schema for {database_name}.{table_name}...")
        mysql_columns = self.db.get_table_schema(database_name, table_name)
        
        # Print schema comparison for debugging
        SchemaMapper.print_schema_comparison(f"{database_name}.{table_name}", mysql_columns)
        
        # Update MySQL structure documentation first
        try:
            row_count = self._get_query_row_count(database_name, f"SELECT * FROM {table_name}")
            self.structure_generator.update_table_structure(
                database_name, table_name, mysql_columns, row_count
            )
        except Exception as e:
            print(f"⚠️  MySQL structure update failed, continuing with ETL: {e}")
        
        # Try to get schema from YAML first, fallback to live generation
        try:
            bq_schema = self.structure_generator.get_table_schema_for_bigquery(database_name, table_name)
            if bq_schema:
                print(f"✅ Using schema from mysql_structure.yaml ({len(bq_schema)} fields)")
            else:
                raise Exception("No schema found in YAML")
        except Exception:
            print("⚠️  Using live schema generation as fallback")
            bq_schema = SchemaMapper.create_bigquery_schema(mysql_columns)
        
        # For truncate, we'll use WRITE_TRUNCATE on first chunk
        
        # Get total row count for progress tracking
        total_rows = self._get_query_row_count(database_name, query or f"SELECT * FROM {table_name}")
        total_chunks = math.ceil(total_rows / chunk_size) if total_rows > 0 else 1
        
        print(f"Processing {total_rows:,} rows in {total_chunks} chunks of {chunk_size:,}")
        
        total_loaded = 0
        
        for chunk_num in range(total_chunks):
            offset = chunk_num * chunk_size
            
            # Build chunked query
            if query is None:
                chunk_query = f"SELECT * FROM {table_name} LIMIT {chunk_size} OFFSET {offset}"
            else:
                chunk_query = f"{query} LIMIT {chunk_size} OFFSET {offset}"
            
            print(f"Processing chunk {chunk_num + 1}/{total_chunks} (offset: {offset:,})")
            
            try:
                # Extract chunk
                chunk_df = self.db._extract_table_data_direct(
                    database_name, table_name, chunk_query, max_retries=3
                )
                
                if len(chunk_df) == 0:
                    print(f"No more data at chunk {chunk_num + 1}, stopping")
                    break
                
                # Convert timedelta columns to string for BigQuery TIME fields
                for col in chunk_df.columns:
                    if chunk_df[col].dtype == 'timedelta64[ns]':
                        chunk_df[col] = chunk_df[col].apply(
                            lambda x: str(x).split(' ')[-1] if pd.notna(x) else None
                        )
                        print(f"Converted timedelta column {col} to TIME string format")
                
                # Clean data: remove null bytes and other problematic characters for BigQuery
                for col in chunk_df.columns:
                    if chunk_df[col].dtype == 'object':  # String/text columns
                        # First clean null bytes and encoding issues
                        chunk_df[col] = chunk_df[col].astype(str).str.replace('\x00', '', regex=False)
                        chunk_df[col] = chunk_df[col].str.encode('utf-8', errors='ignore').str.decode('utf-8')
                        # Replace various null representations with actual None
                        chunk_df[col] = chunk_df[col].replace(['nan', 'None', 'null', 'NULL', ''], None)
                        # Convert back to object dtype to handle None properly
                        chunk_df[col] = chunk_df[col].where(chunk_df[col].notna(), None)
                
                # Load chunk directly to BigQuery with proper schema
                write_disposition = 'WRITE_TRUNCATE' if chunk_num == 0 and truncate_target else 'WRITE_APPEND'
                
                # ALWAYS use schema (not just first chunk) - BigQuery needs it for consistency
                self.bq_manager.load_dataframe_to_table(
                    chunk_df, bq_table_name, 
                    write_disposition=write_disposition,
                    schema=bq_schema  # Always use schema!
                )
                
                total_loaded += len(chunk_df)
                print(f"Loaded chunk {chunk_num + 1}: {len(chunk_df):,} rows (total: {total_loaded:,})")
                
            except Exception as e:
                print(f"Error processing chunk {chunk_num + 1}: {str(e)}")
                # Continue with next chunk instead of failing completely
                continue
        
        print(f"Completed streaming extraction: {total_loaded:,} total rows loaded to {bq_table_name}")
        return total_loaded
    
    def _get_query_row_count(self, database_name: str, query: str) -> int:
        """Get row count for a query"""
        connection = None
        try:
            connection = self.db.get_mysql_connection(database_name)
            
            # Wrap query in COUNT to get total rows
            count_query = f"SELECT COUNT(*) as row_count FROM ({query}) as subquery"
            
            with connection.cursor() as cursor:
                cursor.execute(count_query)
                result = cursor.fetchone()
                return result['row_count']
                
        except Exception as e:
            print(f"Error getting query row count: {str(e)}")
            return 100000  # Default estimate
        finally:
            if connection:
                connection.close()
    
    def extract_database_data_streaming(self, database_name: str, lookback_days: int = 3, force_full_refresh: bool = False) -> dict:
        """Extract data from a database using YAML configuration"""
        results = {}
        
        # Get all tables from MySQL
        mysql_tables = self.get_mysql_tables(database_name)
        
        if not mysql_tables:
            print(f"⚠️  No tables found in {database_name}")
            return results
        
        print(f"🚀 Processing {len(mysql_tables)} tables from {database_name} with lookback_days={lookback_days}")
        
        # Define table prefix for BigQuery
        table_prefix = {
            'plex': 'plex_',
            'quantio': 'quantio_'
        }
        prefix = table_prefix.get(database_name, f"{database_name}_")
        
        for table_name in mysql_tables:
            bq_table_name = f"{prefix}{table_name}"
            
            try:
                print(f"\n--- Processing {database_name}.{table_name} -> {bq_table_name} ---")
                
                # Get table strategy from YAML config
                table_config = self.get_table_strategy(database_name, table_name)
                strategy = table_config.get('strategy', 'full_refresh')
                chunk_size = table_config.get('chunk_size', 100000)
                
                print(f"📋 Strategy: {strategy} | Chunk size: {chunk_size:,}")
                print(f"📄 {table_config.get('description', 'No description')}")
                
                # Build query based on strategy
                if force_full_refresh or strategy == 'full_refresh':
                    mysql_query = f"SELECT * FROM {table_name}"
                    delete_condition = None
                    truncate_target = True
                    print(f"🔄 Using FULL REFRESH")
                else:
                    mysql_query, delete_condition = self.build_incremental_query(
                        database_name, table_name, table_config, lookback_days
                    )
                    truncate_target = False
                    print(f"⚡ Using INCREMENTAL (DELETE + INSERT last {lookback_days} days)")
                    print(f"🔍 MySQL Query: {mysql_query[:100]}...")
                    
                    # Delete incremental data from BigQuery BEFORE loading new data
                    if delete_condition:
                        self.delete_incremental_data_from_bigquery(bq_table_name, delete_condition)
                
                # Extract and load data
                rows_loaded = self.extract_and_load_table_streaming(
                    database_name=database_name,
                    table_name=table_name,
                    bq_table_name=bq_table_name,
                    query=mysql_query,
                    chunk_size=chunk_size,
                    truncate_target=truncate_target
                )
                
                results[bq_table_name] = rows_loaded
                print(f"✅ Completed {table_name}: {rows_loaded:,} rows loaded")
                
            except Exception as e:
                print(f"❌ Failed to process {table_name}: {str(e)}")
                results[bq_table_name] = 0
                continue
        
        return results
    
    def extract_all_data_streaming(self, lookback_days: int = 3, force_full_refresh: bool = False) -> dict:
        """Extract data from both databases using YAML configuration"""
        print(f"🚀 Starting streaming data extraction with lookback_days={lookback_days}, force_full_refresh={force_full_refresh}")
        
        all_results = {}
        
        # Extract Plex data
        print("\n=== EXTRACTING PLEX DATA ===")
        plex_results = self.extract_database_data_streaming('plex', lookback_days, force_full_refresh)
        all_results.update(plex_results)
        
        # Extract Quantio data  
        print("\n=== EXTRACTING QUANTIO DATA ===")
        quantio_results = self.extract_database_data_streaming('quantio', lookback_days, force_full_refresh)
        all_results.update(quantio_results)
        
        print("Streaming data extraction completed!")
        print(f"Summary: {sum(all_results.values()):,} total rows loaded across all tables")
        
        return all_results