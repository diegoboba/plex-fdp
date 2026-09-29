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
                config = yaml.safe_load(f)
                return config
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
                                       truncate_target: bool = False, initial_offset: int = None) -> int:
        """Extract data from MySQL table and load directly to BigQuery in chunks"""
        
        # ID-based incremental: check config for id_column
        table_config = self.get_table_strategy(database_name, table_name)
        if table_config.get('strategy') == 'id_incremental' and not truncate_target:
            id_column = table_config.get('id_column')
            if id_column:
                return self._extract_id_based_incremental(
                    database_name, table_name, bq_table_name, chunk_size, id_column
                )
        
        # Detect if this is incremental processing
        is_incremental = query and 'WHERE' in query.upper() and ('DATE_SUB' in query.upper() or 'INTERVAL' in query.upper())
        
        if is_incremental:
            print(f"📅 Starting INCREMENTAL extraction for {database_name}.{table_name} -> {bq_table_name}")
        else:
            print(f"Starting streaming extraction for {database_name}.{table_name} -> {bq_table_name}")
        
        if initial_offset:
            print(f"🔄 Resuming from offset: {initial_offset:,} rows")
        
        # Create dataset if it doesn't exist
        self.bq_manager.create_dataset_if_not_exists()
        
        # Get MySQL schema and create BigQuery schema
        print(f"Retrieving schema for {database_name}.{table_name}...")
        mysql_columns = self.db.get_table_schema(database_name, table_name)
        
        # Schema comparison only on first table of the run (reduce logging cost)
        if not hasattr(self, '_schema_printed'):
            self._schema_printed = set()
        if database_name not in self._schema_printed:
            SchemaMapper.print_schema_comparison(f"{database_name}.{table_name}", mysql_columns)
            self._schema_printed.add(database_name)
        
        # Skip MySQL structure documentation update to avoid full table counts
        # This was causing timeouts on large tables like asientos_detalle
        # Structure documentation can be updated separately if needed
        
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
        
        # NEVER do row counts - always process until no more data
        print(f"🔍 Processing data without row count (will extract until no more data)")
        total_rows = -1  # Process until no more data
        
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
            if is_incremental:
                print(f"📅 Processing {total_rows:,} INCREMENTAL rows in {total_chunks} chunks of {chunk_size:,}")
            else:
                print(f"Processing {total_rows:,} rows in {total_chunks} chunks of {chunk_size:,}")
        
        total_loaded = 0
        
        # Calculate starting chunk and offset
        if initial_offset:
            # If resuming from an offset, calculate the starting chunk
            chunk_num = initial_offset // chunk_size
            actual_offset = initial_offset
            print(f"📍 Starting from chunk {chunk_num + 1} at offset {actual_offset:,}")
            
            # Adjust total chunks if we know the total rows
            if total_rows > 0:
                remaining_rows = total_rows - initial_offset
                if remaining_rows <= 0:
                    print(f"⚠️  Initial offset ({initial_offset:,}) >= total rows ({total_rows:,})")
                    return 0
                # Update total chunks based on remaining data
                total_chunks = math.ceil(remaining_rows / chunk_size)
                print(f"Processing remaining {remaining_rows:,} rows in {total_chunks} chunks")
        else:
            chunk_num = 0
            actual_offset = 0
        
        # Process chunks until no more data
        while True:
            if total_chunks != float('inf') and chunk_num >= total_chunks:
                break
                
            # chunk_num already starts at initial_offset // chunk_size when resuming,
            # so only the chunks processed since the resume point advance the offset
            if initial_offset:
                offset = initial_offset + (chunk_num - (initial_offset // chunk_size)) * chunk_size
            else:
                offset = chunk_num * chunk_size
            
            # Build chunked query
            if query is None:
                chunk_query = f"SELECT * FROM {table_name} LIMIT {chunk_size} OFFSET {offset}"
            else:
                chunk_query = f"{query} LIMIT {chunk_size} OFFSET {offset}"
            
            # Adjust chunk display number for resuming
            display_chunk_num = chunk_num + 1 if not initial_offset else chunk_num - (initial_offset // chunk_size) + 1
            print(f"Processing chunk {display_chunk_num}/{total_chunks} (offset: {offset:,})")
            
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
                
                # If we got a full chunk and row count was unknown, continue silently
                
                chunk_df = self._prepare_chunk(chunk_df)

                # Load chunk directly to BigQuery with proper schema
                write_disposition = 'WRITE_TRUNCATE' if chunk_num == 0 and truncate_target else 'WRITE_APPEND'

                self.bq_manager.load_dataframe_to_table(
                    chunk_df, bq_table_name,
                    write_disposition=write_disposition,
                    schema=bq_schema
                )

                total_loaded += len(chunk_df)
                # Only log every 5 chunks or last chunk to reduce Cloud Logging cost
                if chunk_num % 5 == 0 or len(chunk_df) < chunk_size:
                    print(f"Loaded chunk {chunk_num + 1}: {len(chunk_df):,} rows (total: {total_loaded:,})")
                
                # Increment chunk counter
                chunk_num += 1
                
            except Exception as e:
                print(f"Error processing chunk {chunk_num + 1}: {str(e)}")
                # Increment chunk counter even on error to avoid infinite loop
                chunk_num += 1
                # Continue with next chunk instead of failing completely
                continue
        
        if is_incremental:
            print(f"✅ Completed INCREMENTAL extraction: {total_loaded:,} rows loaded to {bq_table_name}")
        else:
            print(f"✅ Completed streaming extraction: {total_loaded:,} total rows loaded to {bq_table_name}")
        return total_loaded
    
    def _extract_id_based_incremental(self, database_name: str, table_name: str,
                                        bq_table_name: str, chunk_size: int,
                                        id_column: str = "IDReceta") -> int:
        """Generic ID-based incremental extraction using MAX(id_column) from BigQuery"""
        print(f"🔑 Starting ID-based incremental extraction for {table_name} (column: {id_column})")

        # Get the last id from BigQuery
        max_id_query = f"""
        SELECT COALESCE(MAX({id_column}), 0) as max_id
        FROM `{self.config.BIGQUERY_PROJECT}.{self.config.BIGQUERY_DATASET}.{bq_table_name}`
        """

        try:
            print(f"📊 Getting MAX({id_column}) from BigQuery...")
            query_job = self.bq_manager.client.query(max_id_query)
            result = query_job.result()

            max_id = 0
            for row in result:
                max_id = row.max_id

            print(f"✅ Last exported {id_column}: {max_id:,}")

            if max_id == 0:
                print(f"⚠️  No data found in BigQuery table {bq_table_name} - starting from {id_column} > 0")
        except Exception as e:
            print(f"⚠️  Could not get MAX({id_column}) from BigQuery (table might not exist): {e}")
            print(f"📋 Starting fresh extraction from {id_column} > 0")
            max_id = 0

        # Build MySQL query using the indexed id column
        mysql_query = f"SELECT * FROM {table_name} WHERE {id_column} > {max_id}"
        print(f"🔍 MySQL query: {mysql_query}")
        
        # Create dataset if it doesn't exist
        self.bq_manager.create_dataset_if_not_exists()
        
        # Get MySQL schema and create BigQuery schema
        print(f"Retrieving schema for {database_name}.{table_name}...")
        mysql_columns = self.db.get_table_schema(database_name, table_name)
        
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
        
        # Process data in chunks without counting
        print(f"🔍 Processing data without row count (will extract until no more data)")
        total_loaded = 0
        chunk_num = 0
        
        while True:
            offset = chunk_num * chunk_size
            chunk_query = f"{mysql_query} ORDER BY {id_column} LIMIT {chunk_size} OFFSET {offset}"
            
            print(f"Processing chunk {chunk_num + 1} (offset: {offset:,})")
            
            try:
                # Extract chunk with timeout
                chunk_df = self.db._extract_table_data_direct(
                    database_name, table_name, chunk_query, 
                    max_retries=3, timeout=self.mysql_data_timeout
                )
                
                if len(chunk_df) == 0:
                    print(f"✅ No more data at chunk {chunk_num + 1} - extraction complete")
                    break
                
                chunk_df = self._prepare_chunk(chunk_df)

                write_disposition = 'WRITE_APPEND'

                self.bq_manager.load_dataframe_to_table(
                    chunk_df, bq_table_name,
                    write_disposition=write_disposition,
                    schema=bq_schema
                )

                total_loaded += len(chunk_df)
                if chunk_num % 5 == 0 or len(chunk_df) < chunk_size:
                    print(f"Loaded chunk {chunk_num + 1}: {len(chunk_df):,} rows (total: {total_loaded:,})")
                
                # Increment chunk counter
                chunk_num += 1
                
            except Exception as e:
                print(f"Error processing chunk {chunk_num + 1}: {str(e)}")
                # Continue with next chunk instead of failing completely
                chunk_num += 1
                continue
        
        print(f"✅ Completed ID-based incremental extraction for {table_name}: {total_loaded:,} new rows loaded")
        return total_loaded
    
    # ------------------------------------------------------------------
    # Shared helpers for chunk preparation
    # ------------------------------------------------------------------
    def _resolve_bq_schema(self, database_name: str, table_name: str) -> list:
        """BigQuery schema from mysql_structure.yaml, falling back to live introspection"""
        try:
            bq_schema = self.structure_generator.get_table_schema_for_bigquery(database_name, table_name)
            if bq_schema:
                return bq_schema
        except Exception:
            pass
        print("⚠️  Using live schema generation as fallback")
        mysql_columns = self.db.get_table_schema(database_name, table_name)
        return SchemaMapper.create_bigquery_schema(mysql_columns)

    @staticmethod
    def _prepare_chunk(chunk_df: pd.DataFrame) -> pd.DataFrame:
        """Normalize a MySQL chunk so BigQuery accepts it (TIME fields, null bytes, null-ish strings)"""
        for col in chunk_df.columns:
            if chunk_df[col].dtype == 'timedelta64[ns]':
                chunk_df[col] = chunk_df[col].apply(
                    lambda x: str(x).split(' ')[-1] if pd.notna(x) else None
                )
        for col in chunk_df.columns:
            if chunk_df[col].dtype == 'object':
                chunk_df[col] = chunk_df[col].astype(str).str.replace('\x00', '', regex=False)
                chunk_df[col] = chunk_df[col].str.encode('utf-8', errors='ignore').str.decode('utf-8')
                chunk_df[col] = chunk_df[col].replace(['nan', 'None', 'null', 'NULL', ''], None)
                chunk_df[col] = chunk_df[col].where(chunk_df[col].notna(), None)
        return chunk_df

    def _bq_scalar(self, query: str, default=0):
        """Run a single-value BigQuery query, returning default on error or NULL"""
        try:
            for row in self.bq_manager.client.query(query).result():
                value = row[0]
                return default if value is None else value
        except Exception as e:
            print(f"⚠️  BigQuery scalar query failed ({e}); using default {default}")
        return default

    def _mysql_scalar(self, database_name: str, query: str, default=0):
        """Run a single-value MySQL query"""
        connection = self.db.get_mysql_connection(database_name, read_timeout=self.mysql_data_timeout)
        with connection.cursor() as cursor:
            cursor.execute(query)
            row = cursor.fetchone()
        if not row:
            return default
        value = list(row.values())[0]
        return default if value is None else value

    def _load_id_windows(self, database_name: str, table_name: str, bq_table_name: str,
                         select_sql: str, id_expr: str, lo: int, hi: int, window: int,
                         bq_schema: list, label: str) -> int:
        """Stream `select_sql` to BigQuery in windows of `window` ids over (lo, hi].

        `select_sql` must end with a WHERE clause (or `WHERE 1=1`) so the id range can be appended.
        Windows are keyed on the primary key, so each MySQL query is a cheap PK range scan
        regardless of how far into the table we are (no OFFSET cost).
        """
        if hi <= lo:
            print(f"   {label}: nothing to load (lo={lo:,} hi={hi:,})")
            return 0

        total_loaded = 0
        window_num = 0
        total_windows = math.ceil((hi - lo) / window)
        cursor_id = lo
        while cursor_id < hi:
            window_hi = min(cursor_id + window, hi)
            window_num += 1
            chunk_query = f"{select_sql} AND {id_expr} > {cursor_id} AND {id_expr} <= {window_hi}"
            try:
                chunk_df = self.db._extract_table_data_direct(
                    database_name, table_name, chunk_query,
                    max_retries=3, timeout=self.mysql_data_timeout
                )
                if len(chunk_df) > 0:
                    chunk_df = self._prepare_chunk(chunk_df)
                    self.bq_manager.load_dataframe_to_table(
                        chunk_df, bq_table_name,
                        write_disposition='WRITE_APPEND',
                        schema=bq_schema
                    )
                    total_loaded += len(chunk_df)
                if window_num % 5 == 0 or window_hi == hi:
                    print(f"   {label}: window {window_num}/{total_windows} "
                          f"({cursor_id:,}-{window_hi:,}] -> {len(chunk_df):,} rows (total {total_loaded:,})")
            except Exception as e:
                # A failed window is a data hole: surface it instead of silently moving on
                print(f"❌ {label}: window ({cursor_id:,}-{window_hi:,}] failed: {e}")
                raise
            cursor_id = window_hi
        return total_loaded

    def _bq_id_list(self, query: str) -> list:
        """Run a BigQuery query whose first column is an integer id; return the ids sorted"""
        try:
            return sorted(int(row[0]) for row in self.bq_manager.client.query(query).result() if row[0] is not None)
        except Exception as e:
            print(f"⚠️  BigQuery id-list query failed ({e}); treating as empty")
            return []

    def _resync_ids(self, database_name: str, table_name: str, bq_table_name: str,
                    select_sql: str, id_expr: str, id_column: str, ids: list,
                    bq_schema: list, label: str, batch: int = 5000) -> int:
        """Delete the given ids from BigQuery and reload them from MySQL, in batches.

        Both sides use PK lookups (`IN (...)` on the id column), so cost is proportional to
        len(ids), not to table size. Delete and reload share the same literal id list so the
        two sides can never drift apart within a run.
        """
        if not ids:
            return 0
        total_loaded = 0
        batches = math.ceil(len(ids) / batch)
        for i in range(batches):
            chunk_ids = ids[i * batch:(i + 1) * batch]
            id_list = ", ".join(str(x) for x in chunk_ids)
            self.delete_incremental_data_from_bigquery(bq_table_name, f"WHERE {id_column} IN ({id_list})")
            chunk_df = self.db._extract_table_data_direct(
                database_name, table_name, f"{select_sql} AND {id_expr} IN ({id_list})",
                max_retries=3, timeout=self.mysql_data_timeout
            )
            if len(chunk_df) > 0:
                chunk_df = self._prepare_chunk(chunk_df)
                self.bq_manager.load_dataframe_to_table(
                    chunk_df, bq_table_name, write_disposition='WRITE_APPEND', schema=bq_schema
                )
                total_loaded += len(chunk_df)
            print(f"   {label}: batch {i + 1}/{batches} ({len(chunk_ids):,} ids) -> {len(chunk_df):,} rows (total {total_loaded:,})")
        return total_loaded

    # ------------------------------------------------------------------
    # hybrid_process strategy (asientos / asientos_detalle)
    # ------------------------------------------------------------------
    def _extract_hybrid_process(self, database_name: str, table_name: str,
                                bq_table_name: str, chunk_size: int, table_config: dict) -> int:
        """Two-phase load for tables whose rows split into an insert-only, chronological
        majority and a small, freely-edited minority (identified by a process column).

        Phase A (auto): rows generated by `auto_processes` are insert-only and their PK is
          chronological, so we load everything with id > MAX(auto id in BigQuery) - id_margin.
          Pure PK range scans in MySQL — no date filters on unindexed columns.
        Phase B (manual): every other row (backdated accounting entries, adjustments, etc.)
          is deleted from BigQuery and reloaded in full. The subset is small (~3% of rows),
          and this is the only way to catch edits/deletes with arbitrary dates.

        For a child table (asientos_detalle) the process column lives in `parent_table`,
        so both phases resolve the process through a JOIN, and phase A is capped at the
        parent's max id in BigQuery so child and parent stay a consistent snapshot.
        """
        id_column = table_config['id_column']
        process_column = table_config['process_column']
        auto_processes = table_config['auto_processes']
        id_margin = int(table_config.get('id_margin', 20000))
        auto_window = int(table_config.get('auto_id_window', chunk_size))
        manual_window = int(table_config.get('manual_id_window', 1000000))
        parent_table = table_config.get('parent_table')

        project = self.config.BIGQUERY_PROJECT
        dataset = self.config.BIGQUERY_DATASET
        bq_full = f"`{project}.{dataset}.{bq_table_name}`"
        auto_list = ", ".join(str(p) for p in auto_processes)

        print(f"🔀 HYBRID extraction for {database_name}.{table_name} -> {bq_table_name}")
        print(f"   auto processes {auto_processes} by {id_column} range | manual subset full reload")

        self.bq_manager.create_dataset_if_not_exists()
        bq_schema = self._resolve_bq_schema(database_name, table_name)

        # --- Resolve how "auto" / "manual" are expressed in MySQL and BigQuery ---
        if parent_table:
            prefix = bq_table_name[:len(bq_table_name) - len(table_name)]  # e.g. "plex_"
            bq_parent = f"`{project}.{dataset}.{prefix}{parent_table}`"
            mysql_select = (f"SELECT t.* FROM {table_name} t "
                            f"INNER JOIN {parent_table} p ON p.{id_column} = t.{id_column} WHERE 1=1")
            mysql_id_expr = f"t.{id_column}"
            mysql_manual_filter = f"(p.{process_column} IS NULL OR p.{process_column} NOT IN ({auto_list}))"
            bq_auto_ids = f"SELECT {id_column} FROM {bq_parent} WHERE {process_column} IN ({auto_list})"
            bq_max_auto_query = (f"SELECT MAX(c.{id_column}) FROM {bq_full} c "
                                 f"WHERE c.{id_column} IN ({bq_auto_ids})")
            bq_manual_delete = f"WHERE {id_column} NOT IN ({bq_auto_ids})"
            # Cap at the parent snapshot already in BigQuery (parent is loaded first in the group)
            hi_bound = int(self._bq_scalar(f"SELECT MAX({id_column}) FROM {bq_parent}", 0))
        else:
            mysql_select = f"SELECT * FROM {table_name} WHERE 1=1"
            mysql_id_expr = id_column
            mysql_manual_filter = f"({process_column} IS NULL OR {process_column} NOT IN ({auto_list}))"
            bq_max_auto_query = f"SELECT MAX({id_column}) FROM {bq_full} WHERE {process_column} IN ({auto_list})"
            bq_manual_delete = f"WHERE {process_column} IS NULL OR {process_column} NOT IN ({auto_list})"
            hi_bound = int(self._mysql_scalar(database_name, f"SELECT MAX({id_column}) FROM {table_name}", 0))

        # ---------------- Phase A: auto rows by id range ----------------
        max_auto_id = int(self._bq_scalar(bq_max_auto_query, 0))
        start_id = max(max_auto_id - id_margin, 0)
        print(f"📍 Phase A (auto): BigQuery max auto {id_column} = {max_auto_id:,} "
              f"-> reloading ({start_id:,}, {hi_bound:,}]")

        if max_auto_id > 0:
            self.delete_incremental_data_from_bigquery(bq_table_name, f"WHERE {id_column} > {start_id}")
        else:
            print("⚠️  No auto rows in BigQuery yet: phase A will load the whole id range")

        rows_auto = self._load_id_windows(
            database_name, table_name, bq_table_name,
            select_sql=mysql_select, id_expr=mysql_id_expr,
            lo=start_id, hi=hi_bound, window=auto_window,
            bq_schema=bq_schema, label="auto"
        )
        print(f"✅ Phase A (auto): {rows_auto:,} rows loaded")

        # ---------------- Phase C: auto rows BigQuery knows are incomplete ----------------
        # Some auto rows are born incomplete and finished later (e.g. a cobranza gets its
        # second line when the payment settles). `stale_ids_query` is a BigQuery query that
        # returns the ids to re-sync — for asientos: auto asientos whose lines don't balance.
        rows_stale = 0
        stale_query = table_config.get('stale_ids_query')
        if stale_query:
            stale_query = stale_query.format(project=project, dataset=dataset)
            stale_ids = self._bq_id_list(
                f"SELECT {id_column} FROM ({stale_query}) WHERE {id_column} <= {start_id}"
            )
            print(f"📍 Phase C (stale auto): {len(stale_ids):,} ids flagged by stale_ids_query")
            rows_stale = self._resync_ids(
                database_name, table_name, bq_table_name,
                select_sql=mysql_select, id_expr=mysql_id_expr, id_column=id_column,
                ids=stale_ids, bq_schema=bq_schema, label="stale"
            )
            print(f"✅ Phase C (stale auto): {rows_stale:,} rows reloaded")

        # ---------------- Phase B: manual subset full reload ----------------
        print(f"📍 Phase B (manual): reloading every row whose {process_column} is not in {auto_processes}")
        self.delete_incremental_data_from_bigquery(bq_table_name, bq_manual_delete)

        rows_manual = self._load_id_windows(
            database_name, table_name, bq_table_name,
            select_sql=f"{mysql_select} AND {mysql_manual_filter}", id_expr=mysql_id_expr,
            lo=0, hi=hi_bound, window=manual_window,
            bq_schema=bq_schema, label="manual"
        )
        print(f"✅ Phase B (manual): {rows_manual:,} rows loaded")

        total = rows_auto + rows_stale + rows_manual
        print(f"✅ Completed HYBRID extraction for {table_name}: {total:,} rows "
              f"(auto {rows_auto:,} + stale {rows_stale:,} + manual {rows_manual:,})")
        return total

    def _get_query_row_count(self, database_name: str, query: str, table_name: str = None) -> int:
        """DEPRECATED - NO ROW COUNTS TO AVOID TIMEOUTS"""
        print(f"⚠️ _get_query_row_count is deprecated - always returning -1 (unknown count)")
        return -1  # Always unknown count to process until no more data
    
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
                elif strategy == 'id_incremental':
                    id_column = table_config.get('id_column')
                    print(f"🔑 Using ID-based incremental for {table_name} (column: {id_column})")
                    mysql_query = None  # Will be handled by _extract_id_based_incremental
                    delete_condition = None
                    truncate_target = False
                elif strategy == 'hybrid_process':
                    rows_loaded = self._extract_hybrid_process(
                        database_name, table_name, bq_table_name, chunk_size, table_config
                    )
                    results[bq_table_name] = rows_loaded
                    print(f"✅ Completed {table_name}: {rows_loaded:,} rows loaded")
                    continue
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
    
    def extract_table_group(self, group_name: str, lookback_days: int = 3, 
                           force_full_refresh: bool = False, override_chunk_size: int = None,
                           mysql_timeout: int = None) -> dict:
        """
        Extract data from a specific group of tables
        
        Args:
            group_name: Name of the table group (high_priority, medium_priority, low_priority, master_data)
            lookback_days: Number of days to look back for incremental processing
            force_full_refresh: Force full refresh for all tables
            override_chunk_size: Override default chunk size
            mysql_timeout: Override default MySQL timeout in seconds
            
        Returns:
            Dictionary with table names and rows loaded
        """
        # Update timeout if provided
        if mysql_timeout:
            self.mysql_data_timeout = mysql_timeout
            self.mysql_count_timeout = min(mysql_timeout, 10)
            print(f"⏱️ Using custom MySQL timeout: {mysql_timeout} seconds")
        
        # Define table groups - aligned with Cloud Scheduler jobs
        # Each group is sized to complete within Cloud Run timeout (1800s)
        table_groups = {
            # Group 1: Heaviest transactional tables with JOINs (~15-20 min incremental)
            'heavy_transactions': [
                'plex.factcabecera',
                'plex.factlineas',
                'plex.asientos',
                'plex.asientos_detalle',
            ],
            # Group 2: Medium transactional tables (~10-15 min incremental)
            'medium_transactions': [
                'plex.factpagos',
                'plex.factlineascostos',
                'plex.factcoberturas',
                'plex.factreglasaplicadas',
                'plex.factlineasbonificaciones',
                'plex.factlineasptesentrega',
                'plex.reccabecera',
                'plex.reclineas',
            ],
            # Group 3: Operational tables - app, orders, purchases (~10 min)
            'operational': [
                'plex.apppedidos',
                'plex.apppedidoslineas',
                'plex.apppedidosmovimientos',
                'plex.apppedidospagos',
                'plex.apppedidoslineasfact',
                'plex.apppedidosestados',
                'plex.apppedidosorigenes',
                'plex.pedidos',
                'plex.pedidoslineas',
                'plex.comprascabecera',
                'plex.comprasdetalle',
                'plex.pagosproveedores',
                'plex.clientes',
            ],
            # Group 4: Catalogs, stock, master data, plex small tables (~10 min)
            'catalogs': [
                'plex.medicamentos',
                'plex.stock',
                'plex.stocklotes',
                'plex.categorizedproducts',
                'plex.ciudades',
                'plex.planes',
                'plex.laboratorios',
                'plex.cuentascontables',
                'plex.obsociales',
                'plex.proveedores',
                'plex.operadores',
                'plex.gastos',
                'plex.clasificadores',
                'plex.categories',
                'plex.categorias',
                'plex.subrubros',
                'plex.sucursales',
                'plex.empresas',
                'plex.rubros',
            ],
            # Group 5: All Quantio tables (~15-20 min due to factlineas 6.2M)
            'quantio': [
                'quantio.factcabecera',
                'quantio.factlineas',
                'quantio.productoscostos',
                'quantio.pedidosfaltantes',
                'quantio.compraslineas',
                'quantio.stocklotes',
                'quantio.ordenescompralineas',
                'quantio.recepcioncompraslineas',
                'quantio.productoscodebars',
                'quantio.productos',
                'quantio.productosproveedores',
                'quantio.comprascabecera',
                'quantio.stock',
                'quantio.comprasarchivos',
                'quantio.laboratorios',
                'quantio.proveedores',
                'quantio.iibb_tipooperaciones',
                'quantio.clientes',
                'quantio.subrubros',
                'quantio.comprobantes_proveedores',
                'quantio.tiposdegastos',
                'quantio.rubros',
            ],
            # Legacy group names (kept for backwards compatibility)
            'high_priority': [
                'plex.factcabecera',
                'plex.factlineas',
                'plex.asientos',
                'plex.asientos_detalle',
                'plex.reccabecera',
                'plex.reclineas',
            ],
            'medium_priority': [
                'plex.factpagos',
                'plex.factlineascostos',
                'plex.factcoberturas',
                'plex.stocklotes',
                'plex.factreglasaplicadas',
                'plex.medicamentos',
                'plex.stock',
                'plex.clientes',
            ],
            'low_priority': [
                'plex.pedidoslineas',
                'plex.factlineasbonificaciones',
                'plex.comprascabecera',
                'plex.comprasdetalle',
                'plex.pagosproveedores',
                'plex.apppedidos',
                'plex.apppedidoslineas',
                'plex.apppedidosmovimientos',
            ],
            'master_data': [
                'plex.ciudades',
                'plex.planes',
                'plex.laboratorios',
                'plex.cuentascontables',
                'plex.obsociales',
                'plex.proveedores',
                'plex.operadores',
                'plex.gastos',
                'plex.clasificadores',
                'plex.categories',
                'plex.categorias',
                'plex.sucursales',
                'plex.empresas',
                'plex.rubros',
            ],
        }
        
        # Get tables for the specified group
        if group_name not in table_groups:
            print(f"❌ Invalid group name: {group_name}")
            print(f"   Valid groups: {', '.join(table_groups.keys())}")
            return {}
        
        tables_to_process = table_groups[group_name]
        print(f"🎯 Processing {len(tables_to_process)} tables in group '{group_name}':")
        for table in tables_to_process:
            print(f"   - {table}")
        
        # Process each table
        results = {}
        for idx, table_spec in enumerate(tables_to_process, 1):
            print(f"\n{'='*80}")
            print(f"Processing table {idx}/{len(tables_to_process)}: {table_spec}")
            print(f"{'='*80}")
            
            try:
                table_results = self.extract_single_table(
                    table_spec=table_spec,
                    lookback_days=lookback_days,
                    force_full_refresh=force_full_refresh,
                    override_chunk_size=override_chunk_size,
                    mysql_timeout=mysql_timeout
                )
                results.update(table_results)
            except Exception as e:
                print(f"❌ Error processing {table_spec}: {e}")
                # Continue with next table instead of failing completely
                continue
        
        # Summary
        print(f"\n{'='*80}")
        print(f"Group '{group_name}' processing completed:")
        print(f"  - Tables processed: {len(results)}/{len(tables_to_process)}")
        print(f"  - Total rows loaded: {sum(results.values()):,}")
        print(f"{'='*80}")
        
        return results
    
    def _build_incremental_queries(self, database_name: str, table_name: str, 
                                  table_config: dict, lookback_days: int) -> tuple:
        """
        Build MySQL query and BigQuery delete condition for incremental processing
        
        Args:
            database_name: Database name (plex or quantio)
            table_name: Table name
            table_config: Table configuration from YAML
            lookback_days: Number of days to look back
            
        Returns:
            Tuple of (mysql_query, bq_delete_condition)
        """
        # Check if table has custom_query defined
        if 'custom_query' in table_config and table_config['custom_query']:
            mysql_query = table_config['custom_query'].replace('{lookback_days}', str(lookback_days))
        else:
            # Build query based on watermark columns
            watermark_columns = table_config.get('watermark_column', [])
            if not watermark_columns:
                # No watermark columns - return full table query
                mysql_query = f"SELECT * FROM {table_name}"
            else:
                # Ensure watermark_columns is a list
                if not isinstance(watermark_columns, list):
                    watermark_columns = [watermark_columns]
                
                # Build WHERE conditions for each watermark column
                conditions = []
                for col in watermark_columns:
                    # Handle different column types
                    if 'fecha' in col.lower() or 'date' in col.lower() or 'emision' in col.lower():
                        conditions.append(f"{col} >= DATE_SUB(CURRENT_DATE(), INTERVAL {lookback_days} DAY)")
                    else:
                        conditions.append(f"DATE({col}) >= DATE_SUB(CURRENT_DATE(), INTERVAL {lookback_days} DAY)")
                
                # Combine conditions with OR
                where_clause = " OR ".join(f"({cond})" for cond in conditions)
                mysql_query = f"SELECT * FROM {table_name} WHERE {where_clause}"
        
        # Build BigQuery delete condition
        if 'delete_condition' in table_config and table_config['delete_condition']:
            bq_delete_condition = table_config['delete_condition'].replace('{lookback_days}', str(lookback_days))
        else:
            # Build delete condition based on watermark columns
            watermark_columns = table_config.get('watermark_column', [])
            if not watermark_columns:
                bq_delete_condition = None
            else:
                # Ensure watermark_columns is a list
                if not isinstance(watermark_columns, list):
                    watermark_columns = [watermark_columns]
                
                # Build WHERE conditions for delete
                # Always use DATE() wrapper to handle both DATE and TIMESTAMP columns in BigQuery
                conditions = []
                for col in watermark_columns:
                    conditions.append(f"DATE({col}) >= DATE_SUB(CURRENT_DATE(), INTERVAL {lookback_days} DAY)")
                
                # Combine conditions with OR
                bq_delete_condition = " OR ".join(f"({cond})" for cond in conditions)
                if bq_delete_condition:
                    bq_delete_condition = f"WHERE {bq_delete_condition}"
        
        return mysql_query, bq_delete_condition
    
    def _delete_incremental_data(self, bq_table_name: str, delete_condition: str):
        """
        Delete incremental data from BigQuery table
        
        Args:
            bq_table_name: BigQuery table name
            delete_condition: WHERE clause for deletion
        """
        try:
            if not delete_condition:
                return
            
            # Build delete query
            project_id = os.environ.get('GCP_PROJECT_ID', 'plex-etl-project')
            dataset_id = 'plex_analytics'
            
            # First, count rows to be deleted
            if delete_condition.strip().upper().startswith('WHERE'):
                count_query = f"SELECT COUNT(*) as cnt FROM `{project_id}.{dataset_id}.{bq_table_name}` {delete_condition}"
                delete_query = f"DELETE FROM `{project_id}.{dataset_id}.{bq_table_name}` {delete_condition}"
            else:
                count_query = f"SELECT COUNT(*) as cnt FROM `{project_id}.{dataset_id}.{bq_table_name}` WHERE {delete_condition}"
                delete_query = f"DELETE FROM `{project_id}.{dataset_id}.{bq_table_name}` WHERE {delete_condition}"
            
            from google.cloud import bigquery
            client = bigquery.Client(project=project_id)
            
            # Count rows to be deleted
            rows_to_delete = 0
            try:
                count_result = client.query(count_query).result()
                for row in count_result:
                    rows_to_delete = row.cnt
                print(f"🗑️  Found {rows_to_delete:,} rows to delete from {bq_table_name}")
            except Exception as count_error:
                print(f"⚠️  Could not count rows to delete: {count_error}")
                print(f"    Proceeding with delete anyway...")
            
            # Execute delete query
            print(f"Executing delete: {delete_query[:200]}...")  # Show first 200 chars
            job = client.query(delete_query)
            result = job.result()  # Wait for completion
            
            # Get actual deleted row count from job statistics
            deleted_rows = job.num_dml_affected_rows
            if deleted_rows is not None:
                print(f"✅ Deleted {deleted_rows:,} incremental rows from {bq_table_name}")
            else:
                print(f"✅ Deleted incremental data from {bq_table_name} (rows deleted: {rows_to_delete:,} estimated)")
            
        except Exception as e:
            print(f"❌ Error deleting from {bq_table_name}: {e}")
            # Don't raise - continue with insertion
    
    def extract_single_table(self, table_spec: str, lookback_days: int = 3, 
                            force_full_refresh: bool = False, override_chunk_size: int = None,
                            mysql_timeout: int = None, initial_offset: int = None) -> dict:
        """
        Extract data from a single specific table
        
        Args:
            table_spec: Table specification in format 'database.table' (e.g., 'plex.factcabecera')
            lookback_days: Number of days to look back for incremental processing
            force_full_refresh: Force full refresh for the table
            override_chunk_size: Override default chunk size from YAML
            mysql_timeout: Override default MySQL timeout in seconds
            initial_offset: Starting row offset for data extraction (useful for resuming failed loads)
        
        Returns:
            Dictionary with table name and rows loaded
        """
        # Update timeout if provided
        if mysql_timeout:
            self.mysql_data_timeout = mysql_timeout
            self.mysql_count_timeout = min(mysql_timeout, 10)  # Max 10s for counts
            print(f"⏱️ Using custom MySQL timeout: {mysql_timeout} seconds")
        
        # Validate initial_offset usage
        if initial_offset and not force_full_refresh:
            print(f"⚠️  Warning: initial_offset is recommended with --force_full_refresh")
            print(f"    Incremental processing with offset may cause data inconsistencies")
        
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
                    query=None,
                    initial_offset=initial_offset
                )
            elif strategy == 'hybrid_process':
                rows_loaded = self._extract_hybrid_process(
                    database_name, table_name, bq_table_name, chunk_size, table_config
                )
            else:
                # Special handling for reccabecera and reclineas - no DELETE, uses ID-based incremental
                if table_name.lower() in ['reccabecera', 'reclineas']:
                    print(f"🔑 Using special ID-based incremental for {table_name} (no DELETE)")
                    rows_loaded = self.extract_and_load_table_streaming(
                        database_name=database_name,
                        table_name=table_name,
                        bq_table_name=bq_table_name,
                        chunk_size=chunk_size,
                        truncate_target=False,
                        query=None,  # Will be handled by special method
                        initial_offset=initial_offset
                    )
                else:
                    # Standard incremental processing
                    mysql_query, bq_delete_condition = self._build_incremental_queries(
                        database_name, table_name, table_config, lookback_days
                    )
                    
                    # Delete old data from BigQuery (skip if resuming with offset)
                    if bq_delete_condition and not initial_offset:
                        print(f"🗑️  Deleting incremental data from {bq_table_name}")
                        print(f"   Query: {bq_delete_condition}")
                        self._delete_incremental_data(bq_table_name, bq_delete_condition)
                    elif initial_offset:
                        print(f"🔄 Skipping data deletion (resuming from offset {initial_offset:,})")
                    
                    # Load new data
                    rows_loaded = self.extract_and_load_table_streaming(
                        database_name=database_name,
                        table_name=table_name,
                        bq_table_name=bq_table_name,
                        chunk_size=chunk_size,
                        truncate_target=False,
                        query=mysql_query,
                        initial_offset=initial_offset
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