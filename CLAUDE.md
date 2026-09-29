# CLAUDE.md - Plex ETL Project Documentation

## 🎯 Project Overview
Sistema ETL para farmacéuticas que extrae datos de MySQL (Plex/Quantio) y los carga a BigQuery para análisis. Implementa streaming ETL directo MySQL → BigQuery evitando Cloud Storage como intermediario.

## 🚀 What We Built

### **ETL Streaming Architecture**
- **MySQL → BigQuery directo** sin Cloud Storage
- **Chunks de 100k filas** para optimizar performance
- **Schema introspection** automática desde MySQL
- **Documentación automática** de estructura MySQL
- **Error handling** robusto con reintentos

### **Key Components**

#### 1. **Database Connection (`src/database/connector.py`)**
- Conexiones MySQL via Google Secret Manager
- Schema introspection usando `INFORMATION_SCHEMA` 
- Extracción manual con cursor (evita bug pandas.read_sql)
- Chunking automático para tablas grandes

#### 2. **Schema Management (`src/utils/schema_mapper.py`)**
- Mapeo automático MySQL → BigQuery types
- Manejo de casos especiales (tinyint(1) → BOOL, varchar → STRING)
- Esquemas BigQuery explícitos para evitar autodetect

#### 3. **Structure Documentation (`src/utils/mysql_structure_generator.py`)**
- Auto-genera `config/mysql_structure.yaml`
- Documenta tipos MySQL y BigQuery por tabla
- Estadísticas de esquema (strings, integers, etc.)
- Fallback para esquemas desde YAML

#### 4. **Streaming ETL (`src/etl/streaming_extractor.py`)**
- Extracción incremental por fecha/timestamp
- Carga directa en chunks con schema explícito
- Conversión automática de timedelta → TIME strings
- Manejo de múltiples bases de datos

#### 5. **BigQuery Management (`src/cloud/bigquery.py`)**
- Schema enforcement (autodetect=False)
- **Schema cache** per table per run (avoids repeated get_table API calls per chunk)
- **Dataset existence cache** (checked once per run, not per table)
- Configuración explícita de formatos de carga

## 🔧 Critical Fixes Applied

### **Problem 1: Headers as Data Rows**
- **Issue**: `pandas.read_sql()` duplicaba headers como filas de datos
- **Solution**: Usar cursor manual de pymysql en lugar de pandas.read_sql
- **Result**: Datos reales en lugar de "IDComprobante, IDGlobal, ..." repetidos

### **Problem 2: Wrong BigQuery Types**
- **Issue**: varchar → INT64, dates → STRING 
- **Solution**: Schema introspection + mapeo explícito MySQL → BigQuery
- **Result**: CliApeNom como STRING, fechas como DATE/TIME

### **Problem 3: Database Name Mismatch**
- **Issue**: Buscaba schema en "plex" pero DB real es "onze_center"
- **Solution**: `SELECT DATABASE()` para obtener nombre real
- **Result**: INFORMATION_SCHEMA queries funcionando

### **Problem 4: Schema Ignored by BigQuery**
- **Issue**: BigQuery ignoraba schema explícito y usaba autodetect
- **Solution**: Forzar `autodetect=False` + schema en todos los chunks
- **Result**: Tipos correctos en BigQuery

### **Problem 5: TIME Field Errors**
- **Issue**: timedelta64[ns] no compatible con BigQuery TIME
- **Solution**: Conversión a string formato TIME antes de carga
- **Result**: Campos TIME sin errores de parsing

### **Problem 6: Row Count Timeouts on Large Tables**
- **Issue**: COUNT(*) timeouts en tablas grandes (>30M rows), causando extracción de solo 1 chunk
- **Solution**: Sistema de 3 niveles de fallback:
  1. COUNT con timeout de 5 segundos
  2. Estimación desde INFORMATION_SCHEMA.TABLES (+20% buffer)
  3. Extracción continua hasta EOF (sin límite de chunks)
- **Result**: Tablas grandes se procesan completamente sin importar timeouts

### **Problem 7: Pub/Sub Redelivery Causing Duplicate Executions**
- **Issue**: Pub/Sub ack deadline max = 600s, but catalogs/quantio groups take 1-2h. Pub/Sub redelivered messages every 10min, spawning duplicate Cloud Function instances all day
- **Solution**: Switched from Pub/Sub trigger to HTTP trigger. Cloud Scheduler calls the function HTTP endpoint directly with OIDC auth. No Pub/Sub = no redelivery.
- **Result**: Single execution per group, no duplicates. Cloud Run timeout 3600s, Scheduler attempt-deadline 1800s, max-retry-attempts=0.

