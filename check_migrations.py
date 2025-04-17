#!/usr/bin/env python
import os
import django

# Set Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'functions.factchecker.settings')

# Initialize Django
django.setup()

from django.db import connection

def check_migrations():
    """Check which migrations have been applied in the database"""
    with connection.cursor() as cursor:
        # Check if the migrations table exists
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'django_migrations'
            );
        """)
        table_exists = cursor.fetchone()[0]
        
        if not table_exists:
            print("The django_migrations table does not exist in the database.")
            return
        
        # Get all migrations for factchecker app
        cursor.execute("""
            SELECT app, name, applied
            FROM django_migrations
            WHERE app = 'factchecker'
            ORDER BY id;
        """)
        
        migrations = cursor.fetchall()
        
        if not migrations:
            print("No migrations found for the factchecker app.")
            return
        
        print(f"Found {len(migrations)} migration(s) for the factchecker app:")
        for app, name, applied in migrations:
            print(f" - {app}.{name} (applied: {applied})")

if __name__ == "__main__":
    print("Checking migration status...\n")
    check_migrations()