# Plan de Automatizacion del ETL - Cloud Functions

**Proyecto**: Plex ETL MySQL → BigQuery
**Objetivo**: Automatizar ejecucion diaria sin intervencion manual
**Fecha**: 2026-01-21
**Estado**: Plan inicial - Pendiente implementacion

---

## 1. Arquitectura Propuesta

### Componente Principal: Cloud Functions (2nd Gen)
**Por que 2nd Gen vs 1st Gen:**
- Timeouts mas largos (hasta 60 minutos vs 9 minutos)
- Mejor manejo de concurrencia
- Integracion nativa con Cloud Run
- Mas recursos de CPU/memoria disponibles

### Flujo de Automatizacion

```
Cloud Scheduler → Pub/Sub Topic → Cloud Function → MySQL (on-premise/Cloud SQL)
                                         ↓
                                    BigQuery
                                         ↓
                                  Cloud Logging
                                         ↓
                              Alerting & Monitoring
```

### Componentes Google Cloud Necesarios

1. **Cloud Functions (2nd Gen)** - Ejecutar codigo ETL
2. **Cloud Scheduler** - Trigger automatico diario
3. **Pub/Sub** - Mensajeria entre Scheduler y Function
4. **Secret Manager** - Credenciales MySQL (ya implementado)
5. **Cloud Logging** - Logs centralizados
6. **Cloud Monitoring** - Alertas y metricas
7. **Cloud Storage** - Backup opcional de logs/errores
8. **Artifact Registry** - Container images (para 2nd Gen)

---

## 2. Configuracion de Cloud Functions

### 2.1 Especificaciones de la Function

```yaml
Nombre: plex-etl-streaming-daily
Runtime: Python 3.11
Tipo: 2nd Gen (Cloud Run)
Trigger: Pub/Sub Topic
Topic: plex-etl-trigger
Region: us-central1 (o la mas cercana a tu MySQL)

Recursos:
  Memory: 4GB (para procesar chunks grandes)
  CPU: 2 vCPU
  Timeout: 3600s (60 minutos - para tablas muy grandes)
  Max instances: 1 (evitar ejecuciones paralelas no deseadas)
  Min instances: 0 (no mantener instancias calientes = ahorro)

Environment Variables:
  GCP_PROJECT_ID: plex-etl-project
  LOOKBACK_DAYS: 5
  CHUNK_SIZE: 100000
  MYSQL_TIMEOUT: 3000

Service Account:
  etl-service-account@plex-etl-project.iam.gserviceaccount.com
```

### 2.2 Entry Point

El codigo ya esta preparado en `src/main_streaming.py`:
- `streaming_etl_cloud_function(request)` - Para HTTP triggers
- `streaming_etl_scheduled_function(cloud_event)` - Para Pub/Sub triggers (recomendado)

**Usaremos**: `streaming_etl_scheduled_function` porque:
- Mejor para scheduled jobs
- No expone endpoint HTTP publico
- Integracion nativa con Cloud Scheduler via Pub/Sub

---

## 3. Configuracion de Cloud Scheduler

### 3.1 Job Diario Principal

```yaml
Nombre: plex-etl-daily-incremental
Descripcion: ETL incremental diario (ultimos 5 dias)
Frecuencia: 0 3 * * * (3:00 AM todos los dias)
Timezone: America/Argentina/Buenos_Aires (o tu timezone)
Target: Pub/Sub Topic
Topic: plex-etl-trigger
Payload: {"lookback_days": 5, "force_full_refresh": false}
Retry Config:
  Max retry attempts: 2
  Max retry duration: 2 hours
  Min/Max backoff: 10s / 300s
```

### 3.2 Jobs Adicionales (Opcionales)

**Full Refresh Semanal**:
```yaml
Nombre: plex-etl-weekly-full-refresh
Frecuencia: 0 2 * * 0 (Domingos 2:00 AM)
Payload: {"lookback_days": 0, "force_full_refresh": true}
```

**Health Check Horario** (opcional):
```yaml
Nombre: plex-etl-health-check
Frecuencia: 0 * * * * (cada hora)
Payload: {"health_check": true}  # Requiere implementar endpoint
```

---

## 4. Deployment Strategy

### 4.1 Archivos Necesarios