### **Problem 8: Excessive BigQuery API Calls & Cloud Costs (~$40/mo)**
- **Issue**: Schema reconciliation called `get_table()` 2x per chunk (not per table), dataset existence checked per table (not per run), verbose logging on every chunk → high Cloud Logging + API costs. Function overprovisioned at 4GB/2vCPU.
- **Solution**:
  1. Schema cache in `BigQueryManager._schema_cache` — reconcile once per table, reuse for all chunks
  2. Dataset check cached via `_dataset_verified` flag — 1 API call per run instead of 66
  3. Chunk logging reduced to every 5th chunk
  4. Cloud Function downsized from 4GB/2vCPU to 2GB/1vCPU
- **Result**: ~97% fewer BigQuery API calls, ~80% less Cloud Logging volume, ~50% compute cost reduction. Projected $40/mo → ~$20-25/mo.

### **Problem 9: Catalogs Group OOM — Stock Tables Not Updating (2026-04-06)**
- **Issue**: After downsizing to 2GB on 2026-03-18, the `catalogs` group crashed with OOM (`Memory limit of 1907 MiB exceeded`). `medicamentos` (63 cols × 400K chunk) was the first table and blew the memory limit, killing the container before processing stock/stocklotes/sucursales. Tables frozen since March 18. Reported by Quiroga (delpuentefarmacias) on March 31.
- **Solution**:
  1. Reduced chunk_size for wide/large full_refresh tables: medicamentos 400K→100K, stocklotes 500K→100K, stock 400K→200K, pedidoslineas 500K→200K
  2. Manual full refresh of 4 stock tables from local machine
  3. Redeployed Cloud Function with updated config
- **Result**: All 4 tables updated (stock 624K, stocklotes 5.4M, medicamentos 774K, sucursales 22). Pending verification of automated run on 2026-04-07.

### **Problem 10: Missed Run + lookback=2 Orphans a Whole Day (2026-08-12)**
- **Issue**: `reporte_ventas` showed only 2 sucursales (43 comprobantes) for Sat 2026-08-08 instead of 16 (4,591). Reported by Crosa via the Power BI dashboard.
- **Root cause (two chained faults)**:
  1. **The source MySQL consolidates a day's data 24-48h late.** At 1 AM on D+1, day D is still nearly empty (only the 1-2 sucursales that sync live). Day D only becomes complete in MySQL after the D+2 run reads it. `lookback_days=2` was exactly wide enough for this to work — with zero margin.
  2. **The Mon 2026-08-10 `heavy-transactions` run never executed.** Cloud Run aborted it at startup: `The request was aborted because there was no available instance` → HTTP 500, and `--max-retry-attempts=0` meant no retry. The Tue 08-11 run only looked back to 08-09, so **Saturday 08-08 was never revisited**.
- **Diagnosis note**: IDComprobante is assigned chronologically at the source, so contiguous ID ranges per day make gaps trivially visible — `MAX(IDComprobante)` of day D+1 minus `MIN` of day D reveals exactly how many rows are missing.
- **Solution**:
  1. Manual reprocess with `--lookback_days 6` for heavy/medium/operational groups
  2. `lookback_days` 2 → **5** for the three transactional groups (margin for 3 missed runs; catalogs/quantio stay at 2)
  3. `--max-retry-attempts=3 --min-backoff=60s` on heavy/medium/operational **only** — these finish in <10 min, far under the 1800s attempt deadline, so a retry fires only on a real failure. Catalogs/quantio deliberately stay at 0: they routinely exceed the deadline (504) and a retry would spawn a duplicate run (see Problem 7)
  4. New Sunday catch-up jobs `plex-etl-{heavy,medium,operational}-catchup` at 1:00/1:20/1:40 AM with `lookback_days=8`, repairing any hole from the prior week
- **Result**: 08-08 and 08-11 restored. Total damage found May→Aug: 9,934 comprobantes, 99.9% of it in those two days.

