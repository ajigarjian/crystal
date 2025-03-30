import os 
from dotenv import load_dotenv

load_dotenv()  # This should be called before importing settings

# Check if running in emulator
IS_EMULATOR = os.getenv('FUNCTIONS_EMULATOR') == 'true'

# Database settings
DB_NAME = os.environ.get('DB_NAME', 'crystal')
DB_USER = os.environ.get('DB_USER', 'postgres')
DB_PASSWORD = os.environ.get('DB_PASSWORD')
DB_PORT = os.environ.get('DB_PORT', '1234')
DB_INSTANCE = os.environ.get('DB_INSTANCE', 'crystal-2f87e:us-east4:crystal-sql')

# settings.py
if IS_EMULATOR:
    # Local development database through Cloud SQL Proxy
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': DB_NAME,
            'USER': DB_USER,
            'PASSWORD': DB_PASSWORD,
            'HOST': os.environ.get('DB_HOST', 'localhost'),
            'PORT': DB_PORT,
        }
    }
else:
    # Production database using Unix socket for Cloud SQL
    socket_dir = os.environ.get('DB_SOCKET_DIR', '/cloudsql')
    unix_socket = f'{socket_dir}/{DB_INSTANCE}'
    
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql_psycopg2',
            'NAME': DB_NAME,
            'USER': DB_USER,
            'PASSWORD': DB_PASSWORD,
            'HOST': unix_socket,  # Unix socket path for Cloud SQL
            'PORT': '',  # Leave empty for Unix socket connections
        }
    }

    # Fallback configuration if unix socket fails
    DB_FALLBACK = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': DB_NAME,
            'USER': DB_USER,
            'PASSWORD': DB_PASSWORD,
            'HOST': '34.48.13.135',  # Public IP as fallback
            'PORT': '5432',
        }
    }

INSTALLED_APPS = [
    'factchecker'     # Add the factchecker app
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.middleware.common.CommonMiddleware',
]

# Database connection options for improved reliability
DATABASE_OPTIONS = {
    'connect_timeout': 30,  # 30 seconds
    'options': '-c statement_timeout=60000',  # 60 seconds statement timeout
}

# Add connection options to both database configs
if not IS_EMULATOR:
    DATABASES['default']['OPTIONS'] = DATABASE_OPTIONS
    if 'DB_FALLBACK' in locals():
        DB_FALLBACK['default']['OPTIONS'] = DATABASE_OPTIONS

# Configure database connection pooling for better performance
CONN_MAX_AGE = 60  # Keep connections alive for 60 seconds

# Minimal settings required by Django
SECRET_KEY = 'dummy-key-for-orm-only'
TIME_ZONE = 'UTC'
USE_TZ = True

# Logging configuration to help debug database issues
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'django.db.backends': {
            'handlers': ['console'],
            'level': 'INFO',  # Change to DEBUG to see all SQL queries
        },
    },
}