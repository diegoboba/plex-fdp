import pymysql
import pandas as pd
from typing import Dict, Any, Optional, List
from .secret_manager import SecretManager
import os
import time
import math

class DatabaseConnector:
    def __init__(self, project_id: Optional[str] = None):
        self.project_id = project_id or os.getenv('GCP_PROJECT_ID')
        if not self.project_id:
            raise ValueError("GCP_PROJECT_ID must be set in environment or passed as parameter")

        self.secret_manager = SecretManager(self.project_id)
        self._connections = {}  # Persistent connection cache per database
        self._configs = {}  # Cache DB configs to avoid repeated Secret Manager calls

    def __del__(self):
        """Cleanup connections on garbage collection"""
        if hasattr(self, '_connections'):
            self.close_all()

    def _get_or_create_connection(self, database_name: str, read_timeout: int = None):
        """Get existing connection or create new one. Reuses connections per database."""
        actual_read_timeout = read_timeout if read_timeout else 300

        # Check if we have a cached connection that's still alive
        if database_name in self._connections:
            conn = self._connections[database_name]
            try:
                conn.ping(reconnect=False)
                return conn
            except Exception:
                print(f"🔄 Connection to {database_name} lost, reconnecting...")
                try:
                    conn.close()
                except Exception:
                    pass
                del self._connections[database_name]

        # Create new connection
        conn = self._create_connection(database_name, actual_read_timeout)
        self._connections[database_name] = conn
        return conn

    def _create_connection(self, database_name: str, read_timeout: int = 300):
        """Create a fresh MySQL connection"""
        # Cache config to avoid repeated Secret Manager calls
        if database_name not in self._configs:
            self._configs[database_name] = self.secret_manager.get_mysql_config(database_name)

        config = self._configs[database_name]

        connection = pymysql.connect(
            host=config['host'],
            port=int(config['port']),
            user=config['user'],
            password=config['password'],
            database=config['database'],
            charset='utf8',
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True,
            connect_timeout=30,
            read_timeout=read_timeout,
            write_timeout=300
        )

        print(f"Connected to {database_name} database")
        return connection

    def get_mysql_connection(self, database_name: str, read_timeout: int = None):
        """Get a MySQL connection (reuses existing connection when possible)"""
        try:
            return self._get_or_create_connection(database_name, read_timeout)
        except Exception as e:
            print(f"Error connecting to {database_name} database: {str(e)}")
            raise

    def close_all(self):
        """Close all cached connections"""
        for db_name, conn in self._connections.items():
            try:
                conn.close()
                print(f"Closed connection to {db_name}")
            except Exception:
                pass
        self._connections.clear()
    
    def test_connection(self, database_name: str) -> bool:
        """Test connection to database"""
        try:
            connection = self.get_mysql_connection(database_name)
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 as test")
                result = cursor.fetchone()
                print(f"✅ {database_name} connection test: {result}")
            connection.close()
            return True
            
        except Exception as e:
            print(f"❌ {database_name} connection test failed: {str(e)}")
            return False
    
    def get_table_info(self, database_name: str, table_name: str) -> Dict[str, Any]:
        """Get table information (schema only - NO ROW COUNT to avoid timeouts)"""
        try:
            connection = self.get_mysql_connection(database_name)

            with connection.cursor() as cursor:
                # Get table schema
                cursor.execute(f"DESCRIBE {table_name}")
                schema = cursor.fetchall()

                # Get sample data
                cursor.execute(f"SELECT * FROM {table_name} LIMIT 5")
                sample_data = cursor.fetchall()

            return {
                'table_name': table_name,
                'database': database_name,
                'schema': schema,
                'sample_data': sample_data
            }

        except Exception as e:
            self._connections.pop(database_name, None)
            print(f"Error getting table info for {database_name}.{table_name}: {str(e)}")
            raise
    
    def extract_table_data(self, database_name: str, table_name: str, 
                          query: Optional[str] = None, limit: Optional[int] = None,
                          chunk_size: Optional[int] = None, max_retries: int = 3) -> pd.DataFrame:
        """Extract data from table as pandas DataFrame with chunking and retries - NO ROW COUNT"""
        connection = None
        
        # Always use chunking if chunk_size is provided, otherwise use direct extraction
        if chunk_size is None:
            chunk_size = 50000  # Default chunk size
        
        try:
            if chunk_size and (query is None or "LIMIT" not in query.upper()):
                # Use chunked extraction - process until no more data
                return self._extract_table_data_chunked(database_name, table_name, query, chunk_size, max_retries)
            else:
                # Use direct extraction for custom queries with LIMIT
                return self._extract_table_data_direct(database_name, table_name, query, limit, max_retries)
                
        except Exception as e:
            print(f"Error extracting data from {database_name}.{table_name}: {str(e)}")
            raise
    
    def _extract_table_data_direct(self, database_name: str, table_name: str, 
                                  query: Optional[str] = None, limit: Optional[int] = None,
                                  max_retries: int = 3, timeout: int = None) -> pd.DataFrame:
        """Direct extraction with retries and configurable timeout
        
        Args:
            timeout: Query timeout in seconds (optional)
        """
        connection = None
        
        for attempt in range(max_retries):
            try:
                # Use custom timeout for connection if provided
                connection = self.get_mysql_connection(database_name, read_timeout=timeout)
                
                if query is None:
                    query = f"SELECT * FROM {table_name}"
                    if limit:
                        query += f" LIMIT {limit}"
                
                print(f"Executing query on {database_name}.{table_name} (attempt {attempt + 1}/{max_retries})...")
                
                # Use manual cursor approach instead of pd.read_sql to avoid header duplication bug
                with connection.cursor() as cursor:
                    # ALWAYS set timeout to prevent hanging - default 5 minutes
                    actual_timeout = timeout if timeout else 300  # 5 minutes default
                    try:
                        # Try modern MySQL syntax first
                        timeout_ms = actual_timeout * 1000
                        cursor.execute(f"SET SESSION MAX_EXECUTION_TIME={timeout_ms}")
                        print(f"⏱️ Query timeout set to {actual_timeout} seconds")
                    except Exception as e:
                        if "Unknown system variable" in str(e):
                            # Fallback for older MySQL versions - just print warning
                            print(f"⚠️ MySQL version doesn't support MAX_EXECUTION_TIME, using connection timeout")
                        else:
                            print(f"⚠️ Could not set timeout: {e}")
                    
                    print(f"📊 Executing query: {query[:100]}...")
                    cursor.execute(query)
                    print(f"⏳ Fetching results...")
                    results = cursor.fetchall()
                    print(f"✅ Query completed, got {len(results) if results else 0} rows")
                    
                    if results:
                        # Convert to DataFrame manually
                        df = pd.DataFrame(results)
                    else:
                        df = pd.DataFrame()
                
                print(f"Extracted {len(df)} rows from {database_name}.{table_name}")
                
                return df
                
            except (pymysql.err.OperationalError, pymysql.err.InterfaceError) as e:
                # Invalidate cached connection on connection errors
                self._connections.pop(database_name, None)
                if "timeout" in str(e).lower() or "lost connection" in str(e).lower() or "too many connections" in str(e).lower():
                    print(f"Connection error on attempt {attempt + 1}: {str(e)}")
                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt  # Exponential backoff
                        print(f"Retrying in {wait_time} seconds...")
                        time.sleep(wait_time)
                        continue
                raise
            except Exception as e:
                print(f"Unexpected error on attempt {attempt + 1}: {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                raise
    
    def _extract_table_data_chunked(self, database_name: str, table_name: str, 
                                   query: Optional[str] = None, chunk_size: int = 50000,
                                   max_retries: int = 3) -> pd.DataFrame:
        """Extract table data in chunks - NO ROW COUNT, process until no more data"""
        
        print(f"Extracting data in chunks of {chunk_size:,} (will process until no more data)")
        
        all_data = []
        chunk_num = 0
        
        while True:
            offset = chunk_num * chunk_size
            
            # Build chunked query
            if query is None:
                chunk_query = f"SELECT * FROM {table_name} LIMIT {chunk_size} OFFSET {offset}"
            else:
                # Modify existing query to add LIMIT and OFFSET
                chunk_query = f"{query} LIMIT {chunk_size} OFFSET {offset}"
            
            print(f"Extracting chunk {chunk_num + 1} (offset: {offset:,})")
            
            # Extract chunk with retries
            chunk_df = self._extract_table_data_direct(database_name, table_name, chunk_query, None, max_retries)
            
            if len(chunk_df) == 0:
                print(f"No more data at chunk {chunk_num + 1}, stopping extraction")
                break
                
            all_data.append(chunk_df)
            chunk_num += 1
            
            # Small delay between chunks to avoid overwhelming the database
            time.sleep(0.5)
        
        if all_data:
            final_df = pd.concat(all_data, ignore_index=True)
            print(f"Completed chunked extraction: {len(final_df):,} total rows")
            return final_df
        else:
            print("No data extracted")
            return pd.DataFrame()
    
    def get_table_row_count(self, database_name: str, table_name: str) -> int:
        """DEPRECATED - NO LONGER USED to avoid timeouts"""
        print(f"⚠️  get_table_row_count is deprecated - use chunked extraction without counts")
        return -1  # Unknown count
    
    def list_tables(self, database_name: str) -> list:
        """List all tables in database"""
        try:
            connection = self.get_mysql_connection(database_name)

            with connection.cursor() as cursor:
                cursor.execute("SHOW TABLES")
                results = cursor.fetchall()

                # Get the column name (it varies by MySQL version/config)
                if results:
                    column_key = list(results[0].keys())[0]
                    tables = [row[column_key] for row in results]
                else:
                    tables = []

            print(f"Tables in {database_name}: {tables}")
            return tables

        except Exception as e:
            self._connections.pop(database_name, None)
            print(f"Error listing tables in {database_name}: {str(e)}")
            raise
    
    def get_table_schema(self, database_name: str, table_name: str) -> List[Dict]:
        """Get detailed schema information for a table"""
        try:
            connection = self.get_mysql_connection(database_name)

            # Query INFORMATION_SCHEMA to get column details
            schema_query = """
            SELECT
                COLUMN_NAME,
                DATA_TYPE,
                COLUMN_TYPE,
                IS_NULLABLE,
                COLUMN_DEFAULT,
                COLUMN_COMMENT,
                CHARACTER_MAXIMUM_LENGTH,
                NUMERIC_PRECISION,
                NUMERIC_SCALE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
            ORDER BY ORDINAL_POSITION
            """

            with connection.cursor() as cursor:
                # Get the actual database name we're connected to
                cursor.execute("SELECT DATABASE() as current_db")
                current_db_result = cursor.fetchone()
                actual_database = current_db_result['current_db']

                cursor.execute(schema_query, (actual_database, table_name))
                columns = cursor.fetchall()

            print(f"Retrieved schema for {database_name}.{table_name}: {len(columns)} columns")
            return columns

        except Exception as e:
            self._connections.pop(database_name, None)
            print(f"Error getting schema for {database_name}.{table_name}: {str(e)}")
            raise


# Test function for development
def test_connections():
    """Test function to verify both database connections"""
    try:
        project_id = os.getenv('GCP_PROJECT_ID')
        if not project_id:
            print("❌ GCP_PROJECT_ID environment variable not set")
            return
        
        db_connector = DatabaseConnector(project_id)
        
        # Test Plex connection
        print("Testing Plex database connection...")
        plex_success = db_connector.test_connection('plex')
        
        # Test Quantio connection
        print("Testing Quantio database connection...")
        quantio_success = db_connector.test_connection('quantio')
        
        if plex_success and quantio_success:
            print("✅ All database connections successful!")
            
            # List tables in both databases
            print("\n--- Plex Tables ---")
            plex_tables = db_connector.list_tables('plex')
            
            print("\n--- Quantio Tables ---")
            quantio_tables = db_connector.list_tables('quantio')
            
        else:
            print("❌ Some database connections failed")
            
    except Exception as e:
        print(f"❌ Connection test failed: {str(e)}")

if __name__ == "__main__":
    test_connections()