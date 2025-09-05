#!/usr/bin/env python3
"""
Script para ejecutar ETL de una sola tabla específica
"""

import os
import sys
import argparse
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.etl.streaming_extractor import StreamingDataExtractor
from src.cloud.bigquery import BigQueryManager

def process_single_table(database_name: str, table_name: str, 
                        chunk_size: int = 50000, 
                        force_truncate: bool = True,
                        mysql_timeout: int = None):
    """
    Procesa una sola tabla específica
    
    Args:
        database_name: Nombre de la base de datos (plex o quantio)
        table_name: Nombre de la tabla (sin prefijo)
        chunk_size: Tamaño del chunk para procesamiento
        force_truncate: Si True, hace TRUNCATE antes de cargar (full refresh)
        mysql_timeout: MySQL query timeout en segundos (opcional)
    """
    print(f"🎯 PROCESAMIENTO DE TABLA INDIVIDUAL")
    print(f"=" * 60)
    print(f"📊 Base de datos: {database_name}")
    print(f"📋 Tabla: {table_name}")
    print(f"📦 Chunk size: {chunk_size:,} filas")
    print(f"🔄 Modo: {'FULL REFRESH (truncate)' if force_truncate else 'APPEND'}")
    if mysql_timeout:
        print(f"⏱️ MySQL timeout: {mysql_timeout} segundos")
    print(f"🕐 Inicio: {datetime.now()}")
    print(f"=" * 60)
    
    # Initialize components with timeout if provided
    extractor = StreamingDataExtractor(mysql_timeout=mysql_timeout)
    extractor.override_chunk_size = chunk_size
    bq_manager = BigQueryManager()
    
    # Determinar nombre de tabla en BigQuery
    bq_table_name = f"{database_name}_{table_name}"
    
    try:
        # Extraer y cargar la tabla
        rows_loaded = extractor.extract_and_load_table_streaming(
            database_name=database_name,
            table_name=table_name,
            bq_table_name=bq_table_name,
            chunk_size=chunk_size,
            truncate_target=force_truncate,
            query=None  # Full table extraction
        )
        
        print(f"\n✅ COMPLETADO: {table_name}")
        print(f"📊 Total filas cargadas: {rows_loaded:,}")
        print(f"🕐 Fin: {datetime.now()}")
        
        return rows_loaded
        
    except Exception as e:
        print(f"\n❌ ERROR procesando {table_name}: {str(e)}")
        return 0

def main():
    parser = argparse.ArgumentParser(
        description='Ejecutar ETL para una sola tabla',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos de uso:
  # Tabla de plex con full refresh
  python run_single_table.py --database plex --table factcabecera
  
  # Tabla de quantio con chunk size específico
  python run_single_table.py --database quantio --table productos --chunk-size 25000
  
  # Tabla sin truncate (append only)
  python run_single_table.py --database plex --table clientes --no-truncate
  
  # Tabla grande con timeout extendido
  python run_single_table.py --database plex --table asientos_detalle --mysql-timeout 600
  
Tablas comunes de plex:
  factcabecera, factlineas, asientos, asientos_detalle, clientes, 
  medicamentos, stock, stocklotes, reccabecera, reclineas
  
Tablas comunes de quantio:
  productos, proveedores, stock, stocklotes, factcabecera
        """
    )
    
    parser.add_argument(
        '--database', '-d',
        required=True,
        choices=['plex', 'quantio'],
        help='Base de datos origen (plex o quantio)'
    )
    
    parser.add_argument(
        '--table', '-t',
        required=True,
        help='Nombre de la tabla (sin prefijo plex_ o quantio_)'
    )
    
    parser.add_argument(
        '--chunk-size', '-c',
        type=int,
        default=50000,
        help='Tamaño del chunk en filas (default: 50000)'
    )
    
    parser.add_argument(
        '--no-truncate',
        action='store_true',
        help='NO truncar la tabla antes de cargar (append mode)'
    )
    
    parser.add_argument(
        '--mysql-timeout',
        type=int,
        help='MySQL query timeout en segundos (default: 300 para datos, 5 para counts). Ejemplo: 600 para 10 minutos'
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
        print("🔍 DRY RUN - Mostrando configuración:")
        print(f"  Base de datos: {args.database}")
        print(f"  Tabla: {args.table}")
        print(f"  Chunk size: {args.chunk_size:,}")
        print(f"  Truncate: {not args.no_truncate}")
        print(f"  MySQL timeout: {args.mysql_timeout or 'default (300s datos, 5s count)'}")
        print(f"  Tabla en BigQuery: {args.database}_{args.table}")
        return
    
    # Confirmar antes de proceder si es full refresh
    if not args.no_truncate:
        print(f"⚠️  ATENCIÓN: Se va a hacer FULL REFRESH de la tabla:")
        print(f"  {args.database}.{args.table} → {args.database}_{args.table}")
        print(f"\nEsto ELIMINARÁ todos los datos existentes y los reemplazará.")
        
        response = input("\n¿Continuar? (s/n): ")
        if response.lower() != 's':
            print("Cancelado.")
            return
    
    # Ejecutar procesamiento
    result = process_single_table(
        database_name=args.database,
        table_name=args.table,
        chunk_size=args.chunk_size,
        force_truncate=not args.no_truncate,
        mysql_timeout=args.mysql_timeout
    )
    
    if result > 0:
        print(f"\n✅ Procesamiento exitoso!")
    else:
        print(f"\n⚠️  El procesamiento falló o no cargó datos.")

if __name__ == "__main__":
    main()