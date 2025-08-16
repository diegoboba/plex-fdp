import pandas as pd
from google.cloud import storage
from datetime import datetime
import io
from utils.config import Config

class StorageManager:
    def __init__(self):
        self.config = Config()
        self.client = storage.Client(project=self.config.GCP_PROJECT_ID)
        self.bucket = self.client.bucket(self.config.GCS_BUCKET_NAME)
    
    def upload_dataframe_as_parquet(self, df: pd.DataFrame, table_name: str, 
                                  partition_date: str = None) -> str:
        """Upload DataFrame to GCS as CSV file (Parquet alternative)"""
        # Redirect to CSV since we're not using PyArrow
        return self.upload_dataframe_as_csv(df, table_name, partition_date)
    
    def upload_dataframe_as_csv(self, df: pd.DataFrame, table_name: str, 
                               partition_date: str = None) -> str:
        """Upload DataFrame to GCS as CSV file (alternative format)"""
        try:
            if partition_date is None:
                partition_date = datetime.now().strftime('%Y-%m-%d')
            
            # Create file path with partitioning  
            file_path = f"raw_data/{table_name}/date={partition_date}/{table_name}_{partition_date}.csv"
            
            # Convert DataFrame to CSV bytes
            csv_buffer = io.StringIO()
            df.to_csv(csv_buffer, index=False)
            csv_bytes = csv_buffer.getvalue().encode('utf-8')
            
            # Upload to GCS
            blob = self.bucket.blob(file_path)
            blob.upload_from_string(csv_bytes, content_type='text/csv')
            
            print(f"Uploaded {table_name} to gs://{self.config.GCS_BUCKET_NAME}/{file_path}")
            return f"gs://{self.config.GCS_BUCKET_NAME}/{file_path}"
            
        except Exception as e:
            print(f"Error uploading {table_name}: {str(e)}")
            raise
    
    def upload_all_data(self, data_dict: dict, file_format: str = 'csv') -> dict:
        """Upload all extracted data to GCS"""
        uploaded_files = {}
        partition_date = datetime.now().strftime('%Y-%m-%d')
        
        print(f"Starting upload of {len(data_dict)} tables to GCS...")
        
        for table_name, df in data_dict.items():
            if df.empty:
                print(f"Skipping {table_name} - no data")
                continue
                
            try:
                if file_format.lower() == 'parquet':
                    file_path = self.upload_dataframe_as_parquet(df, table_name, partition_date)
                else:
                    file_path = self.upload_dataframe_as_csv(df, table_name, partition_date)
                
                uploaded_files[table_name] = file_path
                
            except Exception as e:
                print(f"Failed to upload {table_name}: {str(e)}")
                continue
        
        print(f"Upload completed! {len(uploaded_files)} files uploaded.")
        return uploaded_files
    
    def list_files(self, prefix: str = "raw_data/") -> list:
        """List files in GCS bucket"""
        blobs = self.client.list_blobs(self.bucket, prefix=prefix)
        return [blob.name for blob in blobs]
    
    def delete_old_files(self, prefix: str = "raw_data/", days_old: int = 30):
        """Delete files older than specified days"""
        from datetime import timedelta
        
        cutoff_date = datetime.now() - timedelta(days=days_old)
        blobs = self.client.list_blobs(self.bucket, prefix=prefix)
        
        deleted_count = 0
        for blob in blobs:
            if blob.time_created.replace(tzinfo=None) < cutoff_date:
                blob.delete()
                deleted_count += 1
                print(f"Deleted old file: {blob.name}")
        
        print(f"Deleted {deleted_count} old files")