import pandas as pd
from datetime import datetime, timedelta
from database.connector import DatabaseConnector
from utils.config import Config

class DataExtractor:
    def __init__(self):
        self.db = DatabaseConnector()
        self.config = Config()
    
    def extract_plex_data(self, incremental: bool = True, hours_back: int = 12) -> dict:
        """Extract data from Plex database"""
        extracted_data = {}
        
        # Extract factcabecera (invoices header)
        if incremental:
            # Get data from last X hours (12 hours by default)
            datetime_filter = (datetime.now() - timedelta(hours=hours_back)).strftime('%Y-%m-%d %H:%M:%S')
            query = f"""
            SELECT * FROM factcabecera 
            WHERE emision >= '{datetime_filter}'
            OR fecha_modificacion >= '{datetime_filter}'
            """
        else:
            query = "SELECT * FROM factcabecera"
            
        extracted_data['factcabecera'] = self.db.extract_table_data('plex', 'factcabecera', query, chunk_size=100000)
        
        # Extract factlineas (invoice lines) - join with factcabecera for filtering
        if incremental:
            query = f"""
            SELECT fl.* FROM factlineas fl
            INNER JOIN factcabecera fc ON fl.IDComprobante = fc.IDComprobante
            WHERE fc.emision >= '{datetime_filter}'
            """
        else:
            query = "SELECT * FROM factlineas"
            
        extracted_data['factlineas'] = self.db.extract_table_data('plex', 'factlineas', query, chunk_size=100000)
        
        # Extract master data (always full extraction, larger chunks for better performance)
        extracted_data['sucursales'] = self.db.extract_table_data('plex', 'sucursales', chunk_size=100000)
        extracted_data['medicamentos'] = self.db.extract_table_data('plex', 'medicamentos', chunk_size=100000)
        
        return extracted_data
    
    def extract_quantio_data(self, incremental: bool = True) -> dict:
        """Extract data from Quantio database"""
        extracted_data = {}
        
        # Extract plex_pedidos (orders)
        if incremental:
            date_filter = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
            query = f"""
            SELECT * FROM plex_pedidos 
            WHERE FechaDesde >= '{date_filter}'
            """
        else:
            query = "SELECT * FROM plex_pedidos"
            
        extracted_data['plex_pedidos'] = self.db.extract_table_data('quantio', 'plex_pedidos', query, chunk_size=100000)
        
        # Extract plex_pedidoslineas (order lines)
        if incremental:
            query = f"""
            SELECT pl.* FROM plex_pedidoslineas pl
            INNER JOIN plex_pedidos p ON pl.IDPedido = p.IDPedido
            WHERE p.FechaDesde >= '{date_filter}'
            """
        else:
            query = "SELECT * FROM plex_pedidoslineas"
            
        extracted_data['plex_pedidoslineas'] = self.db.extract_table_data('quantio', 'plex_pedidoslineas', query, chunk_size=100000)
        
        # Extract reporte_bi (always incremental based on emision)
        if incremental:
            date_filter = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
            query = f"""
            SELECT * FROM reporte_bi 
            WHERE emision >= '{date_filter}'
            """
        else:
            query = "SELECT * FROM reporte_bi"
            
        extracted_data['reporte_bi'] = self.db.extract_table_data('quantio', 'reporte_bi', query, chunk_size=100000)
        
        return extracted_data
    
    def extract_all_data(self, incremental: bool = True) -> dict:
        """Extract data from both databases"""
        print(f"Starting {'incremental' if incremental else 'full'} data extraction...")
        
        all_data = {}
        
        # Extract Plex data
        print("Extracting Plex data...")
        plex_data = self.extract_plex_data(incremental)
        for table, df in plex_data.items():
            all_data[f'plex_{table}'] = df
            print(f"  - plex_{table}: {len(df)} rows")
        
        # Extract Quantio data  
        print("Extracting Quantio data...")
        quantio_data = self.extract_quantio_data(incremental)
        for table, df in quantio_data.items():
            all_data[f'quantio_{table}'] = df
            print(f"  - quantio_{table}: {len(df)} rows")
        
        print("Data extraction completed!")
        return all_data