import sqlite3
import psycopg2
from sqlalchemy import create_engine, text
import pandas as pd
import time
import sys
import os

DB_PW = os.environ["DB_PW"]

def migrate_sqlite_to_postgres(sqlite_path, pg_connection_string, chunk_size=10000):
    """
    Migrate a SQLite database to PostgreSQL table by table.
    
    Args:
        sqlite_path: Path to the SQLite database file
        pg_connection_string: SQLAlchemy connection string for PostgreSQL
        chunk_size: Number of rows to process at once
    """
    print(f"Starting migration from {sqlite_path} to PostgreSQL")
    print(f"Using chunk size of {chunk_size} rows")
    
    # Connect to SQLite
    try:
        sqlite_conn = sqlite3.connect(sqlite_path)
        print("Connected to SQLite database")
    except Exception as e:
        print(f"Error connecting to SQLite database: {e}")
        return
    
    # Connect to PostgreSQL
    try:
        pg_engine = create_engine(pg_connection_string)
        with pg_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("Connected to PostgreSQL database")
    except Exception as e:
        print(f"Error connecting to PostgreSQL database: {e}")
        sqlite_conn.close()
        return
    
    # Get list of tables from SQLite
    try:
        tables = pd.read_sql_query("SELECT name FROM sqlite_master WHERE type='table';", sqlite_conn)
        print(f"Found {len(tables)} tables in SQLite database")
    except Exception as e:
        print(f"Error getting table list: {e}")
        sqlite_conn.close()
        return
    
    # Skip SQLite internal tables
    skip_tables = ['sqlite_sequence', 'sqlite_stat1', 'sqlite_stat2', 'sqlite_stat3', 'sqlite_stat4']
    tables_to_migrate = [table for table in tables['name'] if table not in skip_tables]
    
    total_tables = len(tables_to_migrate)
    tables_migrated = 0
    
    # Migrate each table
    for table_name in tables_to_migrate:
        start_time = time.time()
        print(f"\n[{tables_migrated+1}/{total_tables}] Migrating table: {table_name}")
        
        try:
            # Get row count (approximate for large tables)
            row_count = pd.read_sql_query(f"SELECT COUNT(*) as count FROM {table_name}", sqlite_conn).iloc[0]['count']
            print(f"Table has approximately {row_count} rows")
            
            # Process in chunks to avoid memory issues
            offset = 0
            rows_processed = 0
            
            while True:
                print(f"  Processing rows {offset} to {offset + chunk_size}...", end="")
                sys.stdout.flush()
                
                query = f"SELECT * FROM {table_name} LIMIT {chunk_size} OFFSET {offset}"
                chunk = pd.read_sql_query(query, sqlite_conn)
                
                if chunk.empty:
                    print(" No more rows.")
                    break
                
                # For first chunk, replace the table (if exists)
                if offset == 0:
                    chunk.to_sql(table_name, pg_engine, if_exists='replace', index=False)
                else:
                    # For subsequent chunks, append to the table
                    chunk.to_sql(table_name, pg_engine, if_exists='append', index=False)
                
                rows_in_chunk = len(chunk)
                rows_processed += rows_in_chunk
                offset += chunk_size
                
                print(f" Done. ({rows_processed}/{row_count} rows, {rows_processed/row_count*100:.1f}%)")
                
                # Break if we processed fewer rows than the chunk size
                if rows_in_chunk < chunk_size:
                    break
            
            elapsed_time = time.time() - start_time
            print(f"Completed migration of table {table_name} in {elapsed_time:.2f} seconds")
            tables_migrated += 1
            
        except Exception as e:
            print(f"Error migrating table {table_name}: {e}")
            print("Continuing with next table...")
    
    sqlite_conn.close()
    print(f"\nMigration completed! {tables_migrated}/{total_tables} tables migrated successfully.")

if __name__ == "__main__":
    # Replace these with your actual connection details
    SQLITE_DB_PATH = "/Users/cedricfitzgerald/Documents/Startup/crystal/db.sqlite3"
    PG_CONNECTION_STRING = f"postgresql://postgres:{DB_PW}@0.0.0.0:1234/crystal"
    
    # You can adjust the chunk size based on your available memory
    CHUNK_SIZE = 15000
    
    migrate_sqlite_to_postgres(SQLITE_DB_PATH, PG_CONNECTION_STRING, CHUNK_SIZE)