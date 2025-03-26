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
import psycopg2.pool

# Configure logging
logger = logging.getLogger(__name__)

# Global engine for SQLAlchemy
_engine = None
_Session = None

# Global connection pool
_pool = None

def get_connection_pool(min_conn=1, max_conn=5):
    """Create or get the connection pool"""
    global _pool
    
    if _pool is None:
        try:
            # Check if running in production or local environment
            if os.getenv('FUNCTIONS_EMULATOR'):
                # Local development pool
                _pool = psycopg2.pool.ThreadedConnectionPool(
                    min_conn, max_conn,
                    host=os.environ.get('DB_HOST', '0.0.0.0'),
                    database=os.environ.get('DB_NAME'),
                    user=os.environ.get('DB_USER'),
                    password=os.environ.get('DB_PASSWORD'),
                    port=os.environ.get('DB_PORT', 1234)
                )
            else:
                # Production environment - use Unix socket or public IP
                db_instance = os.environ.get('DB_INSTANCE', 'crystal-2f87e:us-east4:crystal-sql')
                db_name = os.environ.get('DB_NAME')
                db_user = os.environ.get('DB_USER')
                db_password = os.environ.get('DB_PASSWORD')
                
                # Try connecting via Unix socket first
                try:
                    socket_dir = os.environ.get('DB_SOCKET_DIR', '/cloudsql')
                    unix_socket = f'{socket_dir}/{db_instance}'
                    
                    _pool = psycopg2.pool.ThreadedConnectionPool(
                        min_conn, max_conn,
                        dbname=db_name,
                        user=db_user,
                        password=db_password,
                        host=unix_socket
                    )
                except Exception as socket_error:
                    logger.warning(f"Socket pool creation failed, trying public IP: {socket_error}")
                    # Fall back to public IP connection
                    _pool = psycopg2.pool.ThreadedConnectionPool(
                        min_conn, max_conn,
                        dbname=db_name,
                        user=db_user,
                        password=db_password,
                        host='34.48.13.135',
                        port=5432
                    )
            
            logger.info("Connection pool created successfully")
        except Exception as e:
            logger.error(f"Failed to create connection pool: {e}")
            raise
    
    return _pool

def get_db_connection():
    """Get a connection from the pool or create a new one if pool not available"""
    pool = get_connection_pool()
    try:
        return pool.getconn()
    except Exception as e:
        logger.error(f"Error getting connection from pool: {e}")
        # Fall back to creating a new connection if pool fails
        try:
            # Check if running in production or local environment
            if os.getenv('FUNCTIONS_EMULATOR'):
                # Local development - connect via local Cloud SQL Proxy
                conn = psycopg2.connect(
                    host=os.environ.get('DB_HOST', '0.0.0.0'),
                    database=os.environ.get('DB_NAME'),
                    user=os.environ.get('DB_USER'),
                    password=os.environ.get('DB_PASSWORD'),
                    port=os.environ.get('DB_PORT', 1234)
                )
            else:
                # Production environment - use Unix socket or public IP
                db_instance = os.environ.get('DB_INSTANCE', 'crystal-2f87e:us-east4:crystal-sql')
                db_name = os.environ.get('DB_NAME')
                db_user = os.environ.get('DB_USER')
                db_password = os.environ.get('DB_PASSWORD')
                
                # Try connecting via Unix socket first
                try:
                    # Unix socket path for Cloud SQL
                    socket_dir = os.environ.get('DB_SOCKET_DIR', '/cloudsql')
                    unix_socket = f'{socket_dir}/{db_instance}'
                    
                    conn = psycopg2.connect(
                        dbname=db_name,
                        user=db_user,
                        password=db_password,
                        host=unix_socket  # Use Unix socket in production
                    )
                except Exception as socket_error:
                    logger.warning(f"Socket connection failed, trying public IP: {socket_error}")
                    # Fall back to public IP connection
                    conn = psycopg2.connect(
                        dbname=db_name,
                        user=db_user,
                        password=db_password,
                        host='34.48.13.135',  # Public IP address
                        port=5432
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
            # Production environment - try Unix socket first, then public IP
            db_instance = os.environ.get('DB_INSTANCE', 'crystal-2f87e:us-east4:crystal-sql')
            db_name = os.environ.get('DB_NAME')
            db_user = os.environ.get('DB_USER')
            db_password = os.environ.get('DB_PASSWORD')
            
            try:
                # Unix socket path for Cloud SQL
                socket_dir = os.environ.get('DB_SOCKET_DIR', '/cloudsql')
                unix_socket = f'{socket_dir}/{db_instance}'
                
                db_url = f"postgresql://{db_user}:{db_password}@/{db_name}?host={unix_socket}"
                _engine = create_engine(db_url)
            except Exception as socket_error:
                logger.warning(f"Socket engine creation failed, trying public IP: {socket_error}")
                # Fall back to public IP connection
                db_url = f"postgresql://{db_user}:{db_password}@34.48.13.135:5432/{db_name}"
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
        SELECT resource_id, name, url, description, format
        FROM factchecker_datasetresource
        WHERE dataset_id = %s AND url IS NOT NULL
        """
        resources = execute_query(query, (dataset_id,))
        
        # Convert to the expected format
        formatted_resources = []
        for resource in resources:
            formatted_resources.append({
                "id": resource["resource_id"],
                "name": resource["name"],
                "url": resource["url"],
                "description": resource["description"],
                "format": resource["format"]
            })
        
        return formatted_resources
    except Exception as e:
        logger.error(f"Error getting resources for dataset {dataset_id}: {e}")
        return []

def get_usable_resources_batch(dataset_ids):
    """
    Get usable resources for multiple datasets in a single query.
    
    Args:
        dataset_ids: List of dataset IDs
        
    Returns:
        Dictionary mapping dataset_ids to lists of resource dictionaries
    """
    try:
        if not dataset_ids:
            return {}
            
        # Convert all dataset_ids to strings for consistent keys
        dataset_ids = [str(ds_id) for ds_id in dataset_ids]
            
        # Use a more efficient query with JOIN if you need to filter by other conditions
        query = """
        SELECT r.resource_id, r.dataset_id, r.name, r.url, r.description, r.format
        FROM factchecker_datasetresource r
        WHERE r.dataset_id = ANY(%s) AND r.url IS NOT NULL
        """
        
        # Use the pooled connection for better performance
        resources = execute_query(query, (dataset_ids,))
        
        # Pre-allocate the result dictionary with empty lists
        result = {ds_id: [] for ds_id in dataset_ids}
        
        # Group resources by dataset_id
        for resource in resources:
            ds_id = str(resource["dataset_id"])
            result[ds_id].append({
                "id": resource["resource_id"],
                "name": resource["name"],
                "url": resource["url"],
                "description": resource["description"],
                "format": resource["format"]
            })
        
        return result
    except Exception as e:
        logger.error(f"Error getting batch resources for datasets: {e}")
        return {} 