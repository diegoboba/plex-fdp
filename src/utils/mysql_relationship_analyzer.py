#!/usr/bin/env python3
"""
MySQL Relationship Analyzer
Discovers foreign keys and relationships between tables to improve JOIN queries
"""

import pandas as pd
import yaml
import os
from database.connector import DatabaseConnector
from datetime import datetime

class MySQLRelationshipAnalyzer:
    def __init__(self):
        self.db = DatabaseConnector()
        
    def analyze_foreign_keys(self, database_name: str) -> pd.DataFrame:
        """Get all foreign key constraints"""
        query = """
        SELECT 
            TABLE_NAME,
            COLUMN_NAME,
            CONSTRAINT_NAME,
            REFERENCED_TABLE_NAME,
            REFERENCED_COLUMN_NAME
        FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE 
        WHERE REFERENCED_TABLE_SCHEMA = DATABASE()
          AND REFERENCED_TABLE_NAME IS NOT NULL
        ORDER BY TABLE_NAME, COLUMN_NAME
        """
        
        connection = self.db.get_mysql_connection(database_name)
        try:
            with connection.cursor() as cursor:
                cursor.execute(query)
                results = cursor.fetchall()
                if results:
                    return pd.DataFrame(results)
                else:
                    return pd.DataFrame()
        finally:
            connection.close()
    
    def analyze_common_columns(self, database_name: str) -> pd.DataFrame:
        """Find columns with same names that likely indicate relationships"""
        query = """
        SELECT 
            t1.TABLE_NAME as table1,
            t1.COLUMN_NAME as column1,
            t2.TABLE_NAME as table2, 
            t2.COLUMN_NAME as column2,
            t1.DATA_TYPE as data_type1,
            t2.DATA_TYPE as data_type2
        FROM INFORMATION_SCHEMA.COLUMNS t1
        JOIN INFORMATION_SCHEMA.COLUMNS t2 
            ON t1.COLUMN_NAME = t2.COLUMN_NAME
            AND t1.TABLE_NAME != t2.TABLE_NAME
            AND t1.TABLE_SCHEMA = t2.TABLE_SCHEMA
        WHERE t1.TABLE_SCHEMA = DATABASE()
          AND (t1.COLUMN_NAME LIKE '%ID%' 
               OR t1.COLUMN_NAME LIKE '%id%'
               OR t1.COLUMN_NAME LIKE '%numero%'
               OR t1.COLUMN_NAME LIKE '%comprobante%')
        ORDER BY t1.COLUMN_NAME, t1.TABLE_NAME
        """
        
        connection = self.db.get_mysql_connection(database_name)
        try:
            with connection.cursor() as cursor:
                cursor.execute(query)
                results = cursor.fetchall()
                if results:
                    return pd.DataFrame(results)
                else:
                    return pd.DataFrame()
        finally:
            connection.close()
    
    def analyze_invoice_tables(self, database_name: str) -> pd.DataFrame:
        """Analyze specific columns in invoice-related tables"""
        invoice_tables = ['factcabecera', 'factlineas', 'factlineascostos', 'factcoberturas', 'factpagos', 'factreglasaplicadas']
        
        table_list = "'" + "','".join(invoice_tables) + "'"
        
        query = f"""
        SELECT 
            c.TABLE_NAME,
            c.COLUMN_NAME,
            c.DATA_TYPE,
            c.IS_NULLABLE,
            c.COLUMN_KEY,
            c.COLUMN_COMMENT
        FROM INFORMATION_SCHEMA.COLUMNS c
        WHERE c.TABLE_SCHEMA = DATABASE()
          AND c.TABLE_NAME IN ({table_list})
          AND (c.COLUMN_NAME LIKE '%ID%' 
               OR c.COLUMN_NAME LIKE '%numero%'
               OR c.COLUMN_NAME LIKE '%comprobante%'
               OR c.COLUMN_KEY = 'PRI')
        ORDER BY c.TABLE_NAME, c.COLUMN_NAME
        """
        
        connection = self.db.get_mysql_connection(database_name)
        try:
            with connection.cursor() as cursor:
                cursor.execute(query)
                results = cursor.fetchall()
                if results:
                    return pd.DataFrame(results)
                else:
                    return pd.DataFrame()
        finally:
            connection.close()
    
    def test_join_relationship(self, database_name: str, table1: str, table2: str, join_column: str) -> dict:
        """Test if a JOIN relationship works and get statistics"""
        query = f"""
        SELECT 
            COUNT(*) as total_joined_rows,
            COUNT(DISTINCT t1.{join_column}) as unique_t1_keys,
            COUNT(DISTINCT t2.{join_column}) as unique_t2_keys
        FROM {table1} t1
        INNER JOIN {table2} t2 ON t1.{join_column} = t2.{join_column}
        WHERE t1.{join_column} IS NOT NULL AND t2.{join_column} IS NOT NULL
        """
        
        connection = self.db.get_mysql_connection(database_name)
        try:
            with connection.cursor() as cursor:
                cursor.execute(query)
                result = cursor.fetchone()
                return {
                    'table1': table1,
                    'table2': table2,
                    'join_column': join_column,
                    'total_joined_rows': result['total_joined_rows'],
                    'unique_t1_keys': result['unique_t1_keys'],
                    'unique_t2_keys': result['unique_t2_keys'],
                    'join_works': result['total_joined_rows'] > 0
                }
        except Exception as e:
            return {
                'table1': table1,
                'table2': table2,
                'join_column': join_column,
                'error': str(e),
                'join_works': False
            }
        finally:
            connection.close()
    
    def sample_table_data(self, database_name: str, table_name: str, key_columns: list) -> pd.DataFrame:
        """Get sample data to understand relationships"""
        columns_str = ', '.join(key_columns)
        query = f"SELECT {columns_str} FROM {table_name} LIMIT 10"
        
        connection = self.db.get_mysql_connection(database_name)
        try:
            with connection.cursor() as cursor:
                cursor.execute(query)
                results = cursor.fetchall()
                if results:
                    return pd.DataFrame(results)
                else:
                    return pd.DataFrame()
        finally:
            connection.close()
    
    def generate_relationship_report(self, database_name: str) -> dict:
        """Generate comprehensive relationship analysis report"""
        print(f"🔍 Analyzing relationships in {database_name} database...")
        
        report = {
            'database': database_name,
            'analyzed_at': datetime.now().isoformat(),
            'foreign_keys': [],
            'common_columns': [],
            'invoice_table_analysis': [],
            'join_tests': [],
            'recommendations': []
        }
        
        # 1. Foreign Keys Analysis
        print("📋 Analyzing formal foreign keys...")
        fk_df = self.analyze_foreign_keys(database_name)
        if not fk_df.empty:
            report['foreign_keys'] = fk_df.to_dict('records')
            print(f"   Found {len(fk_df)} foreign key relationships")
        else:
            print("   No formal foreign keys found")
        
        # 2. Common Columns Analysis
        print("🔗 Analyzing common column patterns...")
        common_df = self.analyze_common_columns(database_name)
        if not common_df.empty:
            report['common_columns'] = common_df.to_dict('records')
            print(f"   Found {len(common_df)} potential relationships by column name")
        else:
            print("   No common column patterns found")
        
        # 3. Invoice Tables Analysis
        print("💰 Analyzing invoice table structures...")
        invoice_df = self.analyze_invoice_tables(database_name)
        if not invoice_df.empty:
            report['invoice_table_analysis'] = invoice_df.to_dict('records')
            print(f"   Analyzed {len(invoice_df)} key columns in invoice tables")
        
        # 4. Test specific JOIN relationships
        print("🧪 Testing critical JOIN relationships...")
        
        # Test factcabecera <-> factlineas relationship
        test_results = []
        
        # Test IDComprobante join
        result = self.test_join_relationship(database_name, 'factcabecera', 'factlineas', 'IDComprobante')
        test_results.append(result)
        print(f"   factcabecera ↔ factlineas via IDComprobante: {'✅' if result['join_works'] else '❌'}")
        
        # Test other potential joins
        potential_joins = [
            ('factcabecera', 'factlineascostos', 'IDComprobante'),
            ('factcabecera', 'factcoberturas', 'IDComprobante'),
            ('factcabecera', 'factpagos', 'IDComprobante'),
            ('factcabecera', 'factreglasaplicadas', 'IDComprobante'),
        ]
        
        for table1, table2, join_col in potential_joins:
            result = self.test_join_relationship(database_name, table1, table2, join_col)
            test_results.append(result)
            status = '✅' if result['join_works'] else '❌'
            print(f"   {table1} ↔ {table2} via {join_col}: {status}")
        
        report['join_tests'] = test_results
        
        # 5. Generate recommendations
        print("💡 Generating recommendations...")
        recommendations = []
        
        working_joins = [r for r in test_results if r['join_works']]
        for join in working_joins:
            recommendations.append({
                'type': 'confirmed_join',
                'message': f"Use {join['join_column']} to join {join['table1']} and {join['table2']}",
                'yaml_update': f"INNER JOIN {join['table1']} ON {join['table2']}.{join['join_column']} = {join['table1']}.{join['join_column']}"
            })
        
        report['recommendations'] = recommendations
        
        return report
    
    def save_relationship_report(self, report: dict, output_path: str = None):
        """Save relationship analysis report to YAML file"""
        if output_path is None:
            output_path = os.path.join(os.path.dirname(__file__), '../../config/mysql_relationships.yaml')
        
        try:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                yaml.dump(report, f, 
                         default_flow_style=False, 
                         allow_unicode=True, 
                         indent=2, 
                         sort_keys=False,
                         width=float('inf'))
            
            print(f"💾 Relationship report saved to {output_path}")
            
        except Exception as e:
            print(f"❌ Error saving report: {e}")

def main():
    """Run relationship analysis for both databases"""
    analyzer = MySQLRelationshipAnalyzer()
    
    # Analyze Plex database
    print("="*60)
    print("🏥 PLEX DATABASE ANALYSIS")
    print("="*60)
    
    plex_report = analyzer.generate_relationship_report('plex')
    analyzer.save_relationship_report(plex_report, 'config/mysql_relationships_plex.yaml')
    
    # Analyze Quantio database  
    print("\n" + "="*60)
    print("📊 QUANTIO DATABASE ANALYSIS")
    print("="*60)
    
    quantio_report = analyzer.generate_relationship_report('quantio')
    analyzer.save_relationship_report(quantio_report, 'config/mysql_relationships_quantio.yaml')
    
    print("\n🎉 Relationship analysis completed!")
    print("📋 Check the generated YAML files for detailed results.")

if __name__ == "__main__":
    main()