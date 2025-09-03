from google.cloud import bigquery
from google.cloud.exceptions import NotFound
from ..utils.config import Config

class BigQueryManager:
    def __init__(self):
        self.config = Config()
        self.client = bigquery.Client(project=self.config.GCP_PROJECT_ID)
        self.dataset_id = self.config.BIGQUERY_DATASET
        self.dataset_ref = self.client.dataset(self.dataset_id)
    
    def create_dataset_if_not_exists(self):
        """Create BigQuery dataset if it doesn't exist"""
        try:
            self.client.get_dataset(self.dataset_ref)
            print(f"Dataset {self.dataset_id} already exists")
        except NotFound:
            dataset = bigquery.Dataset(self.dataset_ref)
            dataset.location = "US"  # or your preferred location
            dataset = self.client.create_dataset(dataset)
            print(f"Created dataset {self.dataset_id}")
    
    def create_external_table(self, table_name: str, gcs_path: str, 
                             schema: list = None, file_format: str = 'CSV'):
        """Create external table pointing to GCS files"""
        try:
            table_id = f"{self.config.GCP_PROJECT_ID}.{self.dataset_id}.{table_name}"
            
            # Configure external data source
            external_config = bigquery.ExternalConfig(file_format)
            external_config.source_uris = [f"{gcs_path}/*"]  # All files in the path
            external_config.autodetect = True if schema is None else False
            
            if schema:
                external_config.schema = schema
            
            # Create table
            table = bigquery.Table(table_id)
            table.external_data_configuration = external_config
            
            table = self.client.create_table(table, exists_ok=True)
            print(f"Created external table {table_id}")
            
            return table
            
        except Exception as e:
            print(f"Error creating external table {table_name}: {str(e)}")
            raise
    
    def create_all_external_tables(self, uploaded_files: dict):
        """Create external tables for all uploaded files"""
        self.create_dataset_if_not_exists()
        
        for table_name, file_path in uploaded_files.items():
            # Extract base path (remove specific file name)
            base_path = '/'.join(file_path.split('/')[:-1])
            
            try:
                self.create_external_table(table_name, base_path)
            except Exception as e:
                print(f"Failed to create external table for {table_name}: {str(e)}")
                continue
    
    def run_query(self, query: str) -> bigquery.QueryJob:
        """Execute a BigQuery SQL query"""
        try:
            job = self.client.query(query)
            return job
        except Exception as e:
            print(f"Error running query: {str(e)}")
            raise
    
    def create_view(self, view_name: str, query: str):
        """Create a BigQuery view"""
        try:
            view_id = f"{self.config.GCP_PROJECT_ID}.{self.dataset_id}.{view_name}"
            view = bigquery.Table(view_id)
            view.view_query = query
            
            view = self.client.create_table(view, exists_ok=True)
            print(f"Created view {view_id}")
            return view
            
        except Exception as e:
            print(f"Error creating view {view_name}: {str(e)}")
            raise
    
    # NOTA: Código de analytical views removido - movido a PLAN.md sección "Next Steps"
    # Las views necesitan ser rediseñadas con la estructura actual de datos
    
    def load_dataframe_to_table(self, df, table_name: str, write_disposition: str = 'WRITE_APPEND', 
                               schema: list = None):
        """Load pandas DataFrame directly to BigQuery table with proper schema"""
        try:
            table_id = f"{self.config.GCP_PROJECT_ID}.{self.dataset_id}.{table_name}"
            
            # Configure job settings
            if schema:
                # Use explicit schema - FORCE disable autodetect
                job_config = bigquery.LoadJobConfig(
                    write_disposition=write_disposition,
                    schema=schema,
                    autodetect=False,
                    source_format=bigquery.SourceFormat.CSV,  # Force explicit format
                    skip_leading_rows=0,  # No header row to skip
                    allow_quoted_newlines=True,
                    allow_jagged_rows=False,
                    max_bad_records=0  # Fail on any schema mismatch
                )
                print(f"🔒 FORCING explicit schema with {len(schema)} fields")
                print(f"Schema fields: {[f.name + ':' + f.field_type for f in schema[:5]]}...")
            else:
                # Use autodetect when no schema provided
                job_config = bigquery.LoadJobConfig(
                    write_disposition=write_disposition,
                    autodetect=True
                )
                print("Using autodetect for schema")
            
            # Load DataFrame
            job = self.client.load_table_from_dataframe(df, table_id, job_config=job_config)
            job.result()  # Wait for the job to complete
            
            print(f"Loaded {len(df)} rows to {table_id}")
            return job
            
        except Exception as e:
            print(f"Error loading DataFrame to {table_name}: {str(e)}")
            raise
    
    def create_table_if_not_exists(self, table_name: str, schema: list = None):
        """Create BigQuery table if it doesn't exist"""
        try:
            table_id = f"{self.config.GCP_PROJECT_ID}.{self.dataset_id}.{table_name}"
            
            # Check if table exists
            try:
                self.client.get_table(table_id)
                print(f"Table {table_id} already exists")
                return
            except NotFound:
                pass
            
            # Create table
            table = bigquery.Table(table_id, schema=schema)
            table = self.client.create_table(table)
            print(f"Created table {table_id}")
            return table
            
        except Exception as e:
            print(f"Error creating table {table_name}: {str(e)}")
            raise
    
    def truncate_table(self, table_name: str):
        """Truncate a BigQuery table"""
        try:
            table_id = f"{self.config.GCP_PROJECT_ID}.{self.dataset_id}.{table_name}"
            query = f"DELETE FROM `{table_id}` WHERE TRUE"
            job = self.client.query(query)
            job.result()
            print(f"Truncated table {table_id}")
            
        except Exception as e:
            print(f"Error truncating table {table_name}: {str(e)}")
            raise

    def test_query(self, query: str, limit: int = 10):
        """Test a query with a limit"""
        test_query = f"SELECT * FROM ({query}) LIMIT {limit}"
        job = self.client.query(test_query)
        return job.result()