```
plex-fdp/
├── src/                          # Ya existe
├── requirements.txt              # Ya existe
├── main.py                       # CREAR: Entry point para Cloud Functions
├── .gcloudignore                 # CREAR: Excluir archivos innecesarios
└── cloudbuild.yaml               # OPCIONAL: CI/CD automatico
```

### 4.2 Crear Entry Point `main.py`

```python
# main.py - Entry point para Cloud Functions
from src.main_streaming import streaming_etl_scheduled_function
import functions_framework

# Re-export la funcion para que Cloud Functions la encuentre
__all__ = ['streaming_etl_scheduled_function']
```

### 4.3 Crear `.gcloudignore`

```
# .gcloudignore - Excluir del deployment
.git/
.gitignore
.env
*.log
logs/
plex-env/
venv/
__pycache__/
*.pyc
*.pyo
.pytest_cache/
.vscode/
.idea/
*.md
etl-service-account-key.json  # NO subir keys locales
debug_*.py
scripts/
config/mysql_structure.yaml
```

### 4.4 Comandos de Deployment

**Paso 1: Crear Pub/Sub Topic**
```bash
gcloud pubsub topics create plex-etl-trigger \
  --project=plex-etl-project
```

**Paso 2: Deploy Cloud Function**
```bash
gcloud functions deploy plex-etl-streaming-daily \
  --gen2 \
  --runtime=python311 \
  --region=us-central1 \
  --source=. \
  --entry-point=streaming_etl_scheduled_function \
  --trigger-topic=plex-etl-trigger \
  --memory=4GB \
  --cpu=2 \
  --timeout=3600s \
  --max-instances=1 \
  --min-instances=0 \
  --service-account=etl-service-account@plex-etl-project.iam.gserviceaccount.com \
  --set-env-vars GCP_PROJECT_ID=plex-etl-project,LOOKBACK_DAYS=5,CHUNK_SIZE=100000,MYSQL_TIMEOUT=3000
```

**Paso 3: Crear Cloud Scheduler Job**
```bash
gcloud scheduler jobs create pubsub plex-etl-daily-incremental \
  --location=us-central1 \
  --schedule="0 3 * * *" \
  --topic=plex-etl-trigger \
  --message-body='{"lookback_days": 5, "force_full_refresh": false}' \
  --time-zone="America/Argentina/Buenos_Aires"
```

**Paso 4: Test Manual**
```bash
# Trigger manual del scheduler job
gcloud scheduler jobs run plex-etl-daily-incremental \
  --location=us-central1

# Ver logs en tiempo real
gcloud functions logs read plex-etl-streaming-daily \
  --gen2 \
  --region=us-central1 \
  --limit=50
```

---

## 5. Monitoreo y Alertas

### 5.1 Metricas Clave a Monitorear

1. **Duracion de Ejecucion**
   - SLO: < 30 minutos para incremental
   - Alerta si > 45 minutos

2. **Tasa de Errores**
   - SLO: < 1% error rate
   - Alerta si > 5% errores

3. **Filas Procesadas**
   - Track: Total rows por tabla
   - Alerta si 0 filas (indica problema)

4. **Uso de Memoria**
   - SLO: < 3.5GB (de 4GB)
   - Alerta si > 3.8GB

### 5.2 Configurar Cloud Monitoring Alerts

**Alerta 1: Function Failed**
```yaml
Condicion: Cloud Function execution status = error
Threshold: > 0 errores en 5 minutos
Notificacion: Email + SMS
Canales: admin@empresa.com
```

**Alerta 2: Function Timeout**
```yaml
Condicion: Execution time > 50 minutos
Threshold: > 1 timeout en 24 horas
Notificacion: Email
```

**Alerta 3: No Data Loaded**
```yaml
Condicion: Log contiene "No data extracted/loaded"
Threshold: > 0 en 24 horas
Notificacion: Email
```

### 5.3 Dashboard Recomendado

Crear dashboard en Cloud Monitoring con:
- Grafico de ejecuciones exitosas vs fallidas (ultimos 30 dias)
- Histograma de duracion de ejecucion
- Total de filas procesadas por dia
- Uso de memoria/CPU por ejecucion
- Errores de BigQuery por tabla

---

## 6. Mejoras al Codigo Actual

### 6.1 Logging Estructurado (Alta Prioridad)

**Problema Actual**: Prints simples no aprovechan Cloud Logging
**Solucion**: Usar `google-cloud-logging`

