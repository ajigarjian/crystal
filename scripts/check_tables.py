#!/usr/bin/env python
import os
import django

# Set Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'functions.factchecker.settings')

# Initialize Django
django.setup()

from django.db import connection

def check_tables():
    """Check if the tables from the migration exist in the database"""
    tables_to_check = [
        'factchecker_datagovarchivecheck',
        'factchecker_resourceavailabilitycheck'
    ]
    
    with connection.cursor() as cursor:
        for table in tables_to_check:
            cursor.execute(f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = %s
                );
            """, [table])
            
            exists = cursor.fetchone()[0]
            if exists:
                print(f"✅ Table '{table}' exists in the database.")
                
                # Check a few columns to verify structure
                cursor.execute(f"""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = %s
                    LIMIT 5;
                """, [table])
                
                columns = cursor.fetchall()
                if columns:
                    print(f"   Sample columns: {', '.join(col[0] for col in columns)}")
            else:
                print(f"❌ Table '{table}' does NOT exist in the database.")

    # Also check if existing table has the new columns
    resource_table = 'factchecker_datasetresource'
    new_columns = [
        'last_availability_check',
        'is_available',
        'availability_history',
        'in_harvard_archive',
        'harvard_archive_path'
    ]
    
    print(f"\nChecking new columns in {resource_table}:")
    with connection.cursor() as cursor:
        for column in new_columns:
            cursor.execute(f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.columns 
                    WHERE table_name = %s AND column_name = %s
                );
            """, [resource_table, column])
            
            exists = cursor.fetchone()[0]
            if exists:
                print(f"✅ Column '{column}' exists in the table.")
            else:
                print(f"❌ Column '{column}' does NOT exist in the table.")

if __name__ == "__main__":
    print("Checking if migration tables exist...\n")
    check_tables()