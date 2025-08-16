#!/usr/bin/env python3
"""
Test script for database connections
"""

import os
import sys

# Agregar el directorio src al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from database.connector import DatabaseConnector

def test_all_connections():
    """Test all database connections"""
    try:
        project_id = os.getenv('GCP_PROJECT_ID')
        if not project_id:
            print("❌ GCP_PROJECT_ID environment variable not set")
            return False
        
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
            
            return True
        else:
            print("❌ Some database connections failed")
            return False
            
    except Exception as e:
        print(f"❌ Connection test failed: {str(e)}")
        return False

if __name__ == "__main__":
    test_all_connections()