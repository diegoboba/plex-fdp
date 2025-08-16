import json
from google.cloud import secretmanager
from typing import Dict, Any

class SecretManager:
    def __init__(self, project_id: str):
        self.project_id = project_id
        self.client = secretmanager.SecretManagerServiceClient()
    
    def get_secret(self, secret_name: str, version: str = "latest") -> str:
        """Retrieve secret from Google Secret Manager"""
        try:
            name = f"projects/{self.project_id}/secrets/{secret_name}/versions/{version}"
            response = self.client.access_secret_version(request={"name": name})
            return response.payload.data.decode("UTF-8")
        except Exception as e:
            print(f"Error retrieving secret {secret_name}: {str(e)}")
            raise
    
    def get_mysql_config(self, database_name: str) -> Dict[str, Any]:
        """Get MySQL configuration for specified database (plex or quantio)"""
        try:
            secret_name = f"mysql-{database_name.lower()}-config"
            secret_value = self.get_secret(secret_name)
            config = json.loads(secret_value)
            
            required_keys = ['host', 'port', 'user', 'password', 'database']
            for key in required_keys:
                if key not in config:
                    raise ValueError(f"Missing required key '{key}' in {secret_name}")
            
            return config
            
        except Exception as e:
            print(f"Error getting MySQL config for {database_name}: {str(e)}")
            raise
    
    def create_mysql_secret(self, database_name: str, config: Dict[str, Any]):
        """Create or update MySQL secret in Secret Manager"""
        try:
            secret_name = f"mysql-{database_name.lower()}-config"
            secret_value = json.dumps(config, indent=2)
            
            # Create secret if it doesn't exist
            parent = f"projects/{self.project_id}"
            try:
                secret = self.client.create_secret(
                    request={
                        "parent": parent,
                        "secret_id": secret_name,
                        "secret": {"replication": {"automatic": {}}},
                    }
                )
                print(f"Created secret: {secret.name}")
            except Exception:
                print(f"Secret {secret_name} already exists, updating...")
            
            # Add secret version
            secret_path = f"projects/{self.project_id}/secrets/{secret_name}"
            response = self.client.add_secret_version(
                request={
                    "parent": secret_path,
                    "payload": {"data": secret_value.encode("UTF-8")},
                }
            )
            
            print(f"Added secret version: {response.name}")
            return response
            
        except Exception as e:
            print(f"Error creating secret for {database_name}: {str(e)}")
            raise