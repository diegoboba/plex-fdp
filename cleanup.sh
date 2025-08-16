#!/bin/bash
# ============================================
# SCRIPT DE LIMPIEZA DEL PROYECTO PLEX ETL
# ============================================

echo "🧹 Limpiando proyecto Plex ETL..."

# Crear directorio backup
mkdir -p backup/old_files
mkdir -p docs/analysis

# Mover archivos obsoletos a backup
echo "📦 Moviendo archivos obsoletos..."
files_to_backup=(
    "database_connector.py"
    "secret_manager.py" 
    "extractor.py"
    "storage.py"
    "bigquery_manager.py"
    "config.py"
    "database.py"
    "analyze_database.py"
    "get_table_sizes.py"
    "setup_secrets.py"
    "main.py"
)

for file in "${files_to_backup[@]}"; do
    if [ -f "$file" ]; then
        mv "$file" backup/old_files/
        echo "  ✅ Moved $file"
    fi
done

# Mover archivos de análisis a docs
echo "📊 Moviendo archivos de análisis..."
mv database_analysis_*.json docs/analysis/ 2>/dev/null || true
mv priority_tables_analysis_*.json docs/analysis/ 2>/dev/null || true
mv database_analysis_*.xlsx docs/analysis/ 2>/dev/null || true
mv cost_analysis.md docs/ 2>/dev/null || true

# Limpiar archivos temporales de Python
echo "🗑️ Limpiando archivos temporales..."
find . -name "*.pyc" -delete 2>/dev/null || true
find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
find . -name ".pytest_cache" -type d -exec rm -rf {} + 2>/dev/null || true

# Limpiar archivos de Jupyter
find . -name ".ipynb_checkpoints" -type d -exec rm -rf {} + 2>/dev/null || true

# Crear .env desde .env.example si no existe
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "📝 Created .env file from template"
fi

echo ""
echo "✅ Limpieza completada!"
echo ""
echo "📁 Estructura final del proyecto:"
echo "├── src/                  # Código fuente"
echo "├── scripts/              # Scripts de setup"
echo "├── tests/                # Tests"
echo "├── config/               # Configuraciones YAML"
echo "├── deploy/               # Deployment files"
echo "├── notebooks/            # Jupyter notebooks"
echo "├── docs/                 # Documentación"
echo "├── backup/               # Archivos respaldados"
echo "├── requirements.txt      # Dependencias Python"
echo "├── setup.py              # Script de setup"
echo "├── .env.example          # Template de variables"
echo "└── README.md             # Documentación principal"
echo ""
echo "🚀 Próximos pasos:"
echo "1. chmod +x cleanup.sh && ./cleanup.sh"
echo "2. python setup.py"
echo "3. python scripts/setup_secrets.py"
echo "4. python tests/test_connections.py"