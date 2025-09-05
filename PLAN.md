# 📋 Plan de Desarrollo ETL Farmacéutico - Estado Actual y Próximos Pasos

**Fecha**: 2025-08-25  
**Versión**: 2.0 - Post Limpieza  
**Estado**: ✅ **ETL Streaming Core Funcional** - Lista para Optimización

## 🎯 Resumen Ejecutivo

**El proyecto tiene un ETL streaming completamente funcional** que replica MySQL (Plex/Quantio) → BigQuery usando chunks de 100k filas. La arquitectura central está sólida, pero necesita limpieza de código y optimizaciones específicas.

### **✅ Lo que Funciona (Mantener)**
- **Streaming ETL directo**: MySQL → BigQuery sin Cloud Storage
- **86 relaciones FK** mapeadas y documentadas
- **Schema introspection** automática con fallback
- **Estrategias incrementales** configuradas por tabla
- **Error handling** robusto con reintentos
- **44 tablas, 692 columnas** completamente documentadas

### **🧹 Lo que Necesita Limpieza (Eliminar/Refactorizar)**
- **Código de analytical views** (no funciona, mover a next steps)
- **Cloud Storage** (ya no se usa, limpiar código)  
- **Requirements** dispersos (3 archivos diferentes)
- **Imports** rotos por archivos movidos

## 📂 Estructura Actual Limpia

```
src/
├── main_streaming.py              # ✅ Pipeline principal (CORE)
├── main_tables_not_created.py     # 🔧 Troubleshooting (mantener)
├── etl/
│   └── streaming_extractor.py     # ✅ Extracción optimizada (CORE)
├── database/
│   ├── connector.py               # ✅ Conexiones MySQL + schema (CORE)
│   └── secret_manager.py          # ✅ Google Secret Manager (CORE)
├── cloud/
│   ├── bigquery.py               # 🧹 LIMPIAR - Remover analytical views
│   └── storage.py                # ❌ OBSOLETO - Eliminar (no se usa)
└── utils/
    ├── config.py                 # ✅ Configuraciones (CORE)
    ├── schema_mapper.py          # ✅ MySQL → BigQuery mapping (CORE)
    ├── mysql_structure_generator.py # ✅ Auto-documentación (CORE)
    └── mysql_relationship_analyzer.py # 🔧 Análisis FK (herramienta)
```

## 🎯 Casos de Uso del Sistema

### **1. ETL Incremental Diario (Uso Principal)**
```bash
# Proceso estándar - últimos 3 días
python src/main_streaming.py

# Función Python
from src.main_streaming import run_local_streaming
run_local_streaming()
```

### **2. Catch-up Semanal/Mensual** 
```bash
# Reprocesar última semana
python src/main_streaming.py --lookback_days=7

# Reproceso mensual
python src/main_streaming.py --lookback_days=30
```

### **3. Full Refresh Emergency**
```bash
# Recargar todo desde cero
python src/main_streaming.py --force_full_refresh=true
```

### **4. Cloud Functions (Producción)**
```bash
# Deploy optimizado
./deploy.sh

# HTTP trigger con parámetros
curl -X POST https://FUNCTION_URL -d '{"lookback_days": 10}'

# Scheduled trigger (automático)
./setup_scheduler.sh
```

### **5. Análisis y Documentación**
```bash
# Auto-generar documentación MySQL
python src/utils/mysql_structure_generator.py

# Analizar relaciones FK
python src/utils/mysql_relationship_analyzer.py

# Validar schema mappings
python src/utils/schema_mapper.py
```

## 🚧 Tareas Pendientes (Por Prioridad)

### **🔥 CRÍTICO - Limpieza Inmediata**

#### **1. Eliminar Código de Analytical Views**
**Problema**: Las views en `bigquery.py` líneas 88-180 no funcionan y causan errores
```python
# ELIMINAR ESTAS LÍNEAS de src/cloud/bigquery.py:
def create_analytical_views(self):  # Lines 88-180
    """Create analytical views based on the existing SQL logic"""
    # TODO: Este código no funciona - mover a next steps
```

**Acción**: 
- Remover método `create_analytical_views()` completo
- Remover llamada en `main_streaming.py` línea 31
- Mover lógica a sección "Next Steps"

#### **2. Eliminar Cloud Storage Obsoleto**
**Problema**: `src/cloud/storage.py` ya no se usa (streaming directo)
```python
# ARCHIVO COMPLETO OBSOLETO: src/cloud/storage.py
# El nuevo ETL va directo MySQL → BigQuery
```

**Acción**:
- Mover `src/cloud/storage.py` a `backup/`
- Verificar que no haya imports rotos

#### **3. Consolidar Requirements**
**Problema**: 3 archivos diferentes confunden las dependencias
```bash
requirements.txt           # Principal 
requirements-cloud.txt     # Cloud Functions
requirements-minimal.txt   # Mínimo
```

**Acción**:
- Consolidar en `requirements.txt` único
- Eliminar dependencias no utilizadas
- Validar que todo funciona

### **⚡ ALTO - Optimización de Código**

