#!/usr/bin/env python3
"""
Crear vistas analíticas en BigQuery mientras el ETL corre
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from cloud.bigquery import BigQueryManager
from datetime import datetime

def create_analytical_views():
    """Crear todas las vistas analíticas"""
    print(f"🏗️ Creating analytical views in BigQuery - {datetime.now()}")
    
    try:
        bq = BigQueryManager()
        
        print("📊 Creating analytical views...")
        bq.create_analytical_views()
        
        print("✅ All views created successfully!")
        
        # Test views
        print("\n🧪 Testing views...")
        test_views(bq)
        
    except Exception as e:
        print(f"❌ Error creating views: {e}")
        raise

def test_views(bq_manager):
    """Test que las vistas funcionen"""
    
    test_queries = [
        ("v_facturas_lineas", "SELECT COUNT(*) as total_facturas FROM `{project}.{dataset}.v_facturas_lineas`"),
        ("v_pedidos_lineas", "SELECT COUNT(*) as total_pedidos FROM `{project}.{dataset}.v_pedidos_lineas`"), 
        ("v_reporte_bi_consolidado", "SELECT COUNT(*) as total_reportes FROM `{project}.{dataset}.v_reporte_bi_consolidado`"),
        ("v_ventas_analysis", "SELECT COUNT(*) as total_ventas FROM `{project}.{dataset}.v_ventas_analysis`")
    ]
    
    for view_name, query_template in test_queries:
        try:
            query = query_template.format(
                project=bq_manager.config.GCP_PROJECT_ID,
                dataset=bq_manager.config.BIGQUERY_DATASET
            )
            
            print(f"Testing {view_name}...")
            job = bq_manager.client.query(query)
            result = job.result()
            
            for row in result:
                count = list(row.values())[0]
                print(f"  ✅ {view_name}: {count:,} rows")
                
        except Exception as e:
            print(f"  ❌ {view_name} failed: {e}")

def show_useful_queries():
    """Mostrar queries útiles para Power BI"""
    
    project_id = os.getenv('GCP_PROJECT_ID', 'plex-etl-project')
    dataset = os.getenv('BIGQUERY_DATASET', 'plex_analytics')
    
    print(f"\n📋 Useful queries for Power BI:")
    print("="*60)
    
    queries = {
        "Ventas por día (último mes)": f"""
SELECT 
    fecha_venta,
    sucursal_nombre,
    SUM(total_ventas) as ventas_dia,
    SUM(unidades_vendidas) as unidades_dia
FROM `{project_id}.{dataset}.v_ventas_analysis`
WHERE fecha_venta >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
GROUP BY 1, 2
ORDER BY 1 DESC
""",
        
        "Top productos por laboratorio": f"""
SELECT 
    Laboratorio,
    producto_nombre,
    SUM(total_ventas) as ventas_total,
    SUM(unidades_vendidas) as unidades_total
FROM `{project_id}.{dataset}.v_ventas_analysis`
WHERE fecha_venta >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
GROUP BY 1, 2
HAVING ventas_total > 1000
ORDER BY ventas_total DESC
LIMIT 50
""",
        
        "Performance por sucursal": f"""
SELECT 
    sucursal_nombre,
    COUNT(DISTINCT fecha_venta) as dias_activos,
    SUM(total_ventas) as ventas_total,
    SUM(total_ventas) / COUNT(DISTINCT fecha_venta) as ventas_promedio_dia,
    COUNT(DISTINCT producto_nombre) as productos_distintos
FROM `{project_id}.{dataset}.v_ventas_analysis`
WHERE fecha_venta >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
GROUP BY 1
ORDER BY ventas_total DESC
"""
    }
    
    for title, query in queries.items():
        print(f"\n-- {title}")
        print(query)
        print()

if __name__ == "__main__":
    create_analytical_views()
    show_useful_queries()
    
    print("\n" + "="*60)
    print("💡 Next steps:")
    print("1. Monitor ETL: python3 monitor_etl.py")
    print("2. Test incremental: python3 run_incremental.py") 
    print("3. Connect Power BI to BigQuery views")
    print("4. Use the queries above for your dashboards")