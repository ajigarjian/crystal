"""
Utility script to check database tables and their structure.
Run this script to diagnose database schema issues.
"""

from sqlalchemy import inspect, create_engine, text
import logging
import sys
import os
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

def get_direct_db_connection():
    """Create a direct connection to the database using environment variables"""
    try:
        # Get database credentials from environment variables
        db_user = os.environ.get('DB_USER')
        db_password = os.environ.get('DB_PASSWORD')  # Note: using DB_PASSWORD not DB_PASS
        db_name = os.environ.get('DB_NAME')
        db_host = os.environ.get('DB_HOST', 'localhost')
        db_port = os.environ.get('DB_PORT', '5432')
        
        if not all([db_user, db_password, db_name]):
            logger.error("Database credentials not found in environment variables")
            logger.info(f"Available env vars: DB_USER={db_user}, DB_PASSWORD={'*****' if db_password else None}, DB_NAME={db_name}, DB_HOST={db_host}, DB_PORT={db_port}")
            return None
        
        # Create connection string
        conn_string = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
        logger.info(f"Connecting to database at {db_host}:{db_port}/{db_name}")
        
        # Create and return engine
        return create_engine(conn_string)
    
    except Exception as e:
        logger.error(f"Error creating database connection: {str(e)}")
        logger.error(f"Traceback: {__import__('traceback').format_exc()}")
        return None

def check_db_tables():
    """Function to check database tables and their structure"""
    try:
        # Get direct database connection
        engine = get_direct_db_connection()
        
        if engine is None:
            logger.error("Could not establish database connection")
            return []
        
        # Test connection
        try:
            with engine.connect() as conn:
                result = conn.execute(text("SELECT 1")).fetchone()
                logger.info(f"Connection test successful: {result}")
        except Exception as e:
            logger.error(f"Connection test failed: {str(e)}")
            return []
        
        inspector = inspect(engine)
        
        # Get all table names
        tables = inspector.get_table_names()
        logger.info(f"Available tables: {tables}")
        
        # Check specific tables related to Census data
        census_tables = [t for t in tables if 'census' in t.lower()]
        logger.info(f"Census-related tables: {census_tables}")
        
        # Check columns for each Census table
        for table in census_tables:
            columns = inspector.get_columns(table)
            logger.info(f"\nTable: {table}")
            for column in columns:
                logger.info(f"  - {column['name']}: {column['type']}")
        
        # Check for binary columns in all tables
        logger.info("\nChecking for binary columns in all tables:")
        for table in tables:
            columns = inspector.get_columns(table)
            binary_columns = [col for col in columns if 'BINARY' in str(col['type']).upper() or 'BLOB' in str(col['type']).upper()]
            if binary_columns:
                logger.info(f"Table {table} has binary columns:")
                for col in binary_columns:
                    logger.info(f"  - {col['name']}: {col['type']}")
        
        # Check primary keys and foreign keys
        logger.info("\nChecking primary keys and foreign keys:")
        for table in tables:
            pks = inspector.get_pk_constraint(table)
            fks = inspector.get_foreign_keys(table)
            logger.info(f"Table: {table}")
            logger.info(f"  - Primary keys: {pks['constrained_columns']}")
            for fk in fks:
                logger.info(f"  - Foreign key: {fk['constrained_columns']} -> {fk['referred_table']}.{fk['referred_columns']}")
        
        return tables
    
    except Exception as e:
        logger.error(f"Error checking database tables: {str(e)}")
        logger.error(f"Traceback: {__import__('traceback').format_exc()}")
        return []

def check_specific_table(table_name):
    """Check the structure of a specific table"""
    try:
        engine = get_direct_db_connection()
        
        if engine is None:
            logger.error("Could not establish database connection")
            return
        
        inspector = inspect(engine)
        
        if table_name not in inspector.get_table_names():
            logger.error(f"Table {table_name} does not exist in the database")
            return
        
        columns = inspector.get_columns(table_name)
        logger.info(f"Columns in {table_name}:")
        for column in columns:
            logger.info(f"  - {column['name']}: {column['type']} (nullable: {column['nullable']})")
        
        # Check indexes
        indexes = inspector.get_indexes(table_name)
        logger.info(f"Indexes on {table_name}:")
        for index in indexes:
            logger.info(f"  - {index['name']}: {index['column_names']} (unique: {index['unique']})")
        
        # Check sample data
        from sqlalchemy.orm import Session
        with Session(engine) as session:
            logger.info(f"Sample data from {table_name}:")
            result = session.execute(text(f"SELECT * FROM {table_name} LIMIT 5")).fetchall()
            for row in result:
                logger.info(f"  - {row}")
            
    except Exception as e:
        logger.error(f"Error checking table {table_name}: {str(e)}")
        logger.error(f"Traceback: {__import__('traceback').format_exc()}")

def check_census_embeddings():
    """
    Diagnose the 'embedding' column of 'factchecker_censusdataset' to see if
    it's storing valid data or if there's an issue with lengths, non-hex, etc.
    """
    logger.info("Checking 'factchecker_censusdataset.embedding' for validity...")
    engine = get_direct_db_connection()
    
    if engine is None:
        logger.error("Could not establish database connection")
        return
    
    try:
        with engine.connect() as conn:
            # Query all embedding rows
            query = text("""
                SELECT id, embedding
                FROM factchecker_censusdataset
                WHERE embedding IS NOT NULL
            """)
            rows = conn.execute(query).fetchall()
            
            for row in rows:
                dataset_id = row.id
                embed_str = row.embedding
                
                # We expect this to be a TEXT column with optional "\x" prefix if using Postgres bytea format
                if not isinstance(embed_str, str):
                    logger.warning(f"Dataset {dataset_id} embedding is not a string: {type(embed_str)}")
                    continue
                
                if embed_str.startswith('\\x'):
                    # Attempt to interpret as hex 
                    hex_str = embed_str[2:]
                    try:
                        binary_data = bytes.fromhex(hex_str)
                        # Log the length to see if it's multiple of 4
                        if len(binary_data) % 4 != 0:
                            logger.warning(
                                f"Dataset {dataset_id} embedding is hex but length {len(binary_data)} "
                                f"is NOT multiple of 4 -> might not be float32"
                            )
                        else:
                            logger.info(
                                f"Dataset {dataset_id} embedding is hex with length {len(binary_data)} (multiple of 4)"
                            )
                    except Exception as e:
                        logger.error(
                            f"Dataset {dataset_id} embedding: failed to decode hex: {str(e)}. "
                            f"Raw preview: {embed_str[:64]}"
                        )
                else:
                    # Maybe it's JSON or something else
                    logger.info(
                        f"Dataset {dataset_id} embedding does not start with '\\x': Probably JSON or raw string. "
                        f"Length: {len(embed_str)}"
                    )
    except Exception as e:
        logger.error(f"Error checking embeddings: {str(e)}")
        logger.error(f"Traceback: {__import__('traceback').format_exc()}")

if __name__ == "__main__":
    logger.info("Starting database table check...")
    tables = check_db_tables()
    
    # Optionally check the 'factchecker_censusdataset.embedding' column
    check_census_embeddings()
    
    # If command line arguments are provided, check specific tables
    if len(sys.argv) > 1:
        for table_name in sys.argv[1:]:
            check_specific_table(table_name)
    
    logger.info("Database table check complete.")