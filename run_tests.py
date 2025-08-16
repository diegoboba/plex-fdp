#!/usr/bin/env python3
"""
Script principal para ejecutar tests desde el directorio raíz
"""

import os
import sys

# Configurar PYTHONPATH
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.join(current_dir, 'src')
sys.path.insert(0, src_dir)

# Configurar variables de entorno básicas
os.environ.setdefault('GCP_PROJECT_ID', 'plex-etl-project')

def test_imports():
    """Test all imports"""
    print("🧪 Testing imports...")
    
    try:
        from database.connector import DatabaseConnector
        print("✅ DatabaseConnector imported")
        
        from database.secret_manager import SecretManager  
        print("✅ SecretManager imported")
        
        from etl.extractor import DataExtractor
        print("✅ DataExtractor imported")
        
        from cloud.storage import StorageManager
        print("✅ StorageManager imported")
        
        from cloud.bigquery import BigQueryManager
        print("✅ BigQueryManager imported")
        
        print("✅ All imports successful!")
        return True
        
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        return False

def test_connections():
    """Test database connections"""
    print("\n🔌 Testing database connections...")
    
    try:
        from database.connector import DatabaseConnector
        
        project_id = os.getenv('GCP_PROJECT_ID')
        if not project_id:
            print("❌ GCP_PROJECT_ID not set")
            return False
            
        db_connector = DatabaseConnector(project_id)
        
        # Test Plex connection
        print("Testing Plex connection...")
        plex_success = db_connector.test_connection('plex')
        
        # Test Quantio connection  
        print("Testing Quantio connection...")
        quantio_success = db_connector.test_connection('quantio')
        
        return plex_success and quantio_success
        
    except Exception as e:
        print(f"❌ Connection test failed: {e}")
        return False

def main():
    """Main test function"""
    print("🚀 Running Plex ETL Tests...\n")
    
    # Test imports first
    if not test_imports():
        print("❌ Import tests failed. Cannot proceed.")
        return
    
    # Test connections if imports work
    if test_connections():
        print("\n✅ All tests passed!")
    else:
        print("\n❌ Some tests failed. Check configuration.")

if __name__ == "__main__":
    main()