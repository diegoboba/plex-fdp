# 🚀 ETL Pipeline - Deployment Guide

## 📋 Overview
ETL pipeline para replicar MySQL (Plex + Quantio) a BigQuery, programado para ejecutarse cada 12 horas.

## 🏗️ Architecture
```
MySQL Databases → Google Cloud Storage → BigQuery → Power BI
     ↓                    ↓                 ↓
  (Extract)          (Transform)        (Load)
```

## 📁 Project Structure
```
plex/
├── src/                    # Source code
│   ├── database/          # MySQL connectors & secrets
│   ├── etl/               # Data extraction logic  
│   ├── cloud/             # GCS & BigQuery managers
│   └── utils/             # Configuration utilities
├── config/                # Database configurations
├── deploy.sh              # Cloud Functions deployment
├── setup_scheduler.sh     # Cloud Scheduler setup
└── requirements-cloud.txt # Cloud dependencies
```

## 🚀 Deployment Steps

### 1. Prerequisites
```bash
# Authenticate with Google Cloud
gcloud auth login
gcloud auth application-default login

# Set project
export GCP_PROJECT_ID="plex-etl-project"
gcloud config set project $GCP_PROJECT_ID
```

### 2. Deploy to Cloud Functions
```bash
# Deploy the ETL function
./deploy.sh
```

This will:
- ✅ Enable required Google Cloud APIs
- ✅ Package and deploy the ETL function
- ✅ Configure 2GB memory, 1-hour timeout
- ✅ Set up environment variables
- ✅ Return function URL for testing

### 3. Set up Automated Scheduling
```bash
# Configure Cloud Scheduler (every 12 hours)
./setup_scheduler.sh
```

This will:
- ✅ Create scheduler job for 12 AM and 12 PM
- ✅ Configure retries and error handling
- ✅ Set Argentina timezone
- ✅ Test run option

## ⏰ Schedule Configuration

**Frequency:** Every 12 hours  
**Times:** 12:00 AM and 12:00 PM (Argentina time)  
**Mode:** Incremental (only last 12 hours of data)  
**Estimated cost:** ~$29/month

## 🔍 Monitoring & Management

### View Logs
```bash
# Function execution logs
gcloud functions logs read plex-etl-pipeline --region=us-central1 --limit=50

# Scheduler logs
gcloud scheduler jobs describe plex-etl-schedule --location=us-central1
```

### Manual Execution
```bash
# Trigger ETL manually
gcloud scheduler jobs run plex-etl-schedule --location=us-central1

# Or via HTTP
curl -X POST https://FUNCTION_URL \
  -H "Content-Type: application/json" \
  -d '{"incremental": true}'
```

### Scheduler Management
```bash
# Pause scheduler
gcloud scheduler jobs pause plex-etl-schedule --location=us-central1

# Resume scheduler  
gcloud scheduler jobs resume plex-etl-schedule --location=us-central1

# Update schedule
gcloud scheduler jobs update http plex-etl-schedule \
  --location=us-central1 \
  --schedule="0 6,18 * * *"  # Example: 6 AM and 6 PM
```

## 📊 BigQuery Views

After deployment, these analytical views will be available:

- `v_facturas_lineas` - Invoices with consolidated lines
- `v_pedidos_lineas` - Orders with consolidated lines  
- `v_reporte_bi_consolidado` - Consolidated BI report
- `v_ventas_analysis` - Sales analysis by branch/product

## 🔧 Performance Features

- ✅ **Chunked extraction** (100k rows per chunk)
- ✅ **Timeout handling** (5min read, 3 retries)
- ✅ **Incremental processing** (only new data)
- ✅ **Automatic retries** with exponential backoff
- ✅ **Cost optimization** (~$29/month target)

## 🚨 Troubleshooting

### Function Timeout
```bash
# Increase timeout (max 9 minutes for HTTP functions)
gcloud functions deploy plex-etl-pipeline \
  --timeout=540s \
  --memory=4GB
```

### Memory Issues
```bash
# Increase memory allocation
gcloud functions deploy plex-etl-pipeline \
  --memory=4GB
```

### MySQL Connection Issues
- Check Secret Manager configurations
- Verify VPC/firewall settings
- Monitor connection logs

### BigQuery Issues
- Verify dataset permissions
- Check external table configurations
- Monitor query quotas

## 📈 Cost Monitoring

Estimated monthly costs:
- Cloud Functions: ~$15
- Cloud Storage: ~$5  
- BigQuery: ~$8
- Cloud Scheduler: ~$1
- **Total: ~$29/month**

Monitor actual costs:
```bash
gcloud billing budgets list
```

## 🔐 Security Notes

- ✅ Database credentials stored in Secret Manager
- ✅ Service account with minimal permissions
- ✅ VPC-native networking (if configured)
- ✅ Function authentication (can be enabled)

## 📞 Support

For issues or questions:
1. Check function logs first
2. Review BigQuery external tables
3. Verify Secret Manager access
4. Monitor Cloud Storage uploads

---

**Next Step:** Connect Power BI to BigQuery views for dashboard creation!