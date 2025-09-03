"""Generate MySQL structure documentation automatically"""

import yaml
import os
from datetime import datetime
from typing import Dict, List
from .schema_mapper import SchemaMapper

class MySQLStructureGenerator:
    """Generates and updates MySQL structure documentation"""
    
    def __init__(self, output_path: str = None):
        if output_path is None:
            # Default to config directory
            self.output_path = os.path.join(
                os.path.dirname(__file__), '../../config/mysql_structure.yaml'
            )
        else:
            self.output_path = output_path
            
        # Initialize structure if file doesn't exist
        if not os.path.exists(self.output_path):
            self._create_initial_structure()
    
    def _create_initial_structure(self):
        """Create initial YAML structure"""
        initial_structure = {
            'metadata': {
                'generated_at': datetime.now().isoformat(),
                'last_updated': datetime.now().isoformat(),
                'generator': 'mysql_structure_generator.py',
                'version': '1.0'
            },
            'databases': {}
        }
        
        self._save_structure(initial_structure)
    
    def update_table_structure(self, database_name: str, table_name: str, 
                             mysql_columns: List[Dict], row_count: int = None):
        """Update structure for a specific table"""
        
        # Load existing structure
        structure = self._load_structure()
        
        # Ensure database exists in structure
        if database_name not in structure['databases']:
            structure['databases'][database_name] = {
                'tables': {},
                'last_updated': datetime.now().isoformat()
            }
        
        # Process columns
        table_info = {
            'column_count': len(mysql_columns),
            'last_analyzed': datetime.now().isoformat(),
            'columns': {},
            'mysql_types': {},
            'bigquery_types': {},
            'schema_summary': {
                'strings': 0,
                'integers': 0,
                'floats': 0,
                'dates': 0,
                'booleans': 0,
                'others': 0
            }
        }
        
        if row_count is not None:
            table_info['estimated_rows'] = row_count
        
        # Process each column
        for col in mysql_columns:
            col_name = col['COLUMN_NAME']
            mysql_type = col['COLUMN_TYPE']
            data_type = col['DATA_TYPE'] 
            bq_type = SchemaMapper.mysql_to_bigquery_type(mysql_type)
            is_nullable = col['IS_NULLABLE'] == 'YES'
            
            # Detailed column info
            table_info['columns'][col_name] = {
                'mysql_type': mysql_type,
                'mysql_data_type': data_type,
                'bigquery_type': bq_type,
                'nullable': True,  # Always nullable in BigQuery to avoid data loading errors
                'mysql_nullable': is_nullable,  # Keep original MySQL nullable info
                'default': col.get('COLUMN_DEFAULT'),
                'comment': col.get('COLUMN_COMMENT', ''),
                'max_length': col.get('CHARACTER_MAXIMUM_LENGTH'),
                'numeric_precision': col.get('NUMERIC_PRECISION'),
                'numeric_scale': col.get('NUMERIC_SCALE')
            }
            
            # Quick reference mappings
            table_info['mysql_types'][col_name] = mysql_type
            table_info['bigquery_types'][col_name] = bq_type
            
            # Count by BigQuery type for summary
            if bq_type == 'STRING':
                table_info['schema_summary']['strings'] += 1
            elif bq_type == 'INT64':
                table_info['schema_summary']['integers'] += 1
            elif bq_type in ['FLOAT64', 'NUMERIC']:
                table_info['schema_summary']['floats'] += 1
            elif bq_type in ['DATE', 'TIME', 'TIMESTAMP']:
                table_info['schema_summary']['dates'] += 1
            elif bq_type == 'BOOL':
                table_info['schema_summary']['booleans'] += 1
            else:
                table_info['schema_summary']['others'] += 1
        
        # Update structure
        structure['databases'][database_name]['tables'][table_name] = table_info
        structure['databases'][database_name]['last_updated'] = datetime.now().isoformat()
        structure['metadata']['last_updated'] = datetime.now().isoformat()
        
        # Save updated structure
        self._save_structure(structure)
        
        print(f"✅ Updated MySQL structure for {database_name}.{table_name}")
        print(f"   📊 {len(mysql_columns)} columns: {table_info['schema_summary']}")
    
    def _load_structure(self) -> dict:
        """Load existing structure from YAML file"""
        try:
            if os.path.exists(self.output_path):
                with open(self.output_path, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f)
            else:
                self._create_initial_structure()
                with open(self.output_path, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f)
        except Exception as e:
            print(f"⚠️  Error loading structure file: {e}")
            print("Creating new structure file...")
            self._create_initial_structure()
            with open(self.output_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
    
    def _save_structure(self, structure: dict):
        """Save structure to YAML file"""
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.output_path), exist_ok=True)
            
            with open(self.output_path, 'w', encoding='utf-8') as f:
                yaml.dump(structure, f, 
                         default_flow_style=False, 
                         allow_unicode=True, 
                         indent=2, 
                         sort_keys=False,
                         width=float('inf'))
        except Exception as e:
            print(f"❌ Error saving structure file: {e}")
            raise
    
    def get_table_schema_for_bigquery(self, database_name: str, table_name: str) -> List:
        """Get BigQuery schema for a table from saved structure"""
        try:
            structure = self._load_structure()
            table_info = structure['databases'][database_name]['tables'][table_name]
            
            # Convert to BigQuery schema format
            schema = []
            for col_name, col_info in table_info['columns'].items():
                from google.cloud import bigquery
                
                schema_field = bigquery.SchemaField(
                    name=col_name,
                    field_type=col_info['bigquery_type'],
                    mode='NULLABLE',  # Always nullable for BigQuery compatibility
                    description=f"MySQL: {col_info['mysql_type']}"
                )
                schema.append(schema_field)
            
            return schema
            
        except Exception as e:
            print(f"⚠️  Could not load schema from structure file: {e}")
            return None
    
    def print_database_summary(self, database_name: str = None):
        """Print summary of database structure"""
        structure = self._load_structure()
        
        if database_name:
            databases_to_show = [database_name] if database_name in structure['databases'] else []
        else:
            databases_to_show = list(structure['databases'].keys())
        
        print(f"\n{'='*60}")
        print(f"MySQL Structure Summary")
        print(f"Generated: {structure['metadata']['last_updated']}")
        print(f"{'='*60}")
        
        for db_name in databases_to_show:
            db_info = structure['databases'][db_name]
            print(f"\n📀 Database: {db_name}")
            print(f"   Last Updated: {db_info['last_updated']}")
            print(f"   Tables: {len(db_info['tables'])}")
            
            for table_name, table_info in db_info['tables'].items():
                summary = table_info['schema_summary']
                print(f"   📊 {table_name}: {table_info['column_count']} columns "
                      f"(S:{summary['strings']}, I:{summary['integers']}, "
                      f"F:{summary['floats']}, D:{summary['dates']}, B:{summary['booleans']})")
                      
                if 'estimated_rows' in table_info:
                    print(f"      Rows: ~{table_info['estimated_rows']:,}")
        
        print(f"\n{'='*60}")