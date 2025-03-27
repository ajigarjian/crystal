import os 
from dotenv import load_dotenv

load_dotenv()  # This should be called before importing settings

DB_PASSWORD = os.environ["DB_PASSWORD"]


# settings.py
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'crystal',
        'USER': 'postgres',
        'PASSWORD': DB_PASSWORD,
        'HOST': 'localhost',  # or your Cloud SQL IP
        'PORT': '1234',
    }
}

INSTALLED_APPS = [
    'factchecker'     # Add the factchecker app
]

# Minimal settings required by Django
SECRET_KEY = 'dummy-key-for-orm-only'
TIME_ZONE = 'UTC'
USE_TZ = True