```python
# Agregar a requirements.txt
google-cloud-logging==3.11.0

# Modificar src/utils/logging_helper.py
import google.cloud.logging
import logging

def setup_cloud_logging():
    client = google.cloud.logging.Client()
    client.setup_logging()

# Usar en main_streaming.py
logger = logging.getLogger(__name__)
logger.info("Starting ETL", extra={
    "lookback_days": lookback_days,
    "tables": len(tables),
    "etl_run_id": run_id  # Para tracking
})
```

### 6.2 Manejo de Parametros via Pub/Sub Message

**Modificar `streaming_etl_scheduled_function`**:
```python
@functions_framework.cloud_event
def streaming_etl_scheduled_function(cloud_event):
    import base64
    import json

    # Parse Pub/Sub message
    if cloud_event.data:
        message_data = base64.b64decode(cloud_event.data["message"]["data"])
        params = json.loads(message_data)
    else:
        params = {}

    lookback_days = params.get('lookback_days', 5)
    force_full_refresh = params.get('force_full_refresh', False)
    chunk_size = params.get('chunk_size', None)
    table_group = params.get('table_group', None)

    result = run_streaming_etl_pipeline(
        lookback_days=lookback_days,
        force_full_refresh=force_full_refresh,
        chunk_size=chunk_size,
        table_group=table_group
    )

    return result
```

### 6.3 Idempotencia y Watermarks

**Problema**: Si la function falla a mitad, puede procesar datos duplicados
**Solucion**: Implementar watermark table en BigQuery

```sql
-- Crear tabla de control
CREATE TABLE IF NOT EXISTS plex_analytics.etl_watermarks (
  table_name STRING,
  last_processed_timestamp TIMESTAMP,
  last_run_status STRING,  -- success, failed, running
  last_run_id STRING,
  rows_processed INT64,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
PARTITION BY DATE(updated_at);

-- Insertar/Update watermark despues de cada tabla
INSERT INTO plex_analytics.etl_watermarks
  (table_name, last_processed_timestamp, last_run_status, last_run_id, rows_processed)
VALUES
  ('plex_factcabecera', '2026-01-21 03:00:00', 'success', 'run-123', 150000)
```

### 6.4 Dead Letter Queue para Errores

```bash
# Crear DLQ topic
gcloud pubsub topics create plex-etl-dead-letter

# Modificar subscription de Cloud Function para usar DLQ
gcloud pubsub subscriptions update <subscription-name> \
  --dead-letter-topic=plex-etl-dead-letter \
  --max-delivery-attempts=5
```

---

## 7. Costos Estimados (USD/mes)

### 7.1 Ejecuciones Diarias

**Cloud Functions (2nd Gen)**:
- 30 ejecuciones/mes x 30 min promedio = 15 horas/mes
- vCPU: 2 vCPU x 15h x $0.000024/vCPU-segundo = $2.59
- Memory: 4GB x 15h x $0.0000025/GB-segundo = $0.54
- Invocations: 30 x $0.40/millones = $0.01
- **Subtotal**: ~$3.15/mes

**Cloud Scheduler**:
- 1 job x $0.10/mes = $0.10/mes

**Pub/Sub**:
- 30 mensajes/mes ≈ gratis (primeros 10GB gratis)
- **Subtotal**: $0.00/mes

**Cloud Logging**:
- Estimado: 5GB logs/mes
- Primeros 50GB gratis
- **Subtotal**: $0.00/mes

**Secret Manager**:
- 3 secrets x $0.06/mes = $0.18/mes

**BigQuery** (costos existentes, no cambian):
- Streaming inserts: Ya los estas usando
- Storage: Ya lo estas usando

### 7.2 Total Estimado

**Costo mensual total**: ~$3.50 - $5.00 USD/mes

**Vs alternativas**:
- Compute Engine e2-micro 24/7: ~$7/mes (pero subutilizado)
- Cloud Composer (Airflow): ~$300/mes (overkill)
- Cloud Run Jobs: Similar a Functions 2nd Gen

**Recomendacion**: Cloud Functions es la opcion mas costo-efectiva

---

## 8. Plan de Implementacion (Paso a Paso)

### Fase 1: Preparacion (1-2 horas)