### **Problem 11: asientos / asientos_detalle Incremental Was Slow and Lossy (2026-09-29)**
- **Issue**: Date-based incremental on `FechaHora` (a) is a full scan — the column is **not indexed** — and (b) never sees the accountant's manual entries, which carry typed dates (1977..2027, month-end closings like "VENTAS ITALIA - DICIEMBRE 2024"). 443 asientos and ~15K detail lines missing. Reported by Crosa; the manual entries hit sales accounts 411100/412100 with large amounts.
- **Root cause / data facts**: `asientos.IdProcesoAsiento` (indexed) classifies rows. 1 = facturas (9.0M), 5 = cobranzas (8.1M) → 96.5%, insert-only, `IdAsiento` chronological. 2/3/4/NULL (615K asientos, 1.97M lines) are manual, backdated and edited. Cobranzas (5) are born with one line and get the balancing line weeks later (Concepto flips "Cobranza" → "COBRANZA").
- **Solution**: new `hybrid_process` strategy (`_extract_hybrid_process` in streaming_extractor.py), three phases, all by PK range / PK lookup:
  1. **Phase A (auto)**: reload `(MAX auto IdAsiento in BQ − 20K, MAX in MySQL]`. Child table capped at the parent's BQ max so both stay a consistent snapshot.
  2. **Phase C (stale auto)**: `stale_ids_query` (BQ) returns auto asientos whose lines don't balance → delete + reload those ids (~7.7K nightly, batches of 5K).
  3. **Phase B (manual)**: delete every row whose process ∉ {1,5} (child: whose parent ∉ {1,5}, which also removes orphans) and reload the whole subset in 1M-id windows.
  - Deletes use the raising variant (`delete_incremental_data_from_bigquery`) so a failed DELETE can never be followed by a duplicate INSERT. Each phase is self-healing on a mid-run crash.
- **Result**: MySQL vs BQ diff = 0 for both tables (per process / per 1M block), 0 duplicates, 0 orphans. Both tables in ~9.5 min. Verified with `verify_hybrid.py` pattern: per-process counts capped at BQ max id.
- **Not viable alternatives checked**: Datastream/binlog CDC — both Plex MySQL servers are **5.1.44** with `log_bin=OFF` (unsupported by Datastream/Debezium, would need restart + major upgrade). Filtering by account code (411xxx) does not separate auto from manual: manual entries hit the same accounts.
- **Side note for dashboards**: `plex_reportes.libro_mayor` has 3.37M rows; aggregated by day/empresa/sucursal/cuenta/leyenda it is 91K. Concepto (ticket numbers) is only needed in the raw table.

## 📊 Current Status

### **Cloud Deployment (Active since 2026-03-15)**
- ✅ Cloud Function `plex-etl-streaming-daily` deployed (gen2, **1vCPU/2GB**, 1h timeout)
- ✅ 5 Scheduler groups running Mon-Sat incremental (lookback_days=2)
- ✅ **HTTP trigger** (no Pub/Sub) — eliminates redelivery/duplicate executions
- ✅ Connection reuse (1 persistent connection per DB)
- ✅ Full refresh verified: 146M rows, 66 tables, reporte_ventas continuo
- ✅ **Cost optimized** (2026-03-18): schema caching, reduced logging, downsized compute
- ✅ **OOM fix** (2026-04-06): reduced chunk_size for catalogs group (medicamentos 100K, stocklotes 100K) — pending verification 2026-04-07
- ✅ **asientos hybrid strategy** (2026-09-29): `hybrid_process` for asientos/asientos_detalle, MySQL↔BQ diff = 0. Heavy group now ~20 min (asientos pair ~9.5 min) — pending verification of automated run 2026-09-30
- ⏳ Biweekly full refresh via Cloud Run Job (pending setup, ~$4.50/mo)

### **Schedule (Argentina time, Mon-Sat)**
| Time | Job | Tables |
|------|-----|--------|
| 1:00 AM | heavy-transactions | factcabecera, factlineas, asientos, asientos_detalle |
| 1:20 AM | medium-transactions | factpagos, factcostos, factcoberturas, rec* |
| 1:40 AM | operational | app*, pedidos, compras, clientes |
| 2:00 AM | catalogs | plex master data, stock |
| 2:20 AM | quantio | all 22 quantio tables |

### **Working Tables**
- ✅ All plex + quantio tables loading correctly
- ✅ Schema auto-documentado en `mysql_structure.yaml`
- ✅ Chunks de 100k-250k funcionando
- ✅ Incremental ETL por fecha

### **Architecture Benefits**
- **Performance**: ~3x más rápido que ETL tradicional (sin Cloud Storage)
- **Cost**: Menor costo (sin almacenamiento intermedio)
- **Reliability**: Schema consistency automática + connection reuse
- **Monitoring**: Auto-documentación de estructura

