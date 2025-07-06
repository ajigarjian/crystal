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

def get_connection_pool(min_conn=2, max_conn=30):
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
                # Production environment - use private IP (same VPC, serverless VPC connector)
                db_name = os.environ.get('DB_NAME')
                db_user = os.environ.get('DB_USER')
                db_password = os.environ.get('DB_PASSWORD')
                private_ip = os.environ.get('DB_PRIVATE_IP', '172.28.48.3')  # Set your private IP here or via env
                _pool = psycopg2.pool.ThreadedConnectionPool(
                    min_conn, max_conn,
                    dbname=db_name,
                    user=db_user,
                    password=db_password,
                    host=private_ip,
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
            # Production environment - use private IP (same VPC, serverless VPC connector)
            db_name = os.environ.get('DB_NAME')
            db_user = os.environ.get('DB_USER')
            db_password = os.environ.get('DB_PASSWORD')
            private_ip = os.environ.get('DB_PRIVATE_IP', '10.0.0.3')  # Set your private IP here or via env
            db_url = f"postgresql://{db_user}:{db_password}@{private_ip}:5432/{db_name}"
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
    """Execute a query and return results with proper connection management"""
    pool = get_connection_pool()
    conn = pool.getconn()

    try:
        conn.autocommit = True  # Optional: Ensure commands are committed
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query, params)
            conn.commit()  # Explicitly commit the transaction
            if fetch_all:
                results = cursor.fetchall()
            else:
                results = cursor.fetchone()
            return results
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Query execution error: {e}")
        raise
    finally:
        if conn:
            pool.putconn(conn)

def get_usable_resources(dataset_id):
    """
    Get usable resources for a dataset from the database using Django ORM.

    Args:
        dataset_id: The ID of the dataset

    Returns:
        List of resource dictionaries
    """
    from factchecker.models import DatasetResource
    try:
        resources_qs = DatasetResource.objects.filter(dataset__dataset_id=dataset_id, url__isnull=False)
        formatted_resources = []
        for resource in resources_qs:
            formatted_resources.append({
                "id": resource.resource_id,
                "name": resource.name,
                "url": resource.url,
                "description": resource.description,
                "format": resource.format
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
    if os.getenv('FUNCTIONS_EMULATOR') or ip_address in ('127.0.0.1', '::1', 'localhost', '162.83.246.82'):
        return False, None
    
    # Define limits for each function
    LIMITS = {
        'stream_search_datasets': 50,  # test for 3
        'stream_analyze': 5,
        'evaluate_search_query': 200
    }
    
    # Get the limit for this function
    limit = LIMITS.get(function_name, 50)  # Default to 10 if function not in limits
    
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
                "If you need a higher limit, please join the beta waitlist on the home page, or email us at ari@askcrystal.info and we'll get back to you."
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

def get_dataset_info(dataset_id):
    """
    Retrieve dataset information from the DatasetCatalog model.

    Args:
        dataset_id: The ID of the dataset

    Returns:
        Dictionary of dataset fields, or None if not found.
    """
    from factchecker.models import DatasetCatalog
    try:
        dataset = DatasetCatalog.objects.get(pk=dataset_id)
        dataset_dict = {}
        for field in dataset._meta.fields:
            dataset_dict[field.name] = getattr(dataset, field.name)
        return dataset_dict
    except DatasetCatalog.DoesNotExist:
        return None
    except Exception as e:
        logger.error(f"Error retrieving dataset info for dataset {dataset_id}: {e}")
        return None