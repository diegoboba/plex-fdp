# 🔒 SECURITY - Configuración de Seguridad

## ⚠️ IMPORTANTE: Información Sensible

Este proyecto **NO contiene** credenciales, contraseñas o keys en el código fuente.

### ✅ Archivos Excluidos de Git

Los siguientes archivos sensibles están en `.gitignore` y **NUNCA** deben subirse a Git:

```
etl-service-account-key.json     # ❌ NUNCA commitear
*credential*.json                 # ❌ NUNCA commitear  
*secret*.json                     # ❌ NUNCA commitear
*.key                            # ❌ NUNCA commitear
.env                             # ❌ NUNCA commitear
secrets_setup.sh                 # ❌ NUNCA commitear
```

### 🔐 Gestión de Credenciales

El proyecto usa **Google Secret Manager** para almacenar credenciales de forma segura:

1. **MySQL Credentials**: Almacenadas en Secret Manager
   - `mysql-plex-config`: Credenciales para base de datos Plex
   - `mysql-quantio-config`: Credenciales para base de datos Quantio

2. **Service Account Key**: Requerida localmente
   - Archivo: `etl-service-account-key.json`
   - **NO incluida en el repositorio**
   - Debe obtenerse del administrador del proyecto

### 📋 Setup de Seguridad

#### 1. Obtener Service Account Key

Contacta al administrador para obtener el archivo `etl-service-account-key.json`

#### 2. Configurar Variable de Entorno

```bash
export GOOGLE_APPLICATION_CREDENTIALS="./etl-service-account-key.json"
export GCP_PROJECT_ID="plex-etl-project"
```

#### 3. Verificar Permisos

El service account necesita estos roles:
- `roles/secretmanager.secretAccessor` - Para leer secrets
- `roles/bigquery.admin` - Para gestionar BigQuery
- `roles/storage.admin` - Para Cloud Storage (si se usa)

### 🛡️ Mejores Prácticas

1. **NUNCA** hardcodees credenciales en el código
2. **NUNCA** commitees archivos `.json` con credenciales
3. **SIEMPRE** usa Google Secret Manager para credenciales
4. **SIEMPRE** verifica `.gitignore` antes de commitear
5. **ROTA** las keys periódicamente

### 🔍 Verificación de Seguridad

Antes de hacer push, ejecuta:

```bash
# Verificar que no haya credenciales en el código
grep -r "password\|secret\|key" --exclude-dir=.git --exclude-dir=plex --exclude-dir=backup .

# Verificar que .gitignore esté funcionando
git status --ignored

# Verificar que el archivo de credenciales NO esté en git
git ls-files | grep -E "\.json|\.key|\.env"
```

### 📞 Contacto de Seguridad

Si encuentras información sensible en el repositorio:
1. **NO hagas push**
2. Contacta inmediatamente al administrador
3. Elimina el archivo del historial de git si ya fue commiteado

### 🚨 En Caso de Exposición de Credenciales

Si accidentalmente se exponen credenciales:

1. **Rota inmediatamente** las credenciales expuestas
2. **Elimina** el commit del historial usando:
   ```bash
   git filter-branch --tree-filter 'rm -f archivo-sensible.json' HEAD
   ```
3. **Notifica** al equipo de seguridad
4. **Audita** los logs para detectar accesos no autorizados

---

**Última revisión de seguridad**: 2025-08-26  
**Próxima revisión programada**: Mensual