- [ ] Verificar service account tiene permisos necesarios:
  ```bash
  gcloud projects add-iam-policy-binding plex-etl-project \
    --member="serviceAccount:etl-service-account@plex-etl-project.iam.gserviceaccount.com" \
    --role="roles/bigquery.dataEditor"

  gcloud projects add-iam-policy-binding plex-etl-project \
    --member="serviceAccount:etl-service-account@plex-etl-project.iam.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"

  gcloud projects add-iam-policy-binding plex-etl-project \
    --member="serviceAccount:etl-service-account@plex-etl-project.iam.gserviceaccount.com" \
    --role="roles/logging.logWriter"
  ```

- [ ] Crear archivos necesarios:
  - [ ] `main.py` (entry point)
  - [ ] `.gcloudignore`
  - [ ] Actualizar `requirements.txt` con `google-cloud-logging`

- [ ] Validar que credenciales MySQL esten en Secret Manager:
  ```bash
  gcloud secrets versions access latest --secret="mysql-plex-host"
  gcloud secrets versions access latest --secret="mysql-plex-user"
  gcloud secrets versions access latest --secret="mysql-plex-password"
  ```

### Fase 2: Deployment Inicial (30 minutos)

- [ ] Crear Pub/Sub topic y subscription
- [ ] Deploy Cloud Function en modo test (sin scheduler)
- [ ] Test manual con payload simple:
  ```bash
  gcloud pubsub topics publish plex-etl-trigger \
    --message='{"lookback_days": 1, "force_full_refresh": false}'
  ```
- [ ] Revisar logs y validar ejecucion exitosa

### Fase 3: Automatizacion (15 minutos)

- [ ] Crear Cloud Scheduler job para incremental diario
- [ ] Configurar timezone correcto
- [ ] Crear job opcional para full refresh semanal
- [ ] Test scheduler job manualmente

### Fase 4: Monitoreo (1 hora)

- [ ] Configurar alertas basicas (errores, timeouts)
- [ ] Crear dashboard en Cloud Monitoring
- [ ] Configurar canales de notificacion (email/SMS)
- [ ] Test alertas con falla inducida

### Fase 5: Validacion (3-7 dias)

- [ ] Monitorear ejecuciones durante 1 semana
- [ ] Ajustar timeouts/memoria si es necesario
- [ ] Validar datos en BigQuery vs local
- [ ] Documentar comportamiento observado

### Fase 6: Cleanup Local (Despues de validacion)

- [ ] Deshabilitar cron local (si existe)
- [ ] Archivar scripts locales (`scripts/run_etl.sh`)
- [ ] Actualizar documentacion (CLAUDE.md, README)

---

## 9. Rollback Plan

Si algo sale mal, poder volver rapido a ejecucion local:

**Pasos de Rollback**:
1. Pausar Cloud Scheduler job:
   ```bash
   gcloud scheduler jobs pause plex-etl-daily-incremental \
     --location=us-central1
   ```

2. Reactivar ejecucion local:
   ```bash
   cd /Users/bobalabs/code/plex-fdp
   ./scripts/run_etl.sh
   ```

3. Investigar logs de Cloud Functions:
   ```bash
   gcloud functions logs read plex-etl-streaming-daily \
     --gen2 \
     --region=us-central1 \
     --limit=200
   ```

4. Fix el problema y re-deploy

---

## 10. Consideraciones de Seguridad

### 10.1 Conectividad MySQL

**Si MySQL esta on-premise**:
- Necesitas abrir firewall para IPs de Cloud Functions
- IPs son dinamicas, considerar Cloud VPN o Cloud Interconnect
- Alternativa: VPC Connector (conectar function a tu VPC)

**Si MySQL esta en Cloud SQL**:
- Usar Cloud SQL Connector (mas seguro que IP whitelisting)
- Modificar `src/database/connector.py` para usar connector

### 10.2 Secrets Management

- Continuar usando Secret Manager (ya implementado)
- Rotar passwords periodicamente
- Auditar accesos a secrets via Cloud Audit Logs

### 10.3 Least Privilege

- Service account solo con permisos minimos necesarios
- No usar Compute Admin, Owner, o Editor roles
- Usar roles especificos: BigQuery Data Editor, Secret Accessor, Logger

---

## 11. Troubleshooting Guide

### Error: "Function timeout after 60 minutes"

**Causa**: Tablas muy grandes no terminan en tiempo
**Solucion**:
- Aumentar chunk_size para reducir overhead
- Considerar table_group para procesar en batches
- Usar Cloud Run Jobs (permite timeouts mas largos)

### Error: "Memory limit exceeded"

