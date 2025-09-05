#!/usr/bin/env python3
"""
Utility script to fix schema issues in BigQuery tables
Run this before incremental loads if you encounter schema conflicts
"""

import argparse
from google.cloud import bigquery
import yaml
import sys
import os

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.utils.config import Config

def load_schema_config():
    """Load schema strategy configuration"""
    with open('config/schema_strategy.yaml', 'r') as f:
        return yaml.safe_load(f)

def fix_table_schema(table_name: str, force_nullable: bool = True, dry_run: bool = False):
    """
    Fix schema issues for a specific table
    
    Args:
        table_name: Name of the table to fix
        force_nullable: Make all fields NULLABLE
        dry_run: Show what would be done without making changes
    """
    config = Config()
    client = bigquery.Client(project=config.GCP_PROJECT_ID)
    
    # Get MySQL schema
    print(f"\n📊 Analyzing table: {table_name}")
    
    # Check if table exists in BigQuery
    table_id = f"{config.GCP_PROJECT_ID}.{config.BIGQUERY_DATASET}.plex_{table_name}"
    
    try:
        table = client.get_table(table_id)
        print(f"✅ Table exists in BigQuery with {len(table.schema)} fields")
        
        # Show current problematic fields (REQUIRED ones)
        required_fields = [f.name for f in table.schema if f.mode == "REQUIRED"]
        if required_fields:
            print(f"⚠️  Found {len(required_fields)} REQUIRED fields: {required_fields}")
            
            if not dry_run and force_nullable:
                print(f"🔧 Converting all fields to NULLABLE...")
                
                # Create new schema with all NULLABLE
                new_schema = []
                for field in table.schema:
                    new_field = bigquery.SchemaField(
                        name=field.name,
                        field_type=field.field_type,
                        mode="NULLABLE",  # Force NULLABLE
                        description=field.description
                    )
                    new_schema.append(new_field)
                
                # Option 1: Update schema (only works for compatible changes)
                # Option 2: Recreate table (more reliable)
                
                print(f"🗑️  Dropping and recreating table with all NULLABLE fields...")
                
                # Save existing data count for validation
                query = f"SELECT COUNT(*) as cnt FROM `{table_id}`"
                result = client.query(query).result()
                original_count = list(result)[0].cnt
                print(f"📊 Table has {original_count:,} rows")
                
                # Export to temp table
                temp_table_id = f"{table_id}_temp_backup"
                print(f"💾 Creating backup at {temp_table_id}")
                
                backup_query = f"""
                CREATE OR REPLACE TABLE `{temp_table_id}` AS 
                SELECT * FROM `{table_id}`
                """
                
                if not dry_run:
                    client.query(backup_query).result()
                    print(f"✅ Backup created")
                    
                    # Drop original table
                    client.delete_table(table_id)
                    print(f"🗑️  Original table dropped")
                    
                    # Recreate with all NULLABLE schema
                    new_table = bigquery.Table(table_id, schema=new_schema)
                    client.create_table(new_table)
                    print(f"✅ Table recreated with NULLABLE schema")
                    
                    # Restore data
                    restore_query = f"""
                    INSERT INTO `{table_id}` 
                    SELECT * FROM `{temp_table_id}`
                    """
                    client.query(restore_query).result()
                    print(f"✅ Data restored")
                    
                    # Verify count
                    verify_query = f"SELECT COUNT(*) as cnt FROM `{table_id}`"
                    result = client.query(verify_query).result()
                    new_count = list(result)[0].cnt
                    
                    if new_count == original_count:
                        print(f"✅ Verification passed: {new_count:,} rows")
                        
                        # Clean up temp table
                        client.delete_table(temp_table_id)
                        print(f"🧹 Temp table cleaned up")
                    else:
                        print(f"❌ Row count mismatch! Original: {original_count}, New: {new_count}")
                        print(f"⚠️  Backup preserved at {temp_table_id}")
                else:
                    print("\n🔍 DRY RUN - Would perform:")
                    print(f"  1. Backup table to {temp_table_id}")
                    print(f"  2. Drop original table")
                    print(f"  3. Recreate with all NULLABLE fields")
                    print(f"  4. Restore {original_count:,} rows")
                    print(f"  5. Clean up temp table")
        else:
            print(f"✅ No REQUIRED fields found - table is already safe for incremental loads")
            
    except Exception as e:
        if "Not found" in str(e):
            print(f"⚠️  Table {table_id} does not exist in BigQuery")
        else:
            print(f"❌ Error: {e}")

def fix_all_tables(dry_run: bool = False):
    """Fix schema issues for all tables"""
    # Load incremental strategy to get table list
    with open('config/incremental_strategy.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    tables = []
    for db_config in config.get('databases', {}).values():
        for priority_group in ['priority_tables', 'medium_priority_tables', 'low_priority_tables']:
            if priority_group in db_config:
                tables.extend(db_config[priority_group].keys())
    
    print(f"\n📋 Found {len(tables)} tables to check")
    
    issues_found = []
    for table in tables:
        try:
            print(f"\n{'='*60}")
            fix_table_schema(table, force_nullable=True, dry_run=dry_run)
        except Exception as e:
            print(f"❌ Error processing {table}: {e}")
            issues_found.append(table)
    
    if issues_found:
        print(f"\n⚠️  Issues found in: {issues_found}")
    else:
        print(f"\n✅ All tables checked successfully")

def main():
    parser = argparse.ArgumentParser(description='Fix BigQuery schema issues for safe incremental loads')
    parser.add_argument('--table', type=str, help='Specific table to fix (or "all" for all tables)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without making changes')
    parser.add_argument('--force', action='store_true', help='Force fix without confirmation')
    
    args = parser.parse_args()
    
    # Set up Google Cloud credentials
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'etl-service-account-key.json'
    
    print("🔧 BigQuery Schema Fixer")
    print("=" * 60)
    
    schema_config = load_schema_config()
    if schema_config['global_settings']['force_all_nullable']:
        print("✅ Schema strategy: All fields will be NULLABLE (safe mode)")
    else:
        print("⚠️  Schema strategy: Mixed REQUIRED/NULLABLE (strict mode)")
    
    if args.table:
        if args.table.lower() == 'all':
            if not args.force and not args.dry_run:
                response = input("\n⚠️  This will check ALL tables. Continue? (y/n): ")
                if response.lower() != 'y':
                    print("Cancelled")
                    return
            fix_all_tables(dry_run=args.dry_run)
        else:
            fix_table_schema(args.table, force_nullable=True, dry_run=args.dry_run)
    else:
        print("\nUsage:")
        print("  python fix_schema_issues.py --table factcabecera")
        print("  python fix_schema_issues.py --table all --dry-run")
        print("  python fix_schema_issues.py --table all --force")

if __name__ == "__main__":
    main()