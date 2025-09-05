# 🏥 Plex ETL Project - Sistema ETL para Farmacéuticas

**Sistema ETL streaming optimizado** que replica bases de datos MySQL (Plex/Quantio) a BigQuery para análisis farmacéutico. Implementa **streaming directo MySQL → BigQuery** evitando Cloud Storage como intermediario.

## 🎯 Arquitectura Actual

```
MySQL (Plex) ──┐
               ├── Streaming ETL (chunks 100k) ──► BigQuery ──► Análisis
MySQL (Quantio) ┘
```

**Características Clave:**
- ✅ **Streaming directo**: MySQL → BigQuery (sin Cloud Storage)
- ✅ **Chunks de 100k filas** para optimizar performance  
- ✅ **Schema introspection** automática desde MySQL
- ✅ **86 relaciones FK** mapeadas automáticamente
- ✅ **Error handling** robusto con reintentos

## 🚀 Quick Start

### 1. Setup Entorno
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Variables de Entorno
```bash
export GCP_PROJECT_ID="plex-etl-project"
export GOOGLE_APPLICATION_CREDENTIALS="./etl-service-account-key.json"
```

### 3. Ejecutar ETL Streaming
```bash
# ETL optimizado (recomendado)
python src/main_streaming.py

# Con configuración específica
python -c "from src.main_streaming import run_local_streaming; run_local_streaming()"
```

## 📊 Datos Procesados

### Base Plex (Principal)
- **factcabecera**: 9.2M facturas (1.2GB)
- **factlineas**: 13.5M líneas (3GB) 
- **asientos_detalle**: 33M asientos (2GB) - CRÍTICO
- **medicamentos**: 773K productos (0.2GB)

### Base Quantio (Complementaria) 
- **productos**: 92K productos
- **stock**: 19K registros
- **stocklotes**: 157K lotes

## 🔧 Configuración Avanzada

### Estructura del Proyecto
```
src/
├── main_streaming.py          # Pipeline principal optimizado
├── etl/
│   └── streaming_extractor.py # Extracción por chunks
├── database/
│   ├── connector.py           # Conexiones MySQL + introspection
│   └── secret_manager.py      # Google Secret Manager
├── cloud/
│   └── bigquery.py           # Gestión BigQuery
├── utils/
│   ├── schema_mapper.py       # MySQL → BigQuery types
│   └── mysql_structure_generator.py  # Auto-documentación
└── config/
    ├── mysql_structure.yaml           # Schema auto-generado
    ├── mysql_relationships_discovered.yaml  # 86 FKs descubiertas
    └── incremental_strategy.yaml      # Estrategia incremental
```

### Configuración de Chunks
Los tamaños están optimizados por volumen de tabla:
- **Tablas críticas** (33M+ filas): 50,000 chunks
- **Tablas grandes** (1M-13M filas): 100,000 chunks  
- **Tablas pequeñas** (<1M filas): 200,000 chunks

## ⚡ Performance y Optimizaciones

### Streaming ETL (Actual)
- **Uso de memoria**: ~100-500MB (vs 2-4GB anterior)
- **Sin Cloud Storage**: Costo $0 (vs $15+/mes)
- **Tiempo**: ~45min para full load (~30% mejora)
- **Fault tolerance**: ✅ Continúa si falla un chunk

### Estrategias Incrementales
Basadas en las **86 relaciones FK** descubiertas:

```yaml
# Ejemplo: factcabecera cluster
factcabecera_cluster:
  parent: "factcabecera" 
  join_column: "IDComprobante"
  child_tables:
    - factlineas (13.5M filas)
    - factpagos (10.2M filas)
    - factcoberturas (6.1M filas)
```

## 🕐 Programación

### Estrategia Incremental por Criticidad
- **Crítico** (33M+ filas): Cada 4 horas
- **Alto** (9M+ filas): Cada 6 horas  
- **Estándar** (1-9M filas): Cada 8 horas
- **App orders**: Cada 2 horas (tiempo real)
- **Master data**: Diario/semanal

### Comandos de Ejecución
```bash
# Proceso estándar (3 días incremental)
python src/main_streaming.py

# Catch-up semanal
python src/main_streaming.py --lookback_days=7

# Reproceso completo
python src/main_streaming.py --force_full_refresh=true
```

## 📈 Monitoreo

### Métricas Clave
- **33M filas** procesadas en asientos_detalle (tabla crítica)
- **86 relaciones FK** validadas automáticamente
- **Schema consistency**: 100% (tipos correctos)
- **Error rate**: 0% en última ejecución

### Logging Detallado
```
Processing chunk 1/100 (offset: 0)
Loaded chunk 1: 100,000 rows (total: 100,000)
✅ Completed factcabecera: 9.2M rows loaded
```

## 🔐 Seguridad y Compliance

- ✅ **Credenciales**: Google Secret Manager
- ✅ **Service Account**: Permisos mínimos
- ✅ **Conexiones**: SSL/TLS encriptadas
- ✅ **Auditoría**: Logs completos en Cloud Functions

## 🚀 Deployment

### Cloud Functions
```bash
# Deploy optimizado
./deploy.sh

# Setup scheduler automático  
./setup_scheduler.sh
```

### Costos Estimados
- **Cloud Functions**: ~$15/mes
- **BigQuery**: ~$8/mes
- **Cloud Storage**: $0 (eliminado)
- **Total**: ~$23/mes (vs $29 anterior)

## 🧪 Testing y Validación

```bash
# Pruebas de conexión
python tests/test_connections.py

# Validación de tipos de datos
python src/utils/schema_mapper.py

# Generación de documentación automática
python src/utils/mysql_structure_generator.py
```

## 📋 Vistas Analíticas Creadas

1. **v_facturas_consolidated**: Facturas con líneas y pagos
2. **v_ventas_analysis**: Análisis de ventas por sucursal/producto  
3. **v_inventory_status**: Estado consolidado de inventarios
4. **v_prescriptions_tracking**: Seguimiento de recetas médicas

## 🔧 Arquitectura Técnica

### Mapeo de Tipos MySQL → BigQuery
```python
mysql_to_bigquery = {
    'varchar': 'STRING',
    'int': 'INTEGER', 
    'datetime': 'DATETIME',
    'tinyint(1)': 'BOOLEAN',
    'double': 'FLOAT'
}
```

### Gestión de Relaciones
- **86 foreign keys** auto-descubiertas
- **Clusters relacionales** para ETL incremental
- **JOIN-based strategies** para tablas dependientes

## 📞 Soporte y Troubleshooting

### Problemas Comunes
1. **Headers como datos**: ✅ Resuelto (usar cursor manual)
2. **Tipos incorrectos**: ✅ Resuelto (schema introspection) 
3. **Timeouts**: ✅ Resuelto (chunks + reintentos)
4. **Campos TIME**: ✅ Resuelto (conversión a strings)

### Logs y Debugging
```bash
# Logs de Cloud Functions
gcloud functions logs read plex-etl-pipeline --limit=50

# Estado del scheduler
gcloud scheduler jobs describe plex-etl-schedule
```

---

**🎯 Status Actual**: ✅ **ETL streaming funcionando** con tipos correctos y performance optimizada

**📅 Última Actualización**: 2025-08-25  
**🔄 Próxima Fase**: Limpieza y optimización de código