**Causa**: Chunks muy grandes en memoria
**Solucion**:
- Reducir chunk_size (de 100k a 50k)
- Aumentar memoria de function (de 4GB a 8GB)
- Verificar que no haya memory leaks en codigo

### Error: "Cannot connect to MySQL"

**Causa**: Firewall o VPC config
**Solucion**:
- Verificar IP whitelisting
- Configurar VPC Connector si es necesario
- Validar secrets en Secret Manager

### Error: "No data extracted/loaded"

**Causa**: Lookback_days muy corto o no hay datos nuevos
**Solucion**:
- Aumentar lookback_days
- Verificar que incremental_column tenga datos recientes
- Considerar force_full_refresh para esa tabla

---

## 12. Proximos Pasos Post-Automatizacion

Una vez automatizado el ETL, considerar:

1. **Data Quality Checks**:
   - Validar row counts vs dia anterior
   - Detectar anomalias en volumenes
   - Alertas de data quality

2. **Lineage Tracking**:
   - Registrar metadata de cada run
   - Tracking de schema changes
   - Audit trail de transformaciones

3. **Backup Strategy**:
   - Snapshots de tablas BigQuery antes de cargas
   - Retention policy de logs (90 dias?)
   - Disaster recovery plan

4. **Performance Optimization**:
   - Analizar costo de BigQuery queries downstream
   - Particionar tablas por fecha si son muy grandes
   - Clustering keys para queries frecuentes

5. **CI/CD Pipeline**:
   - Tests automaticos antes de deploy
   - Staging environment para testing
   - Blue/green deployments de functions

---

## 13. Checklist de Implementacion

### Pre-Deployment
- [ ] Codigo ya tiene funciones de Cloud Functions (`main_streaming.py`)
- [ ] Requirements.txt actualizado con dependencies
- [ ] Service account con permisos necesarios
- [ ] Secrets en Secret Manager configurados
- [ ] MySQL accesible desde GCP (firewall/VPN)

### Deployment
- [ ] Crear Pub/Sub topic
- [ ] Deploy Cloud Function (gen2)
- [ ] Test manual de function
- [ ] Crear Cloud Scheduler job
- [ ] Test scheduler manualmente
- [ ] Validar datos en BigQuery

### Post-Deployment
- [ ] Configurar alertas basicas
- [ ] Crear dashboard de monitoring
- [ ] Documentar en CLAUDE.md el nuevo setup
- [ ] Monitorear durante 1 semana
- [ ] Deshabilitar ejecucion local

---

## 14. Referencias y Recursos

### Documentacion Google Cloud
- Cloud Functions 2nd Gen: https://cloud.google.com/functions/docs/2nd-gen/overview
- Cloud Scheduler: https://cloud.google.com/scheduler/docs
- Pub/Sub: https://cloud.google.com/pubsub/docs
- Cloud Logging: https://cloud.google.com/logging/docs

### Comandos Utiles
```bash
# Ver todas las functions deployadas
gcloud functions list --gen2

# Ver logs en tiempo real
gcloud functions logs tail plex-etl-streaming-daily --gen2

# Ver scheduler jobs
gcloud scheduler jobs list

# Pausar/Reanudar scheduler
gcloud scheduler jobs pause JOB_NAME
gcloud scheduler jobs resume JOB_NAME

# Ver metricas de function
gcloud monitoring dashboards list
```

### Monitoreo
- Cloud Console Functions: https://console.cloud.google.com/functions
- Cloud Scheduler: https://console.cloud.google.com/cloudscheduler
- Logs Explorer: https://console.cloud.google.com/logs
- Monitoring: https://console.cloud.google.com/monitoring

---

## Conclusion

Este plan permite automatizar completamente el ETL con:
- **Costo bajo**: ~$3-5 USD/mes
- **Mantenimiento minimo**: Solo monitorear alertas
- **Escalabilidad**: Cloud Functions escala automaticamente
- **Confiabilidad**: Reintentos automaticos y alertas
- **Auditoria**: Logs centralizados en Cloud Logging

**Tiempo estimado de implementacion**: 3-4 horas para deployment completo
**Tiempo de validacion**: 1 semana de monitoreo antes de confiar completamente

**Riesgo**: BAJO - Codigo ya esta probado localmente, solo cambias la ejecucion

**Recomendacion**: Empezar con Fase 1-3, validar durante 1 semana, luego Fase 4-6.
