"""
Schema Reconciler for BigQuery Tables
Handles schema evolution and conflicts between MySQL source and BigQuery destination
"""

from google.cloud import bigquery
from typing import List, Dict, Optional
import json

class SchemaReconciler:
    """Reconciles schema differences between MySQL and BigQuery"""
    
    def __init__(self, bq_client: bigquery.Client, project_id: str, dataset_id: str):
        self.client = bq_client
        self.project_id = project_id
        self.dataset_id = dataset_id
    
    def get_existing_schema(self, table_name: str) -> Optional[List[bigquery.SchemaField]]:
        """Get existing BigQuery table schema if it exists"""
        try:
            table_id = f"{self.project_id}.{self.dataset_id}.{table_name}"
            table = self.client.get_table(table_id)
            return list(table.schema)
        except Exception:
            return None
    
    def reconcile_schemas(self, 
                         table_name: str,
                         new_schema: List[bigquery.SchemaField],
                         force_nullable: bool = True) -> List[bigquery.SchemaField]:
        """
        Reconcile new schema with existing table schema
        
        Args:
            table_name: BigQuery table name
            new_schema: Schema from MySQL/ETL
            force_nullable: If True, always use NULLABLE mode for safety
            
        Returns:
            Reconciled schema that works with existing table
        """
        existing_schema = self.get_existing_schema(table_name)
        
        # If table doesn't exist, use new schema but make everything NULLABLE for safety
        if not existing_schema:
            if force_nullable:
                return self._make_all_nullable(new_schema)
            return new_schema
        
        # Build lookup maps
        existing_fields = {field.name: field for field in existing_schema}
        new_fields = {field.name: field for field in new_schema}
        
        reconciled_schema = []
        
        # Process each field from new schema
        for field_name, new_field in new_fields.items():
            if field_name in existing_fields:
                existing_field = existing_fields[field_name]
                
                # Use the MORE PERMISSIVE mode
                # NULLABLE is more permissive than REQUIRED
                if existing_field.mode == "REQUIRED" and new_field.mode == "NULLABLE":
                    # Keep REQUIRED from existing (can't change REQUIRED to NULLABLE)
                    reconciled_field = bigquery.SchemaField(
                        name=field_name,
                        field_type=existing_field.field_type,
                        mode="REQUIRED",  # Keep existing REQUIRED
                        description=new_field.description
                    )
                elif existing_field.mode == "NULLABLE" and new_field.mode == "REQUIRED":
                    # Keep NULLABLE (more permissive)
                    reconciled_field = bigquery.SchemaField(
                        name=field_name,
                        field_type=existing_field.field_type,
                        mode="NULLABLE",  # Keep existing NULLABLE
                        description=new_field.description
                    )
                else:
                    # Same mode or both NULLABLE - use existing
                    reconciled_field = existing_field
                
                reconciled_schema.append(reconciled_field)
            else:
                # New field not in existing - add as NULLABLE for safety
                reconciled_field = bigquery.SchemaField(
                    name=field_name,
                    field_type=new_field.field_type,
                    mode="NULLABLE",  # Always NULLABLE for new fields
                    description=new_field.description
                )
                reconciled_schema.append(reconciled_field)
        
        # Check for fields that exist in BigQuery but not in new schema
        # These should be kept to avoid breaking existing queries
        for field_name, existing_field in existing_fields.items():
            if field_name not in new_fields:
                print(f"⚠️  Field '{field_name}' exists in BigQuery but not in source - keeping it")
                reconciled_schema.append(existing_field)
        
        return reconciled_schema
    
    def _make_all_nullable(self, schema: List[bigquery.SchemaField]) -> List[bigquery.SchemaField]:
        """Make all fields NULLABLE for maximum flexibility"""
        nullable_schema = []
        for field in schema:
            nullable_field = bigquery.SchemaField(
                name=field.name,
                field_type=field.field_type,
                mode="NULLABLE",  # Force NULLABLE
                description=field.description
            )
            nullable_schema.append(nullable_field)
        return nullable_schema
    
    def update_table_schema_if_needed(self, 
                                     table_name: str,
                                     new_schema: List[bigquery.SchemaField]) -> bool:
        """
        Update table schema if compatible changes are needed
        
        Returns:
            True if schema was updated, False otherwise
        """
        try:
            table_id = f"{self.project_id}.{self.dataset_id}.{table_name}"
            table = self.client.get_table(table_id)
            
            # Check if we need to add new fields
            existing_field_names = {f.name for f in table.schema}
            new_field_names = {f.name for f in new_schema}
            
            fields_to_add = new_field_names - existing_field_names
            
            if fields_to_add:
                print(f"📝 Adding {len(fields_to_add)} new fields to {table_name}: {fields_to_add}")
                
                # Build updated schema
                updated_schema = list(table.schema)
                for field in new_schema:
                    if field.name in fields_to_add:
                        # New fields must be NULLABLE
                        nullable_field = bigquery.SchemaField(
                            name=field.name,
                            field_type=field.field_type,
                            mode="NULLABLE",
                            description=field.description
                        )
                        updated_schema.append(nullable_field)
                
                # Update table
                table.schema = updated_schema
                self.client.update_table(table, ["schema"])
                print(f"✅ Schema updated for {table_name}")
                return True
            
            return False
            
        except Exception as e:
            print(f"⚠️  Could not update schema for {table_name}: {e}")
            return False
    
    def get_safe_schema_for_incremental(self, 
                                       table_name: str,
                                       mysql_schema: List[bigquery.SchemaField]) -> List[bigquery.SchemaField]:
        """
        Get a schema that will work for incremental loads
        Always returns a schema compatible with existing table
        """
        existing_schema = self.get_existing_schema(table_name)
        
        if not existing_schema:
            # Table doesn't exist - use all NULLABLE for safety
            print(f"📋 Creating new table {table_name} with all NULLABLE fields for safety")
            return self._make_all_nullable(mysql_schema)
        
        # Reconcile with existing
        reconciled = self.reconcile_schemas(table_name, mysql_schema, force_nullable=False)
        
        # Log any differences
        mysql_fields = {f.name: f.mode for f in mysql_schema}
        reconciled_fields = {f.name: f.mode for f in reconciled}
        
        for field_name in mysql_fields:
            if field_name in reconciled_fields:
                if mysql_fields[field_name] != reconciled_fields[field_name]:
                    print(f"🔄 Schema reconciliation for {table_name}.{field_name}: "
                          f"{mysql_fields[field_name]} → {reconciled_fields[field_name]}")
        
        return reconciled