#### **4. Arreglar Imports Rotos**
**Problema**: Los archivos movidos a backup pueden causar ImportError

**Acción**:
- Ejecutar `python src/main_streaming.py` para detectar imports rotos
- Arreglar referencias faltantes
- Validar que todos los módulos cargan correctamente

#### **5. Refactorizar BigQuery Manager**
**Problema**: Métodos mezclados (streaming + obsoletos)

**Acción**:
- Mantener solo métodos streaming: `load_dataframe_to_table()`, `create_dataset_if_not_exists()`
- Eliminar métodos obsoletos: `create_external_table()`, `create_all_external_tables()`
- Simplificar clase para uso streaming únicamente

### **📊 MEDIO - Mejoras Funcionales**

#### **6. Implementar Estrategias Incrementales Avanzadas**
**Objetivo**: Usar las 86 relaciones FK descubiertas

**Implementación**:
```python
# Ejemplo: factcabecera cluster incremental
factcabecera_strategy = {
    'parent': 'factcabecera',
    'children': ['factlineas', 'factpagos', 'factcoberturas'],
    'join_column': 'IDComprobante',
    'watermark': 'emision'
}
```

#### **7. Optimizar Performance por Tabla**
**Basado en volumen de datos**:
- **33M+ filas** (asientos_detalle): Chunks 50k, cada 4h
- **13M+ filas** (factlineas): Chunks 100k, cada 6h  
- **<1M filas** (master data): Chunks 200k, diario

#### **8. Mejorar Error Handling**
- Logging estructurado (no solo prints)
- Notificaciones de errores críticos
- Recovery automático en fallos de chunks

### **🚀 LARGO PLAZO - Nuevas Características**

#### **9. Analytical Views (Next Steps)**
**Objetivo**: Crear vistas analíticas que SÍ funcionen
```sql
-- Ejemplos de vistas necesarias:
CREATE VIEW v_ventas_consolidadas AS ...
CREATE VIEW v_inventario_actual AS ...  
CREATE VIEW v_prescripciones_tracking AS ...
```

#### **10. Data Quality & Monitoring**
- Validación automática de datos
- Métricas de calidad de datos
- Dashboards de monitoreo ETL

#### **11. Parallel Processing**
- Procesamiento paralelo de tablas independientes
- Optimización de recursos Cloud Functions
- Schedulers diferenciados por criticidad

## 🛠️ Plan de Implementación (Próximas 2 Semanas)

### **Semana 1: Limpieza Crítica**
- **Día 1-2**: Eliminar analytical views + cloud storage
- **Día 3-4**: Consolidar requirements + arreglar imports
- **Día 5**: Validar que ETL streaming funciona 100%

### **Semana 2: Optimizaciones**  
- **Día 1-2**: Refactorizar BigQuery Manager
- **Día 3-4**: Implementar estrategias incrementales avanzadas
- **Día 5**: Testing completo + documentación

## 📊 Métricas de Éxito

### **Técnicas**
- ✅ **ETL streaming**: 0 errores de schema/tipos
- ✅ **Performance**: <45min para full load
- ✅ **Incremental**: <5min para load diario
- ✅ **Reliability**: >99% success rate

### **Operacionales**
- ✅ **Cost**: <$25/mes (actual ~$23/mes)
- ✅ **Data Freshness**: <2 horas lag máximo
- ✅ **Monitoring**: Alertas automáticas en fallos

## 🔄 Comando de Validación

**Para probar que todo funciona después de cada cambio**:
```bash
# Test completo del sistema
python src/main_streaming.py --lookback_days=1

# Debe retornar:
# ✅ Schema introspection working
# ✅ MySQL connections successful  
# ✅ BigQuery load successful
# ✅ All 44 tables processed
# ✅ No import errors
```

## 📞 Support & Questions

**Si algo no funciona después de los cambios**:
1. Check `claude_sessions/SESSION_2025-08-25_CLEANUP.md` 
2. Revisar archivos movidos a `backup/`
3. Validar que `requirements.txt` tiene todas las dependencias
4. Ejecutar test de validación arriba

## 🔄 **Mejoras Futuras - Logging System**

### **ETL Audit & Logging Infrastructure**
1. **Crear schema de auditoría** `plex_etl_audit` en BigQuery
2. **Tablas de logging**:
   - `etl_execution_log` - Registro de cada ejecución ETL (inicio, fin, status)
   - `table_processing_log` - Log por tabla (filas procesadas, tiempo, errores)  
   - `incremental_watermarks` - Tracking de marcas de agua por tabla
   - `data_quality_metrics` - Métricas de calidad por tabla/columna
3. **Implementar en StreamingDataExtractor**:
   - Log inicio/fin de cada tabla
   - Capturar métricas (filas MySQL vs BigQuery, tiempo procesamiento)
   - Alertas automáticas por fallos o discrepancias
4. **Dashboard de monitoreo** con métricas ETL en tiempo real

---

**🎯 Objetivo**: Sistema ETL limpio, optimizado y 100% funcional para análisis farmacéutico  
**📅 Target**: 2 semanas para completar todas las optimizaciones críticas