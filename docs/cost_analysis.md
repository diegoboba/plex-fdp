# Análisis de Costos - ETL Plex a BigQuery

## Parámetros Base
- **Tamaño DB inicial**: 50GB
- **Crecimiento estimado**: 2-3GB/mes
- **Región**: us-central1
- **Retención**: 12 meses

---

## Escenario 1: ETL DIARIO (1x/día)

### Cloud Functions
- **Ejecuciones**: 30/mes
- **Memoria**: 2GB, Timeout: 15min
- **Costo**: ~$8/mes

### Cloud Storage
- **Storage**: 50GB inicial + 3GB/mes = 53GB promedio
- **Costo**: $1.06/mes ($0.02/GB)

### BigQuery
- **Storage**: 50GB inicial + 36GB/año = 86GB promedio
- **Storage cost**: $1.72/mes ($0.02/GB)
- **Query processing**: 
  - ETL queries: ~200GB/mes procesados = $1.00/mes
  - Vistas/transformaciones: ~100GB/mes = $0.50/mes
  - Power BI refresh (1x/día): ~150GB/mes = $0.75/mes
- **Streaming inserts**: Mínimo (batch loading)

### Power BI Premium (si aplica)
- **Egress BigQuery → Power BI**: ~50GB/mes = $5.00/mes

**TOTAL DIARIO: ~$17.03/mes**

---

## Escenario 2: ETL CADA 12 HORAS (2x/día)

### Cloud Functions
- **Ejecuciones**: 60/mes
- **Memoria**: 2GB, Timeout: 12min (datos semi-incrementales)
- **Costo**: ~$12/mes

### Cloud Storage
- **Storage**: 50GB inicial + 3GB/mes = 53GB
- **Operations**: 2x más operaciones = +$1/mes
- **Costo**: $2.06/mes

### BigQuery
- **Storage**: 86GB promedio = $1.72/mes
- **Query processing**:
  - ETL queries: ~300GB/mes = $1.50/mes
  - Vistas/transformaciones: ~150GB/mes = $0.75/mes
  - Power BI refresh (2x/día): ~300GB/mes = $1.50/mes
- **Streaming inserts**: ~$1.50/mes

### Power BI Premium
- **Egress**: ~100GB/mes = $10.00/mes

**TOTAL 12 HORAS: ~$29.03/mes**

---

## Escenario 3: ETL CADA 6 HORAS (4x/día)

### Cloud Functions
- **Ejecuciones**: 120/mes
- **Memoria**: 2GB, Timeout: 8min (datos incrementales)
- **Costo**: ~$15/mes

### Cloud Storage
- **Storage**: 50GB inicial + 3GB/mes = 53GB
- **Operations**: 4x más operaciones = +$2/mes
- **Costo**: $3.06/mes

### BigQuery
- **Storage**: 86GB promedio = $1.72/mes
- **Query processing**:
  - ETL queries: ~400GB/mes = $2.00/mes
  - Vistas/transformaciones: ~200GB/mes = $1.00/mes
  - Power BI refresh (4x/día): ~600GB/mes = $3.00/mes
- **Streaming inserts**: ~$3/mes

### Power BI Premium
- **Egress**: ~200GB/mes = $20.00/mes

**TOTAL 6 HORAS: ~$45.78/mes**

---

## Escenario 3: ETL CADA HORA (24x/día)

### Cloud Functions
- **Ejecuciones**: 720/mes
- **Memoria**: 1GB, Timeout: 5min (micro-incrementales)
- **Costo**: ~$35/mes

### Cloud Storage
- **Storage**: 53GB = $1.06/mes
- **Operations**: 24x más = +$8/mes
- **Costo**: $9.06/mes

### BigQuery
- **Storage**: 86GB = $1.72/mes
- **Query processing**:
  - ETL queries: ~1,200GB/mes = $6.00/mes
  - Vistas/transformaciones: ~600GB/mes = $3.00/mes
  - Power BI refresh (24x/día): ~3,600GB/mes = $18.00/mes
- **Streaming inserts**: ~$15/mes

### Power BI Premium
- **Egress**: ~1,200GB/mes = $120.00/mes

**TOTAL HORARIO: ~$207.78/mes**

---

## RECOMENDACIÓN: ETL CADA 6 HORAS

### ✅ **Balance óptimo costo/beneficio**
- **Latencia aceptable**: 6 horas máximo
- **Costo moderado**: ~$46/mes
- **Performance**: MySQL no sobrecargado
- **Power BI**: Datos frescos 4x/día

### 🚀 **Optimizaciones adicionales**:

1. **Compresión Parquet**: -20% storage costs
2. **Partition pruning**: -30% query costs  
3. **Materialized views**: Cache queries frecuentes
4. **Power BI Direct Query**: Reducir egress costs
5. **Scheduled queries**: Pre-calcular aggregados

### 💰 **Costo optimizado estimado**: $32-35/mes

---

## Notas Importantes

- **Costos variables**: Dependen del crecimiento real de datos
- **Power BI**: Considerar Direct Query mode para reducir egress
- **Monitoring**: Cloud Monitoring incluido en costos GCP
- **Disaster Recovery**: No incluido (agregar ~$10/mes)