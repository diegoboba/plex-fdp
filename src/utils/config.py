import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # MySQL Plex
    MYSQL_PLEX_HOST = os.getenv('MYSQL_PLEX_HOST', 'localhost')
    MYSQL_PLEX_PORT = int(os.getenv('MYSQL_PLEX_PORT', 3306))
    MYSQL_PLEX_USER = os.getenv('MYSQL_PLEX_USER')
    MYSQL_PLEX_PASSWORD = os.getenv('MYSQL_PLEX_PASSWORD')
    MYSQL_PLEX_DATABASE = os.getenv('MYSQL_PLEX_DATABASE', 'plex')
    
    # MySQL Quantio
    MYSQL_QUANTIO_HOST = os.getenv('MYSQL_QUANTIO_HOST', 'localhost')
    MYSQL_QUANTIO_PORT = int(os.getenv('MYSQL_QUANTIO_PORT', 3306))
    MYSQL_QUANTIO_USER = os.getenv('MYSQL_QUANTIO_USER')
    MYSQL_QUANTIO_PASSWORD = os.getenv('MYSQL_QUANTIO_PASSWORD')
    MYSQL_QUANTIO_DATABASE = os.getenv('MYSQL_QUANTIO_DATABASE', 'quantio')
    
    # Google Cloud
    GCP_PROJECT_ID = os.getenv('GCP_PROJECT_ID')
    GCS_BUCKET_NAME = os.getenv('GCS_BUCKET_NAME')
    BIGQUERY_DATASET = os.getenv('BIGQUERY_DATASET', 'plex_analytics')
    
    # Tables to extract
    PLEX_TABLES = [
        'factcabecera',
        'factlineas', 
        'sucursales',
        'medicamentos'
    ]
    
    QUANTIO_TABLES = [
        'plex_pedidos',
        'plex_pedidoslineas',
        'reporte_bi'
    ]