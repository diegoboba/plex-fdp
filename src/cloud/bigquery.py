from google.cloud import bigquery
from google.cloud.exceptions import NotFound
from utils.config import Config

class BigQueryManager:
    def __init__(self):
        self.config = Config()
        self.client = bigquery.Client(project=self.config.GCP_PROJECT_ID)
        self.dataset_id = self.config.BIGQUERY_DATASET
        self.dataset_ref = self.client.dataset(self.dataset_id)
    
    def create_dataset_if_not_exists(self):
        """Create BigQuery dataset if it doesn't exist"""
        try:
            self.client.get_dataset(self.dataset_ref)
            print(f"Dataset {self.dataset_id} already exists")
        except NotFound:
            dataset = bigquery.Dataset(self.dataset_ref)
            dataset.location = "US"  # or your preferred location
            dataset = self.client.create_dataset(dataset)
            print(f"Created dataset {self.dataset_id}")
    
    def create_external_table(self, table_name: str, gcs_path: str, 
                             schema: list = None, file_format: str = 'CSV'):
        """Create external table pointing to GCS files"""
        try:
            table_id = f"{self.config.GCP_PROJECT_ID}.{self.dataset_id}.{table_name}"
            
            # Configure external data source
            external_config = bigquery.ExternalConfig(file_format)
            external_config.source_uris = [f"{gcs_path}/*"]  # All files in the path
            external_config.autodetect = True if schema is None else False
            
            if schema:
                external_config.schema = schema
            
            # Create table
            table = bigquery.Table(table_id)
            table.external_data_configuration = external_config
            
            table = self.client.create_table(table, exists_ok=True)
            print(f"Created external table {table_id}")
            
            return table
            
        except Exception as e:
            print(f"Error creating external table {table_name}: {str(e)}")
            raise
    
    def create_all_external_tables(self, uploaded_files: dict):
        """Create external tables for all uploaded files"""
        self.create_dataset_if_not_exists()
        
        for table_name, file_path in uploaded_files.items():
            # Extract base path (remove specific file name)
            base_path = '/'.join(file_path.split('/')[:-1])
            
            try:
                self.create_external_table(table_name, base_path)
            except Exception as e:
                print(f"Failed to create external table for {table_name}: {str(e)}")
                continue
    
    def run_query(self, query: str) -> bigquery.QueryJob:
        """Execute a BigQuery SQL query"""
        try:
            job = self.client.query(query)
            return job
        except Exception as e:
            print(f"Error running query: {str(e)}")
            raise
    
    def create_view(self, view_name: str, query: str):
        """Create a BigQuery view"""
        try:
            view_id = f"{self.config.GCP_PROJECT_ID}.{self.dataset_id}.{view_name}"
            view = bigquery.Table(view_id)
            view.view_query = query
            
            view = self.client.create_table(view, exists_ok=True)
            print(f"Created view {view_id}")
            return view
            
        except Exception as e:
            print(f"Error creating view {view_name}: {str(e)}")
            raise
    
    def create_analytical_views(self):
        """Create analytical views based on the existing SQL logic"""
        
        # View 1: Facturas con líneas consolidadas (based on factlineascab)
        facturas_view_query = f"""
        CREATE OR REPLACE VIEW `{self.config.GCP_PROJECT_ID}.{self.dataset_id}.v_facturas_lineas` AS
        SELECT 
            fl.*,
            fc.emision,
            fc.tipo,
            fc.sucursal,
            fc.hora,
            DATETIME_ADD(
                DATETIME_ADD(fc.emision, INTERVAL EXTRACT(HOUR FROM fc.hora) HOUR),
                INTERVAL EXTRACT(MINUTE FROM fc.hora) MINUTE
            ) AS emision_fecha_hora
        FROM `{self.config.GCP_PROJECT_ID}.{self.dataset_id}.plex_factlineas` fl 
        LEFT JOIN `{self.config.GCP_PROJECT_ID}.{self.dataset_id}.plex_factcabecera` fc 
            ON fc.IDComprobante = fl.IDComprobante
        """
        
        # View 2: Pedidos con líneas consolidadas (based on pedidoslineascab)
        pedidos_view_query = f"""
        CREATE OR REPLACE VIEW `{self.config.GCP_PROJECT_ID}.{self.dataset_id}.v_pedidos_lineas` AS
        SELECT 
            pl.*,
            p.sucursal,
            DATETIME_ADD(
                DATETIME_ADD(p.FechaDesde, INTERVAL EXTRACT(HOUR FROM p.HoraDesde) HOUR),
                INTERVAL EXTRACT(MINUTE FROM p.HoraDesde) MINUTE
            ) AS fecha_desde_comp,
            DATETIME_ADD(
                DATETIME_ADD(p.FechaHasta, INTERVAL EXTRACT(HOUR FROM p.HoraHasta) HOUR),
                INTERVAL EXTRACT(MINUTE FROM p.HoraHasta) MINUTE
            ) AS fecha_hasta_comp
        FROM `{self.config.GCP_PROJECT_ID}.{self.dataset_id}.quantio_plex_pedidoslineas` pl 
        LEFT JOIN `{self.config.GCP_PROJECT_ID}.{self.dataset_id}.quantio_plex_pedidos` p 
            ON pl.IDPedido = p.IDPedido
        """
        
        # View 3: Reporte BI consolidado
        reporte_bi_view_query = f"""
        CREATE OR REPLACE VIEW `{self.config.GCP_PROJECT_ID}.{self.dataset_id}.v_reporte_bi_consolidado` AS
        SELECT
            t.*,
            fc.IDCliente
        FROM `{self.config.GCP_PROJECT_ID}.{self.dataset_id}.quantio_reporte_bi` t 
        LEFT JOIN `{self.config.GCP_PROJECT_ID}.{self.dataset_id}.plex_factcabecera` fc 
            ON t.idcomprobante = fc.IDComprobante
        """
        
        # View 4: Ventas por sucursal y producto
        ventas_view_query = f"""
        CREATE OR REPLACE VIEW `{self.config.GCP_PROJECT_ID}.{self.dataset_id}.v_ventas_analysis` AS
        SELECT 
            s.NombreFantasia as sucursal_nombre,
            m.Producto as producto_nombre,
            m.Laboratorio,
            DATE(fl.emision) as fecha_venta,
            SUM(fl.Cantidad * 
                CASE 
                    WHEN fl.TipoCantidad = 'C' THEN m.Unidades 
                    ELSE 1 
                END
            ) as unidades_vendidas,
            SUM(fl.Total) as total_ventas,
            COUNT(DISTINCT fl.IDComprobante) as num_facturas
        FROM `{self.config.GCP_PROJECT_ID}.{self.dataset_id}.v_facturas_lineas` fl
        LEFT JOIN `{self.config.GCP_PROJECT_ID}.{self.dataset_id}.plex_sucursales` s 
            ON fl.sucursal = s.Sucursal
        LEFT JOIN `{self.config.GCP_PROJECT_ID}.{self.dataset_id}.plex_medicamentos` m
            ON fl.IDProducto = m.CodPlex
        WHERE fl.tipo IN ('FV', 'TK', 'TF')
            AND fl.emision >= DATE_SUB(CURRENT_DATE(), INTERVAL 365 DAY)
        GROUP BY 1, 2, 3, 4
        """
        
        # Execute all view creation queries
        views = [
            ("v_facturas_lineas", facturas_view_query),
            ("v_pedidos_lineas", pedidos_view_query), 
            ("v_reporte_bi_consolidado", reporte_bi_view_query),
            ("v_ventas_analysis", ventas_view_query)
        ]
        
        for view_name, query in views:
            try:
                job = self.run_query(query)
                job.result()  # Wait for completion
                print(f"Created view: {view_name}")
            except Exception as e:
                print(f"Error creating view {view_name}: {str(e)}")
                continue
    
    def test_query(self, query: str, limit: int = 10):
        """Test a query with a limit"""
        test_query = f"SELECT * FROM ({query}) LIMIT {limit}"
        job = self.client.query(test_query)
        return job.result()