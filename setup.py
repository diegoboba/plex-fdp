#!/usr/bin/env python3
"""
Setup script for Plex ETL Project
"""

import subprocess
import sys
import os

def install_requirements():
    """Install Python requirements"""
    print("📦 Installing requirements...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])

def setup_environment():
    """Setup environment variables"""
    print("🔧 Setting up environment...")
    
    # Check if .env exists
    if not os.path.exists('.env'):
        print("Creating .env file from template...")
        subprocess.run(['cp', '.env.example', '.env'])
        print("⚠️  Please edit .env file with your actual values")
    
    # Check required environment variables
    required_vars = ['GCP_PROJECT_ID', 'GOOGLE_APPLICATION_CREDENTIALS']
    for var in required_vars:
        if not os.getenv(var):
            print(f"⚠️  Environment variable {var} not set")

def test_setup():
    """Test the setup"""
    print("🧪 Testing setup...")
    
    try:
        # Add src to Python path for testing
        sys.path.insert(0, 'src')
        
        # Test imports
        from database.connector import DatabaseConnector
        from etl.extractor import DataExtractor
        from cloud.storage import StorageManager
        from cloud.bigquery import BigQueryManager
        
        print("✅ All imports successful")
        
        # Test connections if environment is configured
        project_id = os.getenv('GCP_PROJECT_ID')
        if project_id:
            print("🔌 Testing database connections...")
            subprocess.run([sys.executable, "tests/test_connections.py"])
        else:
            print("⚠️  GCP_PROJECT_ID not set, skipping connection tests")
            
    except ImportError as e:
        print(f"❌ Import error: {e}")
    except Exception as e:
        print(f"❌ Setup test failed: {e}")

def main():
    """Main setup function"""
    print("🚀 Setting up Plex ETL Project...")
    
    try:
        install_requirements()
        setup_environment()
        test_setup()
        
        print("\n✅ Setup completed!")
        print("\n📋 Next steps:")
        print("1. Configure .env file with your values")
        print("2. Run: python scripts/setup_secrets.py")
        print("3. Test: python tests/test_connections.py")
        print("4. Run ETL: python src/main.py")
        
    except Exception as e:
        print(f"❌ Setup failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()