#!/usr/bin/env python3
"""
Script para re-procesar solo las tablas que fallaron (cargaron solo 300K filas)
"""

import os
import sys
import argparse
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.etl.streaming_extractor import StreamingDataExtractor
from src.cloud.bigquery import BigQueryManager

# Tablas que necesitan re-procesamiento (solo cargaron 300K filas)
TABLES_TO_REPROCESS = [
    'asientos_detalle',
    'factcabecera', 
    'factlineas',
    'reccabecera'
]

def reprocess_specific_tables(tables_list: list = None, chunk_size: int = 50000):
    """
    Re-procesa solo las tablas especificadas con full refresh
    
    Args:
        tables_list: Lista de tablas a re-procesar (sin prefijo plex_)
        chunk_size: Tamaño del chunk para el procesamiento
    """
    tables = tables_list or TABLES_TO_REPROCESS
    
    print(f"🔄 REPROCESAMIENTO DE TABLAS FALLIDAS")
    print(f"=" * 60)
    print(f"📋 Tablas a re-procesar: {', '.join(tables)}")
    print(f"📦 Chunk size: {chunk_size:,} filas")
    print(f"🕐 Inicio: {datetime.now()}")
    print(f"=" * 60)
    
    # Initialize components
    extractor = StreamingDataExtractor()
    extractor.override_chunk_size = chunk_size
    bq_manager = BigQueryManager()
    
    results = {}
    total_rows = 0
    
    for table_name in tables:
        try:
            print(f"\n{'='*60}")
            print(f"🔄 Re-procesando tabla: {table_name}")
            print(f"{'='*60}")
            
            # Determinar la base de datos (todas estas son de plex)
            database_name = 'plex'
            bq_table_name = f"plex_{table_name}"
            
            # Forzar TRUNCATE para limpiar datos parciales anteriores
            print(f"🗑️  Truncando tabla existente {bq_table_name}...")
            
            # Extraer y cargar con el nuevo código mejorado
            # Usar el método público extract_and_load_table_streaming
            rows_loaded = extractor.extract_and_load_table_streaming(
                database_name=database_name,
                table_name=table_name,
                bq_table_name=bq_table_name,
                chunk_size=chunk_size,
                truncate_target=True,  # IMPORTANTE: Truncar datos anteriores
                query=None  # Full table extraction
            )
            
            results[table_name] = rows_loaded
            total_rows += rows_loaded
            
            print(f"✅ {table_name}: {rows_loaded:,} filas cargadas")
            
        except Exception as e:
            print(f"❌ Error procesando {table_name}: {str(e)}")
            results[table_name] = 0
    
    # Resumen final
    print(f"\n{'='*60}")
    print(f"📊 RESUMEN DE REPROCESAMIENTO")
    print(f"{'='*60}")
    
    for table, rows in results.items():
        status = "✅" if rows > 300000 else "⚠️"
        print(f"{status} {table}: {rows:,} filas")
    
    print(f"\n📈 Total: {total_rows:,} filas procesadas")
    print(f"🕐 Fin: {datetime.now()}")
    
    return results

def main():
    parser = argparse.ArgumentParser(
        description='Re-procesar tablas que solo cargaron 300K filas'
    )
    parser.add_argument(
        '--tables', 
        nargs='+',
        help='Lista de tablas específicas a re-procesar (sin prefijo plex_)',
        default=TABLES_TO_REPROCESS
    )
    parser.add_argument(
        '--chunk-size',
        type=int,
        default=50000,
        help='Tamaño del chunk (default: 50000)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Solo mostrar qué se haría sin ejecutar'
    )
    
    args = parser.parse_args()
    
    # Set up credentials
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'etl-service-account-key.json'
    
    if args.dry_run:
        print("🔍 DRY RUN - Solo mostrando lo que se haría:")
        print(f"Tablas a procesar: {args.tables}")
        print(f"Chunk size: {args.chunk_size:,}")
        return
    
    # Confirmar antes de proceder
    print(f"⚠️  ATENCIÓN: Se van a re-procesar {len(args.tables)} tablas:")
    for t in args.tables:
        print(f"  - {t}")
    print(f"\nChunk size: {args.chunk_size:,}")
    print("\nEsto TRUNCARÁ los datos existentes y los reemplazará.")
    
    response = input("\n¿Continuar? (s/n): ")
    if response.lower() != 's':
        print("Cancelado.")
        return
    
    # Ejecutar reprocesamiento
    results = reprocess_specific_tables(
        tables_list=args.tables,
        chunk_size=args.chunk_size
    )
    
    # Verificar éxito
    failed = [t for t, r in results.items() if r <= 300000]
    if failed:
        print(f"\n⚠️  Las siguientes tablas aún tienen problemas: {failed}")
        print("Considera usar un chunk_size más pequeño o revisar la conexión.")
    else:
        print(f"\n✅ Todas las tablas se reprocesaron exitosamente!")

if __name__ == "__main__":
    main()