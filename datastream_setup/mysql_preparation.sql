-- ============================================
-- PREPARACIÓN DE MYSQL PARA DATASTREAM CDC
-- ============================================

-- 1. Verificar configuración actual de binlog
SHOW VARIABLES LIKE 'log_bin';
SHOW VARIABLES LIKE 'binlog_format';
SHOW VARIABLES LIKE 'binlog_row_image';

-- 2. Configuraciones necesarias en my.cnf (requiere reinicio de MySQL):
/*
[mysqld]
log-bin=mysql-bin
binlog-format=ROW
binlog-row-image=FULL
server-id=1
*/

-- 3. Crear usuario para Datastream con permisos necesarios
CREATE USER 'datastream'@'%' IDENTIFIED BY 'STRONG_PASSWORD_HERE';

-- Permisos para replicación
GRANT REPLICATION SLAVE, REPLICATION CLIENT ON *.* TO 'datastream'@'%';

-- Permisos de lectura en las bases específicas
GRANT SELECT ON plex.* TO 'datastream'@'%';
GRANT SELECT ON quantio.* TO 'datastream'@'%';

-- Aplicar cambios
FLUSH PRIVILEGES;

-- 4. Verificar estado de replicación
SHOW MASTER STATUS;

-- 5. Verificar tablas que se van a replicar
-- Base Plex
USE plex;
SHOW TABLES;
SELECT COUNT(*) FROM factcabecera;
SELECT COUNT(*) FROM factlineas;
SELECT COUNT(*) FROM sucursales;
SELECT COUNT(*) FROM medicamentos;

-- Base Quantio  
USE quantio;
SHOW TABLES;
SELECT COUNT(*) FROM plex_pedidos;
SELECT COUNT(*) FROM plex_pedidoslineas;
SELECT COUNT(*) FROM reporte_bi;

-- 6. Verificar claves primarias (Datastream las necesita)
SELECT 
    TABLE_SCHEMA,
    TABLE_NAME,
    COLUMN_NAME,
    CONSTRAINT_NAME
FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE 
WHERE CONSTRAINT_NAME = 'PRIMARY' 
AND TABLE_SCHEMA IN ('plex', 'quantio')
ORDER BY TABLE_SCHEMA, TABLE_NAME;

-- 7. Verificar conexiones permitidas
SHOW VARIABLES LIKE 'bind_address';
SHOW VARIABLES LIKE 'max_connections';