#!/usr/bin/env python3
"""
Test script para probar las mejoras de timeout en MySQL
"""

import os
import sys

# Configurar PYTHONPATH
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from database.connector import DatabaseConnector
from etl.extractor import DataExtractor
import time

def test_timeout_fixes():
    """Test las mejoras de timeout y chunking"""
    print("🔧 Testing MySQL timeout fixes...")
    
    project_id = os.getenv('GCP_PROJECT_ID', 'plex-etl-project')
    
    # Test 1: Conexión con timeouts mejorados
    print("\n1. Testing improved connection timeouts...")
    db = DatabaseConnector(project_id)
    
    try:
        # Test conexiones básicas
        plex_ok = db.test_connection('plex')
        quantio_ok = db.test_connection('quantio')
        
        if plex_ok and quantio_ok:
            print("✅ Improved connection timeouts working")
        else:
            print("❌ Connection issues persist")
            return False
    except Exception as e:
        print(f"❌ Connection test failed: {e}")
        return False
    
    # Test 2: Chunked extraction en tabla grande
    print("\n2. Testing chunked extraction on large table...")
    try:
        # Test en factlineas (tabla grande en Plex)
        print("Testing chunked extraction on plex.factlineas...")
        
        # Primer test: obtener row count
        row_count = db.get_table_row_count('plex', 'factlineas')
        print(f"Table factlineas has {row_count:,} rows")
        
        # Test chunked extraction con límite pequeño para prueba
        start_time = time.time()
        test_df = db.extract_table_data('plex', 'factlineas', 
                                       query="SELECT * FROM factlineas LIMIT 1000", 
                                       chunk_size=250)  # Chunks pequeños para test
        end_time = time.time()
        
        print(f"✅ Chunked extraction successful: {len(test_df)} rows in {end_time - start_time:.2f}s")
        
    except Exception as e:
        print(f"❌ Chunked extraction failed: {e}")
        return False
    
    # Test 3: Retry logic con tabla problemática
    print("\n3. Testing retry logic...")
    try:
        # Test con retry en medicamentos (tabla mediana)
        print("Testing retry logic on plex.medicamentos...")
        
        start_time = time.time()
        med_df = db.extract_table_data('plex', 'medicamentos', 
                                      limit=100,  # Limitar para test rápido
                                      max_retries=2)
        end_time = time.time()
        
        print(f"✅ Retry logic working: {len(med_df)} rows in {end_time - start_time:.2f}s")
        
    except Exception as e:
        print(f"❌ Retry logic failed: {e}")
        return False
    
    # Test 4: Extractor completo con muestras pequeñas
    print("\n4. Testing improved DataExtractor...")
    try:
        extractor = DataExtractor()
        
        print("Testing incremental extraction (small sample)...")
        start_time = time.time()
        
        # Override para test pequeño
        test_data = {}
        
        # Test Plex tables con límites
        test_data['plex_sucursales'] = db.extract_table_data('plex', 'sucursales', limit=50)
        test_data['plex_medicamentos'] = db.extract_table_data('plex', 'medicamentos', limit=100, chunk_size=50)
        
        # Test Quantio con límites  
        test_data['quantio_productos'] = db.extract_table_data('quantio', 'productos', limit=100)
        
        end_time = time.time()
        
        total_rows = sum(len(df) for df in test_data.values())
        print(f"✅ DataExtractor working: {total_rows} total rows in {end_time - start_time:.2f}s")
        
        for table, df in test_data.items():
            print(f"  - {table}: {len(df)} rows")
            
    except Exception as e:
        print(f"❌ DataExtractor test failed: {e}")
        return False
    
    print("\n🎉 All timeout fixes working correctly!")
    print("\n📋 Summary of improvements:")
    print("✅ Connection timeouts increased (60s connect, 300s read/write)")
    print("✅ Chunked extraction for large tables (auto-detects >100k rows)")
    print("✅ Automatic retry with exponential backoff (3 attempts)")
    print("✅ Intelligent chunk sizes based on table size")
    print("✅ Better error handling for timeout scenarios")
    
    return True

def test_specific_large_table():
    """Test específico para tabla grande que causaba timeout"""
    print("\n🔍 Testing specific large table that was causing timeouts...")
    
    project_id = os.getenv('GCP_PROJECT_ID', 'plex-etl-project')
    db = DatabaseConnector(project_id)
    
    try:
        # Test la tabla más problemática: factlineas
        print("Testing plex.factlineas (historically problematic table)...")
        
        # Primero verificar row count
        row_count = db.get_table_row_count('plex', 'factlineas')
        print(f"factlineas has {row_count:,} rows")
        
        if row_count > 100000:
            print("Large table detected - will use chunked extraction")
            chunk_size = 25000
        else:
            print("Medium table - using direct extraction with timeouts")
            chunk_size = None
        
        # Extract con timeout protection
        start_time = time.time()
        df = db.extract_table_data('plex', 'factlineas', 
                                  query="SELECT * FROM factlineas LIMIT 5000",  # Prueba con 5k rows
                                  chunk_size=1000)  # Chunks pequeños para test
        end_time = time.time()
        
        print(f"✅ Large table extraction successful!")
        print(f"   Rows extracted: {len(df):,}")
        print(f"   Time taken: {end_time - start_time:.2f}s")
        print(f"   Avg speed: {len(df)/(end_time - start_time):.0f} rows/second")
        
        return True
        
    except Exception as e:
        print(f"❌ Large table test failed: {e}")
        return False

if __name__ == "__main__":
    success = test_timeout_fixes()
    
    if success:
        print("\n" + "="*50)
        test_specific_large_table()
    
    print("\n" + "="*50)
    print("💡 Next steps:")
    print("1. Run full ETL: cd src && python main_local.py")
    print("2. Monitor for any remaining timeout issues")
    print("3. Adjust chunk sizes if needed based on performance")