## 🛠️ Commands

### **Run Streaming ETL**
```bash
# Full extraction with default chunk size
python -m src.main_streaming --force_full_refresh

# Incremental with custom chunk size (recommended for large tables)
python -m src.main_streaming --lookback_days 30 --chunk_size 50000

# Re-process failed tables only
python reprocess_failed_tables.py --chunk-size 50000
```

### **Environment Setup**
```bash
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/etl-service-account-key.json"
export GCP_PROJECT_ID="plex-etl-project"
```

### **BigQuery Table Management**
```bash
# Remove table with wrong schema
bq rm -f plex-etl-project:plex_analytics.plex_factcabecera

# Check schema
bq show --schema plex-etl-project:plex_analytics.plex_factcabecera
```

### **Debug Scripts**
```bash
# Test connections and schema introspection
python debug_dataframe.py

# Generate structure docs
python -c "from src.utils.mysql_structure_generator import MySQLStructureGenerator; MySQLStructureGenerator().print_database_summary()"
```

## 📁 Key Files

### **Main Scripts**
- `src/main_streaming.py` - Entry point para streaming ETL
- `src/etl/streaming_extractor.py` - Core streaming logic
- `src/database/connector.py` - MySQL connections + schema introspection

### **Schema & Mapping**
- `src/utils/schema_mapper.py` - MySQL → BigQuery type mapping
- `src/utils/mysql_structure_generator.py` - Auto-documentation
- `config/mysql_structure.yaml` - Auto-generated structure docs

### **Cloud Integration**
- `src/cloud/bigquery.py` - BigQuery operations
- `src/database/secret_manager.py` - Google Secret Manager integration

### **Config**
- `config/database_config_complete.yaml` - Original config (deprecated)
- `etl-service-account-key.json` - Google Cloud credentials

## 🔄 Next Steps

### **Biweekly Full Refresh (HIGHEST Priority)**
1. **Set up Cloud Run Job** for automated full refresh (1st and 15th of each month, 1:00 AM ARG)
   - Cloud Function can't handle it (30min timeout, full refresh takes ~14h)
   - Cloud Run Job runs `scripts/full_refresh.sh` (staging dataset pattern)
   - Estimated cost: ~$4.50/month (2 vCPU, 4GB, ~14h × 2 runs)
   - Need: Dockerfile, Cloud Run Job config, Cloud Scheduler trigger

### **Immediate Cleanup**
4. Remove deprecated `create_typed_views.py`
5. Clean up old ETL methods in bigquery.py
6. Consolidate error handling patterns
7. Add proper logging instead of prints

### **Feature Enhancements**
8. Add data quality checks
9. Implement column-level lineage tracking
10. Add performance metrics collection
11. Create monitoring dashboards

### **Code Refactoring**
12. Extract common patterns into base classes
13. Add proper type hints throughout
14. Create configuration objects instead of environment variables
15. Add comprehensive unit tests

## 🐛 Known Issues

### **Technical Debt**
- Print statements instead of proper logging
- Error handling inconsistent across modules
- No unit tests for schema mapping
- Configuration scattered across files

### **Performance**
- Parallel processing for multiple tables (currently sequential)
- Connection pooling for high-frequency runs

## 🔐 Security Notes

- Credentials via Google Secret Manager (✅)
- No hardcoded passwords or keys (✅)
- Service account with minimal permissions (✅)
- All connections encrypted (✅)

## 📈 Metrics & Monitoring

### **Current ETL Performance**
- **plex_factcabecera**: 9.2M filas en chunks de 100k
- **Average chunk time**: ~30 segundos
- **Total time estimate**: ~45 minutos para full load
- **Incremental time**: ~5 minutos (12 horas de datos)

### **Success Indicators**
- Schema consistency: 100% (tipos correctos)
- Data integrity: Headers eliminados completamente
- Error rate: 0% en última ejecución
- Performance: 3x mejora vs ETL tradicional

---

**Last Updated**: 2026-09-29
**Status**: ✅ Cloud ETL active Mon-Sat + Sunday catch-up, lookback=5 on transactional groups, 1vCPU/2GB, asientos/asientos_detalle on `hybrid_process`
**Next Session**: Verify heavy-transactions run of 2026-09-30 (hybrid phases in logs, per-process counts vs MySQL) + aggregated libro_mayor view for Power BI + biweekly full refresh via Cloud Run Job