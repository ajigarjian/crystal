"""
Database utility functions for Firebase Cloud Functions.
Provides connection and query execution for PostgreSQL database.
"""

import os
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session

# Configure logging
logger = logging.getLogger(__name__)

# Global engine for SQLAlchemy
_engine = None
_Session = None

def get_db_connection():
    """Create and return a connection to the PostgreSQL database"""
    try:
        # Check if running in production or local environment
        if os.getenv('FUNCTIONS_EMULATOR'):
            # Local development - connect via local Cloud SQL Proxy
            conn = psycopg2.connect(
                host=os.environ.get('DB_HOST', 'localhost'),
                database=os.environ.get('DB_NAME'),
                user=os.environ.get('DB_USER'),
                password=os.environ.get('DB_PASSWORD'),
                port=os.environ.get('DB_PORT', 1234)
            )
        else:
            # Production environment - use Unix socket
            db_instance = os.environ.get('DB_INSTANCE')
            db_name = os.environ.get('DB_NAME')
            db_user = os.environ.get('DB_USER')
            db_password = os.environ.get('DB_PASSWORD')
            
            # Unix socket path for Cloud SQL
            socket_dir = os.environ.get('DB_SOCKET_DIR', '/cloudsql')
            unix_socket = f'{socket_dir}/{db_instance}'
            
            conn = psycopg2.connect(
                dbname=db_name,
                user=db_user,
                password=db_password,
                host=unix_socket  # Use Unix socket in production
            )
        
        return conn
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        raise

def get_sqlalchemy_engine():
    """Get or create a SQLAlchemy engine"""
    global _engine
    
    if _engine is None:
        # Create SQLAlchemy engine based on environment
        if os.getenv('FUNCTIONS_EMULATOR'):
            # Local development
            db_host = os.environ.get('DB_HOST', 'localhost')
            db_name = os.environ.get('DB_NAME')
            db_user = os.environ.get('DB_USER')
            db_password = os.environ.get('DB_PASSWORD')
            db_port = os.environ.get('DB_PORT', 1234)
            
            db_url = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
            _engine = create_engine(db_url)
        else:
            # Production environment - use Unix socket
            db_instance = os.environ.get('DB_INSTANCE')
            db_name = os.environ.get('DB_NAME')
            db_user = os.environ.get('DB_USER')
            db_password = os.environ.get('DB_PASSWORD')
            
            # Unix socket path for Cloud SQL
            socket_dir = os.environ.get('DB_SOCKET_DIR', '/cloudsql')
            unix_socket = f'{socket_dir}/{db_instance}'
            
            db_url = f"postgresql://{db_user}:{db_password}@/{db_name}?host={unix_socket}"
            _engine = create_engine(db_url)
    
    return _engine

def get_db_session():
    """Get a SQLAlchemy session"""
    global _Session
    
    if _Session is None:
        engine = get_sqlalchemy_engine()
        _Session = scoped_session(sessionmaker(bind=engine))
    
    return _Session()

def execute_query(query, params=None, fetch_all=True):
    """Execute a query and return results"""
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query, params)
            if fetch_all:
                return cursor.fetchall()
            else:
                return cursor.fetchone()
    except Exception as e:
        logger.error(f"Query execution error: {e}")
        raise
    finally:
        if conn:
            conn.close()

def get_usable_resources(dataset_id):
    """
    Get usable resources for a dataset from the database.
    
    Args:
        dataset_id: The ID of the dataset
        
    Returns:
        List of resource dictionaries
    """
    try:
        # Query the database for resources
        query = """
        SELECT id, name, url, description, format
        FROM factchecker_datasetresource
        WHERE dataset_id = %s AND url IS NOT NULL
        """
        resources = execute_query(query, (dataset_id,))
        
        # Convert to the expected format
        formatted_resources = []
        for resource in resources:
            formatted_resources.append({
                "id": resource["id"],
                "name": resource["name"],
                "url": resource["url"],
                "description": resource["description"],
                "format": resource["format"]
            })
        
        return formatted_resources
    except Exception as e:
        logger.error(f"Error getting resources for dataset {dataset_id}: {e}")
        return [] 