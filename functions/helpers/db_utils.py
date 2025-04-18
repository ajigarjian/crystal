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

def get_connection_pool(min_conn=1, max_conn=20):
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
    pool = get_connection_pool() # Get the pool
    try:
        conn = pool.getconn() # Get connection from pool
        conn.autocommit = True # Optional: Ensure commands are committed
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query, params)
            conn.commit() # Explicitly commit the transaction
            if fetch_all:
                results = cursor.fetchall()
            else:
                results = cursor.fetchone()
            # Ensure cursor is closed before returning connection to pool
            cursor.close() 
            return results
    except Exception as e:
        # Rollback in case of error
        if conn:
            conn.rollback() 
        logger.error(f"Query execution error: {e}")
        raise
    finally:
        if conn:
            pool.putconn(conn) # Return connection to pool correctly

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
        
def check_usage_limit(ip_address, function_name):
    """
    Check if the IP address has exceeded the usage limit for the given function.
    Uses Firestore for tracking instead of PostgreSQL.
    
    Args:
        ip_address (str): The IP address of the request
        function_name (str): The name of the function ('stream_search_datasets' or 'stream_analyze')
        
    Returns:
        tuple: (bool, str) - (exceeded_limit, error_message)
            - exceeded_limit: True if limit is exceeded, False otherwise
            - error_message: Error message if limit exceeded, None otherwise
    """
    import os
    from firebase_admin import firestore
    
    # Skip limit checking in local development environment
    if os.getenv('FUNCTIONS_EMULATOR') or ip_address in ('127.0.0.1', '::1', 'localhost', '73.141.182.144', '162.83.246.82'):
        return False, None
    
    # Define limits for each function
    LIMITS = {
        'stream_search_datasets': 50,  # test for 3
        'stream_analyze': 5,
        'evaluate_search_query': 200
    }
    
    # Get the limit for this function
    limit = LIMITS.get(function_name, 10)  # Default to 10 if function not in limits
    
    try:
        # Get Firestore client
        db = firestore.client()
        
        # Create a document reference for this IP and function
        usage_ref = db.collection('usage_limits').document(f"{ip_address}_{function_name}")
        
        # Get the current document
        doc = usage_ref.get()
        
        if not doc.exists:
            # Document doesn't exist, create it
            usage_ref.set({
                'ip_address': ip_address,
                'function_name': function_name,
                'request_count': 1,
                'first_request_at': firestore.SERVER_TIMESTAMP,
                'last_request_at': firestore.SERVER_TIMESTAMP
            })
            return False, None
        
        # Document exists, get current count
        data = doc.to_dict()
        current_count = data.get('request_count', 0)
        
        # Check if limit is exceeded
        if current_count >= limit:
            error_message = (
                "Thank you for using Crystal! To ensure everyone gets a fair chance to use our Alpha "
                "version, we've set a limit of {} requests per user for this feature. "
                "If you need a higher limit, please join the beta waitlist on the home page, or email us at ajigarjian@gmail.com and we'll get back to you."
            ).format(limit)
            
            # Update the timestamp even when exceeding limit
            usage_ref.update({
                'last_request_at': firestore.SERVER_TIMESTAMP
            })
            
            return True, error_message
        
        # Increment the counter and update timestamp
        usage_ref.update({
            'request_count': current_count + 1,
            'last_request_at': firestore.SERVER_TIMESTAMP
        })
        
        return False, None
    
    except Exception as e:
        # If there's an error, log it but don't block the request
        logger.error(f"Error checking usage limit: {e}")
        return False, None