#!/usr/bin/env python3
"""
Script para configurar los secrets de MySQL en Google Secret Manager
"""

import os
import sys

# Agregar el directorio src al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from database.secret_manager import SecretManager

def setup_mysql_secrets():
    """Configure MySQL secrets in Google Secret Manager"""
    
    project_id = input("Ingresa tu GCP Project ID: ")
    
    if not project_id:
        print("❌ Project ID es requerido")
        return
    
    secret_manager = SecretManager(project_id)
    
    print("=== Configurando Secret para Base de Datos PLEX ===")
    
    # Configuración para Plex
    plex_config = {
        "host": input("Plex MySQL Host: "),
        "port": input("Plex MySQL Port (default 3306): ") or "3306",
        "user": input("Plex MySQL User: "),
        "password": input("Plex MySQL Password: "),
        "database": input("Plex Database Name (default 'plex'): ") or "plex"
    }
    
    print("\n=== Configurando Secret para Base de Datos QUANTIO ===")
    
    # Configuración para Quantio
    quantio_config = {
        "host": input("Quantio MySQL Host: "),
        "port": input("Quantio MySQL Port (default 3306): ") or "3306", 
        "user": input("Quantio MySQL User: "),
        "password": input("Quantio MySQL Password: "),
        "database": input("Quantio Database Name (default 'quantio'): ") or "quantio"
    }
    
    try:
        print("\n🔐 Creando secrets en Google Secret Manager...")
        
        # Crear secret para Plex
        print("Creating Plex secret...")
        secret_manager.create_mysql_secret("plex", plex_config)
        
        # Crear secret para Quantio
        print("Creating Quantio secret...")
        secret_manager.create_mysql_secret("quantio", quantio_config)
        
        print("\n✅ Secrets creados exitosamente!")
        print("\nSecrets creados:")
        print("- mysql-plex-config")
        print("- mysql-quantio-config")
        
        print(f"\n🔧 Para usar en tu código, configura la variable de entorno:")
        print(f"export GCP_PROJECT_ID={project_id}")
        
    except Exception as e:
        print(f"❌ Error creando secrets: {str(e)}")

def test_secrets():
    """Test that secrets are properly configured"""
    
    project_id = os.getenv('GCP_PROJECT_ID')
    if not project_id:
        project_id = input("Ingresa tu GCP Project ID: ")
    
    try:
        secret_manager = SecretManager(project_id)
        
        print("🧪 Testing Plex secret...")
        plex_config = secret_manager.get_mysql_config("plex")
        print(f"✅ Plex config retrieved: host={plex_config['host']}, database={plex_config['database']}")
        
        print("🧪 Testing Quantio secret...")
        quantio_config = secret_manager.get_mysql_config("quantio")
        print(f"✅ Quantio config retrieved: host={quantio_config['host']}, database={quantio_config['database']}")
        
        print("\n✅ All secrets are properly configured!")
        
    except Exception as e:
        print(f"❌ Error testing secrets: {str(e)}")

if __name__ == "__main__":
    print("🔐 MySQL Secret Manager Setup")
    print("1. Setup secrets")
    print("2. Test secrets")
    
    choice = input("Selecciona una opción (1 o 2): ")
    
    if choice == "1":
        setup_mysql_secrets()
    elif choice == "2":
        test_secrets()
    else:
        print("Opción inválida")