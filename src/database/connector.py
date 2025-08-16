import pymysql
import pandas as pd
from typing import Dict, Any, Optional
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
        self._connections = {}  # Cache connections
    
    def get_mysql_connection(self, database_name: str):
        """Create connection to MySQL database using Secret Manager"""
        try:
            # Get configuration from Secret Manager
            config = self.secret_manager.get_mysql_config(database_name)
            
            connection = pymysql.connect(
                host=config['host'],
                port=int(config['port']),
                user=config['user'],
                password=config['password'],
                database=config['database'],
                charset='utf8',
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=True,
                connect_timeout=60,
                read_timeout=300,
                write_timeout=300
            )
            
            print(f"Successfully connected to {database_name} database")
            return connection
            
        except Exception as e:
            print(f"Error connecting to {database_name} database: {str(e)}")
            raise
    
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
        """Get table information (schema, row count, etc.)"""
        connection = None
        try:
            connection = self.get_mysql_connection(database_name)
            
            with connection.cursor() as cursor:
                # Get table schema
                cursor.execute(f"DESCRIBE {table_name}")
                schema = cursor.fetchall()
                
                # Get row count
                cursor.execute(f"SELECT COUNT(*) as row_count FROM {table_name}")
                count_result = cursor.fetchone()
                row_count = count_result['row_count']
                
                # Get sample data
                cursor.execute(f"SELECT * FROM {table_name} LIMIT 5")
                sample_data = cursor.fetchall()
                
            return {
                'table_name': table_name,
                'database': database_name,
                'schema': schema,
                'row_count': row_count,
                'sample_data': sample_data
            }
            
        except Exception as e:
            print(f"Error getting table info for {database_name}.{table_name}: {str(e)}")
            raise
        finally:
            if connection:
                connection.close()
    
    def extract_table_data(self, database_name: str, table_name: str, 
                          query: Optional[str] = None, limit: Optional[int] = None,
                          chunk_size: Optional[int] = None, max_retries: int = 3) -> pd.DataFrame:
        """Extract data from table as pandas DataFrame with chunking and retries"""
        connection = None
        
        # Get estimated row count if chunking is needed
        if chunk_size is None:
            row_count = self.get_table_row_count(database_name, table_name)
            # Use chunking for large tables (>100k rows)
            if row_count > 100000:
                chunk_size = 50000
                print(f"Large table detected ({row_count:,} rows). Using chunk size: {chunk_size:,}")
        
        try:
            if chunk_size and (query is None or "LIMIT" not in query.upper()):
                # Use chunked extraction for large tables
                return self._extract_table_data_chunked(database_name, table_name, query, chunk_size, max_retries)
            else:
                # Use direct extraction for small tables or custom queries
                return self._extract_table_data_direct(database_name, table_name, query, limit, max_retries)
                
        except Exception as e:
            print(f"Error extracting data from {database_name}.{table_name}: {str(e)}")
            raise
    
    def _extract_table_data_direct(self, database_name: str, table_name: str, 
                                  query: Optional[str] = None, limit: Optional[int] = None,
                                  max_retries: int = 3) -> pd.DataFrame:
        """Direct extraction with retries"""
        connection = None
        
        for attempt in range(max_retries):
            try:
                connection = self.get_mysql_connection(database_name)
                
                if query is None:
                    query = f"SELECT * FROM {table_name}"
                    if limit:
                        query += f" LIMIT {limit}"
                
                print(f"Executing query on {database_name}.{table_name} (attempt {attempt + 1}/{max_retries})...")
                df = pd.read_sql(query, connection)
                print(f"Extracted {len(df)} rows from {database_name}.{table_name}")
                
                return df
                
            except (pymysql.err.OperationalError, pymysql.err.InterfaceError) as e:
                if "timeout" in str(e).lower() or "lost connection" in str(e).lower():
                    print(f"Timeout error on attempt {attempt + 1}: {str(e)}")
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
            finally:
                if connection:
                    connection.close()
                    connection = None
    
    def _extract_table_data_chunked(self, database_name: str, table_name: str, 
                                   query: Optional[str] = None, chunk_size: int = 50000,
                                   max_retries: int = 3) -> pd.DataFrame:
        """Extract large table data in chunks"""
        
        # Get total row count
        total_rows = self.get_table_row_count(database_name, table_name)
        total_chunks = math.ceil(total_rows / chunk_size)
        
        print(f"Extracting {total_rows:,} rows in {total_chunks} chunks of {chunk_size:,}")
        
        all_data = []
        
        for chunk_num in range(total_chunks):
            offset = chunk_num * chunk_size
            
            # Build chunked query
            if query is None:
                chunk_query = f"SELECT * FROM {table_name} LIMIT {chunk_size} OFFSET {offset}"
            else:
                # Modify existing query to add LIMIT and OFFSET
                chunk_query = f"{query} LIMIT {chunk_size} OFFSET {offset}"
            
            print(f"Extracting chunk {chunk_num + 1}/{total_chunks} (rows {offset:,} to {min(offset + chunk_size, total_rows):,})")
            
            # Extract chunk with retries
            chunk_df = self._extract_table_data_direct(database_name, table_name, chunk_query, None, max_retries)
            
            if len(chunk_df) == 0:
                print(f"No more data at chunk {chunk_num + 1}, stopping extraction")
                break
                
            all_data.append(chunk_df)
            
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
        """Get row count for a table (with caching)"""
        connection = None
        try:
            connection = self.get_mysql_connection(database_name)
            
            with connection.cursor() as cursor:
                cursor.execute(f"SELECT COUNT(*) as row_count FROM {table_name}")
                result = cursor.fetchone()
                return result['row_count']
                
        except Exception as e:
            print(f"Error getting row count for {database_name}.{table_name}: {str(e)}")
            # Return a default chunk size if count fails
            return 100000
        finally:
            if connection:
                connection.close()
    
    def list_tables(self, database_name: str) -> list:
        """List all tables in database"""
        connection = None
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
            print(f"Error listing tables in {database_name}: {str(e)}")
            raise
        finally:
            if connection:
                connection.close()


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