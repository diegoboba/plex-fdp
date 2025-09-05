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
    def __init__(self, mysql_timeout: int = None):
        """
        Initialize StreamingDataExtractor with optional MySQL timeout
        
        Args:
            mysql_timeout: Query timeout in seconds (default: 300 for data, 5 for counts)
        """
        self.db = DatabaseConnector()
        self.bq_manager = BigQueryManager()
        self.config = Config()
        self.structure_generator = MySQLStructureGenerator()
        self.strategy_config = self._load_incremental_strategy()
        
        # Store timeout settings
        self.mysql_data_timeout = mysql_timeout or 300  # Default 5 minutes for data queries
        self.mysql_count_timeout = min(mysql_timeout or 5, 10)  # Max 10 seconds for counts
    
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
        total_rows = self._get_query_row_count(
            database_name, 
            query or f"SELECT * FROM {table_name}",
            table_name=table_name
        )
        
        # Handle different row count scenarios
        if total_rows == -1:
            # Unknown count - process until no more data
            print(f"Processing unknown number of rows in chunks of {chunk_size:,}")
            print(f"⚠️ Will continue extracting until no more data is returned")
            total_chunks = float('inf')  # Unknown number of chunks
        elif total_rows == 0:
            print(f"No rows to process")
            return 0
        else:
            total_chunks = math.ceil(total_rows / chunk_size)
            print(f"Processing {total_rows:,} rows in {total_chunks} chunks of {chunk_size:,}")
        
        total_loaded = 0
        chunk_num = 0
        
        # Process chunks until no more data
        while True:
            if total_chunks != float('inf') and chunk_num >= total_chunks:
                break
                
            offset = chunk_num * chunk_size
            
            # Build chunked query
            if query is None:
                chunk_query = f"SELECT * FROM {table_name} LIMIT {chunk_size} OFFSET {offset}"
            else:
                chunk_query = f"{query} LIMIT {chunk_size} OFFSET {offset}"
            
            print(f"Processing chunk {chunk_num + 1}/{total_chunks} (offset: {offset:,})")
            
            try:
                # Extract chunk with timeout
                chunk_df = self.db._extract_table_data_direct(
                    database_name, table_name, chunk_query, 
                    max_retries=3, timeout=self.mysql_data_timeout
                )
                
                if len(chunk_df) == 0:
                    if total_rows == -1:
                        print(f"✅ No more data at chunk {chunk_num + 1} - extraction complete")
                    else:
                        print(f"No more data at chunk {chunk_num + 1}, stopping")
                    break
                
                # If we got a full chunk and row count was unknown, continue
                if len(chunk_df) == chunk_size and total_rows == -1:
                    print(f"📦 Full chunk received, continuing to next chunk...")
                
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
                chunk_display = f"{chunk_num + 1}/{total_chunks}" if total_chunks != float('inf') else f"{chunk_num + 1}"
                print(f"Loaded chunk {chunk_display}: {len(chunk_df):,} rows (total: {total_loaded:,})")
                
                # Increment chunk counter
                chunk_num += 1
                
            except Exception as e:
                print(f"Error processing chunk {chunk_num + 1}: {str(e)}")
                # Increment chunk counter even on error to avoid infinite loop
                chunk_num += 1
                # Continue with next chunk instead of failing completely
                continue
        
        print(f"Completed streaming extraction: {total_loaded:,} total rows loaded to {bq_table_name}")
        return total_loaded
    
    def _get_query_row_count(self, database_name: str, query: str, table_name: str = None) -> int:
        """Get row count for a query with fallback to estimated count"""
        connection = None
        try:
            connection = self.db.get_mysql_connection(database_name)
            
            # First try: Simple COUNT with timeout
            count_query = f"SELECT COUNT(*) as row_count FROM ({query}) as subquery"
            
            with connection.cursor() as cursor:
                # Set timeout for count queries (configurable, with fallback for older MySQL)
                try:
                    timeout_ms = self.mysql_count_timeout * 1000
                    cursor.execute(f"SET SESSION MAX_EXECUTION_TIME={timeout_ms}")
                    print(f"⏱️ Count timeout set to {self.mysql_count_timeout} seconds")
                except Exception as e:
                    if "Unknown system variable" in str(e):
                        print(f"⚠️ MySQL version doesn't support MAX_EXECUTION_TIME, using default timeout for counts")
                    else:
                        print(f"⚠️ Could not set count timeout: {e}")
                
                cursor.execute(count_query)
                result = cursor.fetchone()
                actual_count = result['row_count']
                print(f"✅ Got exact row count: {actual_count:,}")
                return actual_count
                
        except Exception as e:
            print(f"⚠️ Error getting exact row count: {str(e)}")
            
            # Fallback: Try to get estimated count from information_schema
            if table_name:
                try:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "SELECT TABLE_ROWS FROM INFORMATION_SCHEMA.TABLES "
                            "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s",
                            (database_name, table_name)
                        )
                        result = cursor.fetchone()
                        if result and result['TABLE_ROWS']:
                            estimated = result['TABLE_ROWS']
                            print(f"📊 Using estimated row count from INFORMATION_SCHEMA: {estimated:,}")
                            # Add 20% buffer to ensure we don't miss rows
                            return int(estimated * 1.2)
                except Exception as e2:
                    print(f"⚠️ Could not get estimated count: {e2}")
            
            # Final fallback: Return -1 to signal unknown count
            print(f"⚠️ Row count unknown - will process until no more data")
            return -1
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
                # Use override chunk size if provided, otherwise use config or default
                if hasattr(self, 'override_chunk_size') and self.override_chunk_size:
                    chunk_size = self.override_chunk_size
                else:
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
    
    def extract_single_table(self, table_spec: str, lookback_days: int = 3, 
                            force_full_refresh: bool = False, override_chunk_size: int = None,
                            mysql_timeout: int = None) -> dict:
        """
        Extract data from a single specific table
        
        Args:
            table_spec: Table specification in format 'database.table' (e.g., 'plex.factcabecera')
            lookback_days: Number of days to look back for incremental processing
            force_full_refresh: Force full refresh for the table
            override_chunk_size: Override default chunk size from YAML
            mysql_timeout: Override default MySQL timeout in seconds
        
        Returns:
            Dictionary with table name and rows loaded
        """
        # Update timeout if provided
        if mysql_timeout:
            self.mysql_data_timeout = mysql_timeout
            self.mysql_count_timeout = min(mysql_timeout, 10)  # Max 10s for counts
            print(f"⏱️ Using custom MySQL timeout: {mysql_timeout} seconds")
        # Parse table specification
        if '.' not in table_spec:
            raise ValueError(f"Table must be in format 'database.table', got: {table_spec}")
        
        database_name, table_name = table_spec.split('.', 1)
        
        print(f"🎯 Processing single table: {database_name}.{table_name}")
        
        if override_chunk_size:
            print(f"📦 Using override chunk size: {override_chunk_size:,} rows")
            self.override_chunk_size = override_chunk_size
        else:
            self.override_chunk_size = None
        
        # Get table configuration
        table_config = self.get_table_strategy(database_name, table_name)
        strategy = table_config.get('strategy', 'full_refresh')
        
        # Override strategy if force_full_refresh
        if force_full_refresh:
            strategy = 'full_refresh'
            print(f"🔄 Forcing full refresh for {table_name}")
        
        # Use override chunk size if provided, otherwise use config or default
        if hasattr(self, 'override_chunk_size') and self.override_chunk_size:
            chunk_size = self.override_chunk_size
        else:
            chunk_size = table_config.get('chunk_size', 100000)
        
        print(f"📋 Strategy: {strategy} | Chunk size: {chunk_size:,}")
        
        # Determine BigQuery table name
        bq_table_name = f"{database_name}_{table_name}"
        
        try:
            # Process based on strategy
            if strategy == 'full_refresh' or force_full_refresh:
                # Full refresh - truncate and load all data
                rows_loaded = self.extract_and_load_table_streaming(
                    database_name=database_name,
                    table_name=table_name,
                    bq_table_name=bq_table_name,
                    chunk_size=chunk_size,
                    truncate_target=True,
                    query=None
                )
            else:
                # Incremental processing
                mysql_query, bq_delete_condition = self._build_incremental_queries(
                    database_name, table_name, table_config, lookback_days
                )
                
                # Delete old data from BigQuery
                if bq_delete_condition:
                    print(f"🗑️  Deleting incremental data from {bq_table_name}")
                    print(f"   Query: {bq_delete_condition}")
                    self._delete_incremental_data(bq_table_name, bq_delete_condition)
                
                # Load new data
                rows_loaded = self.extract_and_load_table_streaming(
                    database_name=database_name,
                    table_name=table_name,
                    bq_table_name=bq_table_name,
                    chunk_size=chunk_size,
                    truncate_target=False,
                    query=mysql_query
                )
            
            result = {bq_table_name: rows_loaded}
            print(f"✅ Completed {table_name}: {rows_loaded:,} rows loaded")
            return result
            
        except Exception as e:
            print(f"❌ Failed to process {table_name}: {str(e)}")
            return {bq_table_name: 0}
    
    def extract_all_data_streaming(self, lookback_days: int = 3, force_full_refresh: bool = False, 
                                  override_chunk_size: int = None, mysql_timeout: int = None) -> dict:
        """Extract data from both databases using YAML configuration
        
        Args:
            lookback_days: Number of days to look back for incremental processing
            force_full_refresh: Force full refresh for all tables
            override_chunk_size: Override default chunk size from YAML
            mysql_timeout: Override default MySQL timeout in seconds
        """
        # Update timeout if provided
        if mysql_timeout:
            self.mysql_data_timeout = mysql_timeout
            self.mysql_count_timeout = min(mysql_timeout, 10)  # Max 10s for counts
            print(f"⏱️ Using custom MySQL timeout: {mysql_timeout} seconds")
        print(f"🚀 Starting streaming data extraction with lookback_days={lookback_days}, force_full_refresh={force_full_refresh}")
        if override_chunk_size:
            print(f"📦 Using override chunk size: {override_chunk_size:,} rows")
            self.override_chunk_size = override_chunk_size
        else:
            self.override_chunk_size = None
        
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