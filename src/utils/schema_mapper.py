"""Schema mapping utilities for MySQL to BigQuery conversion"""

from google.cloud import bigquery
from typing import Dict, List, Tuple
import yaml
import os
import pandas as pd

class SchemaMapper:
    """Maps MySQL schema to BigQuery schema"""
    
    # MySQL to BigQuery type mapping
    MYSQL_TO_BQ_TYPE_MAP = {
        # Integer types
        'tinyint': 'INT64',
        'smallint': 'INT64', 
        'mediumint': 'INT64',
        'int': 'INT64',
        'integer': 'INT64',
        'bigint': 'INT64',
        
        # Floating point types
        'float': 'FLOAT64',
        'double': 'FLOAT64',
        'decimal': 'NUMERIC',
        'numeric': 'NUMERIC',
        
        # String types
        'char': 'STRING',
        'varchar': 'STRING',
        'text': 'STRING',
        'tinytext': 'STRING',
        'mediumtext': 'STRING',
        'longtext': 'STRING',
        'enum': 'STRING',
        'set': 'STRING',
        
        # Date/time types
        'date': 'DATE',
        'time': 'TIME',
        'datetime': 'TIMESTAMP',
        'timestamp': 'TIMESTAMP',
        'year': 'INT64',
        
        # Binary types
        'binary': 'BYTES',
        'varbinary': 'BYTES',
        'blob': 'BYTES',
        'tinyblob': 'BYTES',
        'mediumblob': 'BYTES',
        'longblob': 'BYTES',
        
        # Boolean
        'bit': 'BOOL',
        'boolean': 'BOOL',
        'bool': 'BOOL',
        
        # JSON
        'json': 'STRING'  # BigQuery has JSON type but STRING is safer for mixed data
    }
    
    @classmethod
    def mysql_to_bigquery_type(cls, mysql_type: str) -> str:
        """Convert MySQL data type to BigQuery data type"""
        # Clean the type (remove size specifications, unsigned, etc.)
        full_type = mysql_type.lower().strip()
        base_type = full_type.split('(')[0].strip()
        
        # Handle special cases first
        # Handle tinyint(1) as boolean (common MySQL pattern)
        if 'tinyint(1)' in full_type:
            return 'BOOL'
        
        # Handle varchar, char, text types
        if base_type in ['varchar', 'char', 'text', 'tinytext', 'mediumtext', 'longtext']:
            return 'STRING'
            
        # Handle unsigned integers
        if 'unsigned' in full_type:
            if base_type in ['tinyint', 'smallint', 'mediumint', 'int', 'integer', 'bigint']:
                return 'INT64'
        
        # Handle regular types
        result = cls.MYSQL_TO_BQ_TYPE_MAP.get(base_type, 'STRING')
        return result
    
    @classmethod
    def create_bigquery_schema(cls, mysql_columns: List[Dict]) -> List[bigquery.SchemaField]:
        """Create BigQuery schema from MySQL column information"""
        schema_fields = []
        
        for col in mysql_columns:
            field_name = col['COLUMN_NAME']
            mysql_type = col['COLUMN_TYPE']  # Use COLUMN_TYPE instead of DATA_TYPE
            is_nullable = col['IS_NULLABLE'] == 'YES'
            
            # Convert MySQL type to BigQuery type
            bq_type = cls.mysql_to_bigquery_type(mysql_type)
            
            # Set mode - ALWAYS use NULLABLE to avoid missing value errors in BigQuery
            # BigQuery is very strict with REQUIRED fields and MySQL data often has NULLs
            mode = 'NULLABLE'
            
            schema_field = bigquery.SchemaField(
                name=field_name,
                field_type=bq_type,
                mode=mode,
                description=f"MySQL: {mysql_type}"
            )
            
            schema_fields.append(schema_field)
        
        return schema_fields
    
    @classmethod
    def update_yaml_config(cls, database_name: str, table_name: str, 
                          mysql_columns: List[Dict], config_path: str):
        """Update YAML configuration with discovered schema information"""
        
        try:
            # Load existing config
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            # Navigate to the table config
            db_config = config['databases'].get(database_name, {})
            
            # Create schema info
            schema_info = {
                'columns_schema': {},
                'mysql_types': {},
                'bigquery_types': {}
            }
            
            column_names = []
            for col in mysql_columns:
                col_name = col['COLUMN_NAME']
                mysql_type = col['COLUMN_TYPE']  # Use COLUMN_TYPE
                bq_type = cls.mysql_to_bigquery_type(mysql_type)
                is_nullable = col['IS_NULLABLE'] == 'YES'
                
                column_names.append(col_name)
                schema_info['columns_schema'][col_name] = {
                    'mysql_type': mysql_type,
                    'bigquery_type': bq_type,
                    'nullable': is_nullable,
                    'default': col.get('COLUMN_DEFAULT'),
                    'comment': col.get('COLUMN_COMMENT', '')
                }
                schema_info['mysql_types'][col_name] = mysql_type
                schema_info['bigquery_types'][col_name] = bq_type
            
            # Update the table configuration
            if 'priority_tables' not in db_config:
                db_config['priority_tables'] = {}
            
            if table_name not in db_config['priority_tables']:
                db_config['priority_tables'][table_name] = {}
            
            table_config = db_config['priority_tables'][table_name]
            
            # Update with schema information
            table_config['columns'] = len(column_names)
            table_config['columns_detail'] = column_names
            table_config.update(schema_info)
            table_config['schema_updated'] = True
            table_config['schema_update_timestamp'] = str(pd.Timestamp.now())
            
            # Save updated config with proper formatting
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, default_flow_style=False, allow_unicode=True, 
                         indent=2, sort_keys=False, width=float('inf'))
            
            print(f"✅ Updated YAML config for {database_name}.{table_name}")
            
        except Exception as e:
            print(f"❌ Error updating YAML config: {e}")
            print("⚠️  Continuing without YAML update...")
    
    @classmethod 
    def print_schema_comparison(cls, table_name: str, mysql_columns: List[Dict]):
        """Print schema comparison for debugging"""
        print(f"\n=== Schema for {table_name} ===")
        print(f"{'Column':<25} {'MySQL Type':<20} {'BigQuery Type':<15} {'Nullable'}")
        print("-" * 80)
        
        for col in mysql_columns:
            col_name = col['COLUMN_NAME']
            mysql_type = col['COLUMN_TYPE']  # Use COLUMN_TYPE
            bq_type = cls.mysql_to_bigquery_type(mysql_type)
            nullable = 'YES' if col['IS_NULLABLE'] == 'YES' else 'NO'
            
            print(f"{col_name:<25} {mysql_type:<20} {bq_type:<15} {nullable}")