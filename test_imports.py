#!/usr/bin/env python3
"""
Test script para verificar que los imports funcionan
"""

import os
import sys

# Agregar src al Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

print("🧪 Testing imports...")

try:
    from database.secret_manager import SecretManager
    print("✅ SecretManager import successful")
except ImportError as e:
    print(f"❌ SecretManager import failed: {e}")

try:
    from database.connector import DatabaseConnector
    print("✅ DatabaseConnector import successful")
except ImportError as e:
    print(f"❌ DatabaseConnector import failed: {e}")

try:
    from etl.extractor import DataExtractor
    print("✅ DataExtractor import successful")
except ImportError as e:
    print(f"❌ DataExtractor import failed: {e}")

try:
    from cloud.storage import StorageManager
    print("✅ StorageManager import successful")
except ImportError as e:
    print(f"❌ StorageManager import failed: {e}")

try:
    from cloud.bigquery import BigQueryManager
    print("✅ BigQueryManager import successful")
except ImportError as e:
    print(f"❌ BigQueryManager import failed: {e}")

try:
    from utils.config import Config
    print("✅ Config import successful")
except ImportError as e:
    print(f"❌ Config import failed: {e}")

print("\n✅ Import test completed!")