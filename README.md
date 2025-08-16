# Plex ETL Project

ETL pipeline para replicar bases de datos MySQL (Plex y Quantio) a BigQuery usando Google Cloud Platform.

## 🏗️ Arquitectura

```
MySQL (Plex) ──┐
               ├── Python ETL ── Google Storage ── BigQuery ── Vistas Analíticas
MySQL (Quantio) ┘                   ↑
                         Cloud Functions (cada 12h)
```

## 📁 Estructura del Proyecto

```
plex/
├── src/
│   ├── database/           # Conexiones a MySQL
│   │   ├── connector.py
│   │   └── secret_manager.py
│   ├── etl/               # Procesos ETL
│   │   └── extractor.py
│   ├── cloud/             # Google Cloud services
│   │   ├── storage.py
│   │   └── bigquery.py
│   ├── utils/             # Utilidades
│   │   └── config.py
│   └── main.py            # Pipeline principal
├── scripts/               # Scripts de setup
│   └── setup_secrets.py
├── tests/                 # Tests
│   └── test_connections.py
├── config/                # Configuración
│   └── database_config_complete.yaml
├── deploy/                # Deployment
│   ├── cloud_scheduler_setup.sh
│   └── terraform/
├── notebooks/             # Jupyter notebooks
│   └── test_connections.ipynb
└── docs/                  # Documentación
```

## 🚀 Setup Rápido

### 1. Configurar entorno virtual
```bash
python3 -m venv plex
source plex/bin/activate
pip install -r requirements.txt
```

### 2. Configurar variables de entorno
```bash
export GCP_PROJECT_ID="plex-etl-project"
export GOOGLE_APPLICATION_CREDENTIALS="./etl-service-account-key.json"
```

### 3. Configurar secrets
```bash
python scripts/setup_secrets.py
```

### 4. Probar conexiones
```bash
python tests/test_connections.py
```

## 📊 Bases de Datos

### Plex (Principal)
- **factcabecera**: 9.2M facturas
- **factlineas**: 13.5M líneas de factura
- **stock**: 622K registros de inventario
- **medicamentos**: 772K productos

### Quantio (Complementaria)
- **productos**: 91K productos
- **stock**: 19K registros
- **stocklotes**: 156K lotes

## ⏰ Programación

- **ETL incremental**: Cada 12 horas (12:00 AM y 12:00 PM)
- **ETL completo**: Domingos 2:00 AM
- **Retención**: 90 días en Cloud Storage

## 💰 Costos Estimados

- **~$29/mes** con ETL cada 12 horas
- **Optimizaciones**: Particionado, compresión Parquet
- **Monitoreo**: Cloud Functions + BigQuery

## 🔧 Uso

### Ejecutar ETL local
```bash
python src/main.py
```

### Ejecutar tests
```bash
python tests/test_connections.py
```

### Deploy a Cloud Functions
```bash
cd deploy/
./cloud_scheduler_setup.sh
```

## 📈 Vistas Creadas

1. **v_facturas_lineas**: Facturas consolidadas
2. **v_ventas_analysis**: Análisis de ventas
3. **v_reporte_bi_consolidado**: Reporte BI completo
4. **v_pedidos_lineas**: Pedidos consolidados

## 🔐 Seguridad

- Credenciales en Google Secret Manager
- Service Account con permisos mínimos
- Conexiones SSL a MySQL
- Datos encriptados en Cloud Storage

## 📝 Logs y Monitoreo

- Cloud Functions logs
- BigQuery job monitoring
- Storage operation logs
- Error alerting configurado