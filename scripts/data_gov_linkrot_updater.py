#!/usr/bin/env python3
"""
data_gov_linkrot_updater.py

A script to check Data.gov resources against the Harvard-LIL S3 archive and 
update our database with availability information, tracking link rot and 
caching resources when needed.

Usage:
    python data_gov_linkrot_updater.py [--limit=N] [--process-new-only] [--cleanup]

Options:
    --limit=N            Limit processing to N datasets (for testing)
    --process-new-only   Only process datasets not previously checked
    --cleanup            Remove temporary files after processing
"""

import os
import sys
import logging
import shutil
import gc

# Setup path for imports
this_dir = os.path.dirname(__file__)
parent_dir = os.path.join(this_dir, "..")
sys.path.append(parent_dir)            # parent of scripts/

# Also add the functions directory to the path so 'factchecker' can be found directly
# This is needed because Django settings.py has 'factchecker' in INSTALLED_APPS
functions_dir = os.path.join(parent_dir, 'functions')
sys.path.append(functions_dir)

# Make factchecker module directly available
factchecker_dir = os.path.join(functions_dir, 'factchecker')
sys.path.append(factchecker_dir)

import json
import time

import zipfile
import hashlib
import tempfile
import argparse
import datetime
import subprocess
import requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import django

os.environ["FUNCTIONS_EMULATOR"] = "True"

# Point DJANGO_SETTINGS_MODULE to the correct module path where settings.py lives.
# If your settings are at "functions/factchecker/settings.py", do:
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'functions.factchecker.settings')

# We'll need to avoid importing the WaitlistEntry model
# Let's instead patch the Django ModelBase.__new__ method to handle models without app_label

# Initialize Django
django.setup()

# Import Django modules
from django.db import transaction
from django.utils import timezone
from django.db import models
from django.db.models import BinaryField

# Now patch Django's ModelBase.__new__ to add app_label to models without it
from django.db.models.base import ModelBase
original_new = ModelBase.__new__

def patched_modelbase_new(cls, name, bases, attrs, **kwargs):
    # Add app_label to Meta if it doesn't exist
    if 'Meta' not in attrs or not hasattr(attrs['Meta'], 'app_label'):
        meta_attrs = {'app_label': 'factchecker'}
        meta_bases = (attrs['Meta'],) if 'Meta' in attrs else ()
        attrs['Meta'] = type('Meta', meta_bases, meta_attrs)
    
    # Call the original method
    return original_new(cls, name, bases, attrs, **kwargs)

# Apply the patch
ModelBase.__new__ = patched_modelbase_new

# Import directly from the module
from functions.factchecker.models import (
    DatasetCatalog, 
    DatasetResource,
    DataGovArchiveCheck,
    ResourceAvailabilityCheck
)

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,  # Change to DEBUG level to see detailed messages
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("linkrot_updater.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("linkrot_updater")
logger.setLevel(logging.DEBUG)  # Ensure logger level is DEBUG

# Add a more detailed debug logger
debug_logger = logging.getLogger("linkrot_debug")
debug_handler = logging.FileHandler("linkrot_debug.log")
debug_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
debug_logger.addHandler(debug_handler)
debug_logger.setLevel(logging.DEBUG)

# Constants
S3_ENDPOINT = "https://data.source.coop"
S3_BUCKET = "harvard-lil"
S3_COLLECTIONS_PREFIX = "collections/data_gov"
S3_METADATA_PREFIX = "metadata/data_gov"
TEMP_DIR = Path(tempfile.gettempdir()) / "data_gov_archive"
HTTP_TIMEOUT = 5  # seconds - set to exactly 5 seconds
MAX_WORKERS = 10
USER_AGENT = "DataGovLinkRotUpdater/1.0"
# Maximum temp storage in MB before forcing cleanup
MAX_TEMP_STORAGE_MB = 1000  # 1GB
# Maximum age for temp files in seconds before cleanup
MAX_TEMP_FILE_AGE = 1800  # 30 minutes


class DataGovArchiveProcessor:
    """Process the Harvard-LIL Data.gov archive to track link rot and update our database"""
    
    def __init__(self, limit=None, process_new_only=False, cleanup=True, single_path=None, start_index=0):
        self.limit = limit
        self.process_new_only = process_new_only
        self.cleanup = cleanup
        self.single_path = single_path
        self.start_index = start_index
        self.stats = {
            "datasets_processed": 0,
            "resources_checked": 0,
            "resources_available": 0,
            "resources_unavailable": 0,
            "resources_cached": 0,
            "errors": 0,
            "datasets_missing": 0,
            "resources_gone_bad": 0
        }
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        
        # Ensure temp directory exists
        os.makedirs(TEMP_DIR, exist_ok=True)
    
    def list_s3_metadata(self):
        """Get list of metadata files in the S3 bucket"""
        logger.info("Listing metadata files from S3 bucket...")
        
        cmd = [
            "aws", "s3", "ls", 
            f"s3://{S3_BUCKET}/gov-data/{S3_METADATA_PREFIX}/", 
            "--recursive", 
            "--human-readable",
            "--endpoint-url", S3_ENDPOINT
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            lines = result.stdout.splitlines()
            
            # Parse the output - typical line:
            # 2023-09-15 12:34:56  789.1 KB metadata/data_gov/dataset-name/v1.json
            metadata_files = []
            for line in lines:
                if not line.strip() or "PRE" in line:
                    continue
                    
                parts = line.split()
                if len(parts) >= 4 and parts[-1].endswith(".json"):
                    # Extract just the path relative to metadata/data_gov/
                    path = parts[-1]
                    
                    # Remove any prefixes to get to the actual dataset path
                    prefixes = [
                        f"{S3_BUCKET}/gov-data/{S3_METADATA_PREFIX}/",
                        f"gov-data/{S3_METADATA_PREFIX}/",
                        f"{S3_METADATA_PREFIX}/"
                    ]
                    
                    for prefix in prefixes:
                        if path.startswith(prefix):
                            path = path[len(prefix):]
                            break
                    
                    metadata_files.append(path)
            
            logger.info(f"Found {len(metadata_files)} metadata files")
            return metadata_files
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Error listing S3 bucket: {e}")
            logger.error(f"STDOUT: {e.stdout}")
            logger.error(f"STDERR: {e.stderr}")
            raise
    
    def download_metadata_file(self, metadata_path):
        """Download a metadata file from S3"""
        # Always use a flattened directory structure to avoid path length issues
        path_hash = hashlib.md5(str(metadata_path).encode()).hexdigest()[:10]
        flat_dir = TEMP_DIR / "metadata_flat"
        filename = os.path.basename(metadata_path)
        local_path = flat_dir / f"{path_hash}_{filename}"
        
        # Create the flat directory
        try:
            os.makedirs(flat_dir, exist_ok=True)
        except OSError as e:
            logger.error(f"Error creating flat directory for metadata: {e}")
            self.stats["errors"] += 1
            return None
            
        # Check if we already have this file
        if local_path.exists() and os.path.getsize(local_path) > 0:
            return local_path
            
        try:
            # Build the direct URL to the file
            s3_url = f"{S3_ENDPOINT}/{S3_BUCKET}/gov-data/{S3_METADATA_PREFIX}/{metadata_path}"
            logger.debug(f"Downloading metadata from URL: {s3_url}")
            
            # Download the file directly via HTTP
            response = self.session.get(s3_url, timeout=HTTP_TIMEOUT * 2, stream=True)
            response.raise_for_status()
            
            # Write the file
            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    
            if os.path.getsize(local_path) == 0:
                logger.error(f"Downloaded file is empty: {local_path}")
                os.remove(local_path)
                self.stats["errors"] += 1
                return None
                
            return local_path
            
        except (requests.RequestException, OSError) as e:
            logger.error(f"Error downloading {metadata_path}: {e}")
            self.stats["errors"] += 1
            
            # Clean up incomplete download if it exists
            if os.path.exists(local_path):
                try:
                    os.remove(local_path)
                except OSError:
                    pass
                    
            return None
    
    def download_collection_file(self, collection_path):
        """Download a collection (zip) file from S3"""
        # Always use a flattened directory structure
        path_hash = hashlib.md5(str(collection_path).encode()).hexdigest()[:10]
        flat_dir = TEMP_DIR / "collections_flat"
        filename = os.path.basename(collection_path)
        local_path = flat_dir / f"{path_hash}_{filename}"
        
        # Create the flat directory
        try:
            os.makedirs(flat_dir, exist_ok=True)
        except OSError as e:
            logger.error(f"Error creating flat directory for collections: {e}")
            return None
        
        # Check if we already have this file
        if local_path.exists() and os.path.getsize(local_path) > 0:
            logger.debug(f"Collection file already exists locally at {local_path}")
            return local_path
            
        try:
            # Build the direct URL to the file
            s3_url = f"{S3_ENDPOINT}/{S3_BUCKET}/gov-data/{collection_path}"
            logger.debug(f"Downloading collection file from {s3_url}")
            
            # Download the file
            response = self.session.get(s3_url, timeout=HTTP_TIMEOUT * 3, stream=True)
            
            if response.status_code != 200:
                logger.error(f"Failed to download collection file: HTTP {response.status_code}")
                return None
                
            response.raise_for_status()
            
            # Save the file as a stream to handle large files better
            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            file_size = os.path.getsize(local_path)
            logger.debug(f"Successfully downloaded collection file: {file_size} bytes")
            
            if file_size == 0:
                logger.error("Downloaded file is empty")
                os.remove(local_path)
                return None
                
            return local_path
            
        except requests.RequestException as e:
            logger.error(f"Error downloading {s3_url}: {e}")
            self.stats["errors"] += 1
            
            # Clean up incomplete download if it exists
            if os.path.exists(local_path):
                try:
                    os.remove(local_path)
                except OSError:
                    pass
                    
            return None
    
    def extract_dataset_info(self, metadata_path):
        """Extract dataset and resource information from a metadata file"""
        try:
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)
                
            # Basic structure validation
            if "signed_metadata" not in metadata or "data_gov_metadata" not in metadata["signed_metadata"]:
                logger.warning(f"Invalid metadata structure in {metadata_path}")
                return None
                
            dataset_metadata = metadata["signed_metadata"]["data_gov_metadata"]
            dataset_name = dataset_metadata.get("name")
            
            if not dataset_name:
                logger.warning(f"Missing dataset name in {metadata_path}")
                return None
                
            # Get the version from the path (e.g., "v1")
            path_parts = str(metadata_path).split('/')
            if len(path_parts) >= 2:
                # Try to extract the version from filename (e.g., "v1.json")
                filename = path_parts[-1]
                if '_' in filename:
                    # If we're using flattened paths, extract from original path
                    # Format is hash_filename, e.g. "abc123_v1.json"
                    filename = filename.split('_', 1)[1]
                version = filename.split('.')[0]  # Extract "v1" from "v1.json"
            else:
                version = "unknown"
                
            # Extract actual dataset path from metadata_path
            # If metadata_path is a local file path with our flat structure, extract from filename
            if isinstance(metadata_path, Path) or str(metadata_path).startswith('/'):
                local_path = str(metadata_path)
                # Check if this is our flattened path with hash prefix
                if "metadata_flat" in local_path and '_' in os.path.basename(local_path):
                    # Example: /tmp/data_gov_archive/metadata_flat/1234abcd_v1.json
                    # We need to reconstruct the dataset_path as "dataset_name/v1"
                    dataset_path = f"{dataset_name}/{version}"
                else:
                    # Regular path - extract dataset name and version
                    dataset_path = f"{dataset_name}/{version}"
                logger.debug(f"Dataset path derived from metadata: {dataset_path}")
            else:
                # If it's already the S3 path, we can use it more directly
                dataset_path = str(metadata_path).split(S3_METADATA_PREFIX + '/')[-1].replace('.json', '')
                logger.debug(f"Dataset path from S3 path: {dataset_path}")
                
            # Corresponding collection file path (not full local path, just S3 relative path)
            collection_path = f"{S3_COLLECTIONS_PREFIX}/{dataset_path}.zip"
            logger.debug(f"Collection path: {collection_path}")
            
            # Create a Harvard archive path that correctly identifies the source with HTTPS URL
            harvard_archive_path = f"{S3_ENDPOINT}/{S3_BUCKET}/gov-data/{S3_COLLECTIONS_PREFIX}/{dataset_name}/{version}.zip"
            
            return {
                "dataset_name": dataset_name,
                "version": version,
                "metadata_path": str(metadata_path),
                "collection_path": str(collection_path),
                "harvard_archive_path": harvard_archive_path,
                "metadata": metadata
            }
            
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            logger.error(f"Error processing metadata file {metadata_path}: {e}")
            self.stats["errors"] += 1
            return None
    
    def check_resource_availability(self, resource_url, dataset_name):
        """Check if a resource is available at its original URL"""
        try:
            start_time = time.time()
            response = self.session.head(resource_url, timeout=HTTP_TIMEOUT, allow_redirects=True)
            response_time = int((time.time() - start_time) * 1000)  # ms
            
            # Consider it available if not explicitly a 404/403/410 status code
            is_available = response.status_code not in [404, 403, 410]
            
            # Try GET if HEAD doesn't work (some servers don't support HEAD)
            if not is_available or response.status_code == 405:
                start_time = time.time()
                response = self.session.get(resource_url, timeout=HTTP_TIMEOUT, stream=True, allow_redirects=True)
                response.close()  # Don't download the whole file
                response_time = int((time.time() - start_time) * 1000)  # ms
                is_available = response.status_code not in [404, 403, 410]
            
            return {
                "is_available": is_available,
                "http_status": response.status_code,
                "response_time_ms": response_time,
                "error_message": None
            }
                
        except requests.RequestException as e:
            # Only consider timeout errors as "available" - the resource might be slow but still there
            # Other errors (like connection errors) still indicate unavailability
            if "timeout" in str(e).lower():
                return {
                    "is_available": True,  # Consider timeout as "OK" since it responded
                    "http_status": None,
                    "response_time_ms": HTTP_TIMEOUT * 1000,  # Just use the timeout value
                    "error_message": str(e)
                }
            else:
                return {
                    "is_available": False,
                    "http_status": None,
                    "response_time_ms": None,
                    "error_message": str(e)
                }
    
    def extract_resource_from_archive(self, zip_path, resource_info):
        """Extract a resource file from the BagIt archive"""
        try:
            logger.debug(f"Attempting to extract resource {resource_info.get('id')} from archive {zip_path}")
            
            # Check disk usage and clean up if needed
            self.check_and_cleanup_disk_space()
            
            with zipfile.ZipFile(zip_path, 'r') as zf:
                # Log file contents for debugging
                file_list = zf.namelist()
                logger.debug(f"Archive contains {len(file_list)} files. First 5: {file_list[:5]}")
                
                # Resource files are typically in data/files/ directory
                file_path = None
                # Get filename from URL, handling query parameters
                url = resource_info["url"]
                from urllib.parse import urlparse
                parsed_url = urlparse(url)
                
                # Get the last part of the path
                resource_url_path = parsed_url.path.strip('/').split('/')[-1]
                
                # If path is empty, use the hostname (sometimes the path is just /)
                if not resource_url_path:
                    resource_url_path = parsed_url.netloc.split('.')[-2]  # Use domain name without TLD
                
                logger.debug(f"URL: {url}, extracted path: {resource_url_path}")
                
                # Check if we're looking for an ASPX file - might be saved as HTML
                is_aspx = resource_url_path.endswith('.aspx')
                html_variant = resource_url_path.replace('.aspx', '.html') if is_aspx else None
                
                logger.debug(f"URL path: {resource_url_path}, HTML variant: {html_variant}")
                
                # Search for files that might match this resource
                for info in zf.infolist():
                    # Check if file path contains the resource URL path
                    if info.filename.startswith('data/files/') and (
                       resource_url_path in info.filename or 
                       (html_variant and html_variant in info.filename) or
                       # Also check for filename without extension
                       resource_url_path.split('.')[0] in info.filename
                    ):
                        file_path = info.filename
                        logger.debug(f"Found matching file: {file_path}")
                        break
                
                if not file_path:
                    logger.debug(f"No matching file found for resource {resource_info.get('id')}")
                    return None
                    
                # Extract the file to a temporary location
                # Use resource ID to create a unique, flat directory structure
                extract_dir = TEMP_DIR / "extracted"
                resource_id = resource_info["id"]
                # Create a flattened path to avoid deep directory structures
                extract_path = extract_dir / resource_id
                os.makedirs(extract_dir, exist_ok=True)
                
                # Extract to a temporary file with resource ID and simple filename
                simple_filename = os.path.basename(file_path)
                temp_extract_path = extract_dir / f"{resource_id}_{simple_filename}"
                
                # Extract the file data directly
                with zf.open(file_path) as source_file:
                    with open(temp_extract_path, 'wb') as target_file:
                        target_file.write(source_file.read())
                
                # Calculate SHA-256 hash of the content
                sha256 = hashlib.sha256()
                with open(temp_extract_path, 'rb') as f:
                    for chunk in iter(lambda: f.read(4096), b''):
                        sha256.update(chunk)
                
                return {
                    "path": str(temp_extract_path),
                    "size": os.path.getsize(temp_extract_path),
                    "hash": sha256.hexdigest()
                }
                
        except (zipfile.BadZipFile, KeyError, FileNotFoundError, OSError) as e:
            logger.error(f"Error extracting resource from archive: {e}")
            # Try to clean up disk space on extraction errors
            self.check_and_cleanup_disk_space(force=True)
            return None
    
    @transaction.atomic
    def update_dataset_record(self, dataset_info):
        """Update or create a dataset record in our database"""
        metadata = dataset_info["metadata"]["signed_metadata"]["data_gov_metadata"]
        debug_logger.debug(f"Processing dataset: {metadata.get('name', 'unknown')}")
        debug_logger.debug(f"Metadata structure: {list(metadata.keys())}")
        
        try:
            # Debug log the metadata
            debug_logger.debug(f"Dataset ID: {metadata.get('id')}")
            debug_logger.debug(f"Title type: {type(metadata.get('title'))}, value: {metadata.get('title')}")
            debug_logger.debug(f"Notes type: {type(metadata.get('notes'))}, value: {repr(metadata.get('notes'))[:100]}")
            
            if 'organization' in metadata:
                debug_logger.debug(f"Organization keys: {list(metadata['organization'].keys())}")

            # Process extras field first to look for issues
            if "extras" in metadata:
                debug_logger.debug(f"Extras count: {len(metadata['extras'])}")
                for i, item in enumerate(metadata['extras']):
                    debug_logger.debug(f"Extra {i} - key: {repr(item.get('key'))} ({type(item.get('key'))}), "
                                      f"value: {repr(item.get('value'))} ({type(item.get('value'))})")

            # Process tags field
            if "tags" in metadata:
                debug_logger.debug(f"Tags count: {len(metadata['tags'])}")
                for i, tag in enumerate(metadata['tags'][:5]):  # Log first 5 tags
                    debug_logger.debug(f"Tag {i} - name: {repr(tag.get('name'))} ({type(tag.get('name'))})")

            # Prepare default values with proper validation
            title = metadata.get("title", "")
            if title and not isinstance(title, str):
                title = str(title)
                
            notes = metadata.get("notes")
            if notes and not isinstance(notes, str):
                notes = str(notes)
                
            org_name = metadata.get("organization", {}).get("name")
            if org_name and not isinstance(org_name, str):
                org_name = str(org_name)
                
            org_title = metadata.get("organization", {}).get("title")
            if org_title and not isinstance(org_title, str):
                org_title = str(org_title)
                
            org_desc = metadata.get("organization", {}).get("description")
            if org_desc and not isinstance(org_desc, str):
                org_desc = str(org_desc)

            debug_logger.debug("Creating or getting dataset with validated fields")
            dataset_defaults = {
                "title": title,
                "notes": notes,
                "organization_name": org_name,
                "organization_title": org_title, 
                "organization_description": org_desc,
                "license_id": metadata.get("license_id"),
                "license_title": metadata.get("license_title"),
                "license_url": metadata.get("license_url"),
                "maintainer": metadata.get("maintainer"),
                "maintainer_email": metadata.get("maintainer_email"),
                "image_url": metadata.get("organization", {}).get("image_url"),
            }
            debug_logger.debug(f"Dataset defaults: {dataset_defaults}")
                
            # Try to find existing dataset
            try:
                debug_logger.debug(f"Looking for existing dataset with ID: {metadata.get('id')}")
                dataset = DatasetCatalog.objects.get(dataset_id=metadata.get('id'))
                created = False
                debug_logger.debug("Found existing dataset, will update")
                
                # Inspect model fields to detect binary fields
                binary_fields = []
                for field in dataset._meta.fields:
                    if isinstance(field, BinaryField):
                        binary_fields.append(field.name)
                        debug_logger.debug(f"Found binary field: {field.name}")
                
                # Update fields one by one to isolate any errors
                for field, value in dataset_defaults.items():
                    try:
                        debug_logger.debug(f"Setting field {field} to {repr(value)} ({type(value)})")
                        # Skip binary fields for now to prevent errors
                        if field in binary_fields:
                            debug_logger.debug(f"Skipping binary field {field}")
                            continue
                        setattr(dataset, field, value)
                    except Exception as e:
                        debug_logger.error(f"Error setting field {field}: {e}")
                
                # Preserve the existing embedding value to prevent overwriting with None
                if 'embedding' in binary_fields and dataset.embedding is not None:
                    embedding_value = dataset.embedding
                else:
                    embedding_value = None
                
                debug_logger.debug("Saving dataset after updating fields")
                try:
                    dataset.save(update_fields=[f for f in dataset_defaults.keys() if f not in binary_fields])
                    debug_logger.debug("Successfully saved with update_fields parameter")
                except Exception as e:
                    debug_logger.error(f"Error saving with update_fields: {e}")
                    # If that fails, restore the embedding and try a different approach
                    if embedding_value is not None:
                        dataset.embedding = embedding_value
                    dataset_data = {k: v for k, v in dataset_defaults.items() if k not in binary_fields}
                    DatasetCatalog.objects.filter(dataset_id=dataset.dataset_id).update(**dataset_data)
                    debug_logger.debug("Successfully saved with direct update query")
                
            except DatasetCatalog.DoesNotExist:
                debug_logger.debug("Dataset doesn't exist, creating new one")
                try:
                    # Inspect model fields to remove binary fields from creation
                    model_fields = {}
                    binary_fields = []
                    for field in DatasetCatalog._meta.fields:
                        if isinstance(field, BinaryField):
                            binary_fields.append(field.name)
                            debug_logger.debug(f"Found binary field in model: {field.name}")
                    
                    # Remove binary fields from defaults
                    cleaned_defaults = {k: v for k, v in dataset_defaults.items() if k not in binary_fields}
                    
                    try:
                        dataset = DatasetCatalog.objects.create(
                            dataset_id=metadata.get('id'),
                            **cleaned_defaults
                        )
                        debug_logger.debug("Successfully created dataset with cleaned defaults")
                    except Exception as e:
                        debug_logger.error(f"Error creating dataset with cleaned defaults: {e}")
                        # Try a more direct approach
                        dataset = DatasetCatalog(dataset_id=metadata.get('id'))
                        for field, value in cleaned_defaults.items():
                            setattr(dataset, field, value)
                        dataset.save()
                        debug_logger.debug("Successfully created dataset with alternative approach")
                    created = True
                    debug_logger.debug("Successfully created new dataset")
                except Exception as e:
                    debug_logger.error(f"Error creating dataset: {e}")
                    raise
            
            # Process tags
            if "tags" in metadata:
                try:
                    debug_logger.debug("Processing tags")
                    tags = []
                    for tag in metadata["tags"]:
                        if tag.get("name"):
                            tag_name = tag.get("name")
                            if not isinstance(tag_name, str):
                                tag_name = str(tag_name)
                            tags.append(tag_name)
                    
                    debug_logger.debug(f"Setting {len(tags)} tags")
                    # The model uses a property that maps to tags_json
                    dataset.tags = tags
                    try:
                        # Update only the tags field to avoid binary field issues
                        DatasetCatalog.objects.filter(dataset_id=dataset.dataset_id).update(tags_json=json.dumps(tags))
                        debug_logger.debug("Successfully updated tags with direct update query")
                    except Exception as e:
                        debug_logger.error(f"Error updating tags: {e}")
                except Exception as e:
                    debug_logger.error(f"Error processing tags: {e}")
            
            # Process extras
            if "extras" in metadata:
                try:
                    debug_logger.debug("Processing extras")
                    extras = {}
                    for item in metadata["extras"]:
                        if item.get("key"):
                            key = item.get("key")
                            if not isinstance(key, str):
                                key = str(key)
                                
                            value = item.get("value")
                            if value is not None:
                                if not isinstance(value, str):
                                    value = str(value)
                                    
                                debug_logger.debug(f"Adding extra: {key} = {value}")
                                extras[key] = value
                    
                    debug_logger.debug(f"Setting {len(extras)} extras")
                    # The model uses a property that maps to extras_json
                    dataset.extras = extras
                    
                    try:
                        # Update extras in a single database update
                        update_fields = {'extras_json': json.dumps(extras)}
                        
                        # Extract important dates and publisher
                        if "issued" in extras:
                            update_fields['datagov_date_issued'] = extras["issued"]
                        if "modified" in extras:
                            update_fields['datagov_date_last_modified'] = extras["modified"]
                        if "publisher" in extras:
                            update_fields['datagov_publisher'] = extras["publisher"]
                            
                        # Update directly in the database
                        DatasetCatalog.objects.filter(dataset_id=dataset.dataset_id).update(**update_fields)
                        debug_logger.debug("Successfully updated extras with direct update query")
                    except Exception as e:
                        debug_logger.error(f"Error updating extras: {e}")
                except Exception as e:
                    debug_logger.error(f"Error processing extras: {e}")
            
            # Process groups
            if "groups" in metadata:
                try:
                    debug_logger.debug("Processing groups")
                    groups = []
                    for group in metadata["groups"]:
                        if group.get("id"):
                            group_id = group.get("id")
                            if not isinstance(group_id, str):
                                group_id = str(group_id)
                                
                            group_name = group.get("name") or ""
                            if not isinstance(group_name, str):
                                group_name = str(group_name)
                                
                            group_title = group.get("title") or ""
                            if not isinstance(group_title, str):
                                group_title = str(group_title)
                                
                            group_desc = group.get("description") or ""
                            if not isinstance(group_desc, str):
                                group_desc = str(group_desc)
                            
                            group_data = {
                                "id": group_id,
                                "name": group_name,
                                "title": group_title,
                                "description": group_desc
                            }
                            debug_logger.debug(f"Adding group: {group_data}")
                            groups.append(group_data)
                    
                    if groups:
                        debug_logger.debug(f"Setting {len(groups)} groups")
                        # The model uses a property that maps to groups_json
                        dataset.groups = groups
                        try:
                            # Update directly in the database
                            DatasetCatalog.objects.filter(dataset_id=dataset.dataset_id).update(groups_json=json.dumps(groups))
                            debug_logger.debug("Successfully updated groups with direct update query")
                        except Exception as e:
                            debug_logger.error(f"Error updating groups: {e}")
                except Exception as e:
                    debug_logger.error(f"Error processing groups: {e}")
            
            # Set search text for basic search
            try:
                debug_logger.debug("Setting search text")
                search_text_parts = [
                    dataset.title or "",
                    dataset.notes or "",
                    dataset.organization_title or "",
                    " ".join(dataset.tags) if dataset.tags else "",
                ]
                search_text = " ".join(filter(None, search_text_parts))
                debug_logger.debug(f"Search text length: {len(search_text)}")
                
                # Simply set the search_text field
                dataset.search_text = search_text
                try:
                    # Update directly in the database
                    DatasetCatalog.objects.filter(dataset_id=dataset.dataset_id).update(search_text=search_text)
                    debug_logger.debug("Successfully updated search_text with direct update query")
                except Exception as e:
                    debug_logger.error(f"Error updating search_text: {e}")
            except Exception as e:
                debug_logger.error(f"Error setting search text: {e}")
            
            debug_logger.debug("Successfully processed dataset")
            return dataset
            
        except Exception as e:
            logger.error(f"Error updating dataset record: {e}")
            debug_logger.exception(f"Detailed exception in update_dataset_record:")
            self.stats["errors"] += 1
            return None
    
    @transaction.atomic
    def update_resource_records(self, dataset, dataset_info, collection_path=None):
        """Update or create resource records for a dataset"""
        metadata = dataset_info["metadata"]["signed_metadata"]["data_gov_metadata"]
        resources_info = metadata.get("resources", [])
        
        updated_resources = []
        
        for resource_info in resources_info:
            resource_id = resource_info.get("id")
            if not resource_id or not resource_info.get("url"):
                continue
                
            try:
                # Handle datetime fields with timezone awareness
                created_date = resource_info.get("created")
                if created_date and isinstance(created_date, str):
                    try:
                        # Parse datetime and ensure it's timezone-aware
                        created_date = django.utils.timezone.make_aware(
                            datetime.datetime.fromisoformat(created_date.replace('Z', '+00:00')),
                            timezone=django.utils.timezone.get_current_timezone()
                        )
                    except (ValueError, TypeError):
                        created_date = None
                
                last_modified = resource_info.get("last_modified")
                if last_modified and isinstance(last_modified, str):
                    try:
                        # Parse datetime and ensure it's timezone-aware
                        last_modified = django.utils.timezone.make_aware(
                            datetime.datetime.fromisoformat(last_modified.replace('Z', '+00:00')),
                            timezone=django.utils.timezone.get_current_timezone()
                        )
                    except (ValueError, TypeError):
                        last_modified = None
                
                # Try to find existing resource
                resource, created = DatasetResource.objects.get_or_create(
                    resource_id=resource_id,
                    defaults={
                        "dataset": dataset,
                        "name": resource_info.get("name", "Unnamed Resource"),
                        "description": resource_info.get("description"),
                        "format": resource_info.get("format"),
                        "url": resource_info.get("url"),
                        "size": resource_info.get("size"),
                        "created": created_date,
                        "last_modified": last_modified,
                        "mimetype": resource_info.get("mimetype"),
                        "mimetype_inner": resource_info.get("mimetype_inner"),
                        "position": resource_info.get("position"),
                        "state": resource_info.get("state"),
                        "hash": resource_info.get("hash"),
                    }
                )
                
                if not created:
                    # Update existing resource
                    resource.name = resource_info.get("name", "Unnamed Resource")
                    resource.description = resource_info.get("description")
                    resource.format = resource_info.get("format")
                    resource.url = resource_info.get("url")
                    resource.size = resource_info.get("size")
                    resource.created = created_date
                    resource.last_modified = last_modified
                    resource.mimetype = resource_info.get("mimetype")
                    resource.mimetype_inner = resource_info.get("mimetype_inner")
                    resource.position = resource_info.get("position")
                    resource.state = resource_info.get("state")
                    resource.hash = resource_info.get("hash")
                    resource.save()
                
                # Check resource availability
                availability = self.check_resource_availability(resource.url, dataset.dataset_id)
                self.stats["resources_checked"] += 1
                
                if availability["is_available"]:
                    self.stats["resources_available"] += 1
                else:
                    self.stats["resources_unavailable"] += 1
                
                # Update resource availability
                resource.is_available = availability["is_available"]
                resource.last_availability_check = timezone.now()
                
                # Store availability history (keep last 10 checks)
                if resource.availability_history is None:
                    resource.availability_history = []
                    
                history_entry = {
                    "date": timezone.now().isoformat(),
                    "available": availability["is_available"],
                    "status": availability["http_status"]
                }
                
                resource.availability_history.insert(0, history_entry)
                resource.availability_history = resource.availability_history[:10]  # Keep last 10
                resource.save()
                
                # Create availability check record
                check = ResourceAvailabilityCheck.objects.create(
                    resource=resource,
                    is_available=availability["is_available"],
                    http_status=availability["http_status"],
                    response_time_ms=availability["response_time_ms"],
                    error_message=availability["error_message"]
                )
                
                # Always try to extract from archive to check if resource is cached
                if collection_path:  # Try regardless of availability status
                    collection_file = self.download_collection_file(collection_path)
                    
                    if collection_file and collection_file.exists():
                        extracted = self.extract_resource_from_archive(collection_file, resource_info)
                        
                        if extracted:
                            # Update resource with archive information
                            resource.in_harvard_archive = True
                            resource.harvard_archive_path = dataset_info["harvard_archive_path"]
                            resource.harvard_archive_version = dataset_info["version"]
                            resource.content_hash = extracted["hash"]
                            resource.content_size_bytes = extracted["size"]
                            resource.save()
                            
                            # Update availability check
                            check.found_in_archive = True
                            check.archive_path = extracted["path"]
                            check.save()
                            
                            self.stats["resources_cached"] += 1
                
                updated_resources.append(resource)
                
            except Exception as e:
                logger.error(f"Error updating resource record {resource_id}: {e}")
                self.stats["errors"] += 1
        
        return updated_resources
    
    @transaction.atomic
    def process_dataset(self, metadata_path):
        """Process a single dataset metadata file"""
        try:
            # Extract dataset info from metadata
            dataset_info = self.extract_dataset_info(metadata_path)
            if not dataset_info:
                return False
                
            # Check if we already processed this dataset version
            archive_check = DataGovArchiveCheck.objects.filter(
                dataset_name=dataset_info["dataset_name"],
                latest_version_checked=dataset_info["version"]
            ).first()
            
            if archive_check and self.process_new_only:
                logger.info(f"Skipping already processed dataset {dataset_info['dataset_name']} ({dataset_info['version']})")
                return False
                
            # Create or update the dataset in our database
            dataset = self.update_dataset_record(dataset_info)
            if not dataset:
                return False
                
            # Create or update resources
            resources = self.update_resource_records(dataset, dataset_info, dataset_info["collection_path"])
            
            # Update archive check record
            now = timezone.now()
            available_resources_count = sum(1 for r in resources if r.is_available)
            has_usable_resources = available_resources_count > 0
            
            # Initialize default values for new or existing archive_check
            existing_had_resources = False
            existing_has_usable_resources = False
            resources_gone_bad = False
            last_available_in_datagov = now
            last_check_with_usable_resources = now if has_usable_resources else None
            availability_history = []
            
            # Check for existing archive_check and update values accordingly
            if archive_check:
                # If dataset was processed before, fetch its previous state
                existing_had_resources = archive_check.resources_checked > 0
                existing_has_usable_resources = archive_check.resources_available > 0
                
                # Detect if resources have gone bad
                resources_gone_bad = (existing_has_usable_resources and not has_usable_resources)
            
            # Create history entry
            history_entry = {
                "date": now.isoformat(),
                "resources_checked": len(resources),
                "resources_available": available_resources_count,
                "has_usable_resources": has_usable_resources,
                "version": dataset_info["version"]
            }
            
            # Add new entry at the beginning of the history
            availability_history.insert(0, history_entry)
            
            # Limit history to last 10 entries to avoid excessive growth
            availability_history = availability_history[:10]
            
            # Determine if the dataset has or had resources
            had_resources = existing_had_resources or len(resources) > 0
            
            # Create or update the archive check record with enhanced tracking
            archive_check, archive_check_created = DataGovArchiveCheck.objects.update_or_create(
                dataset_name=dataset_info["dataset_name"],
                defaults={
                    "latest_version_checked": dataset_info["version"],
                    "last_checked_at": now,
                    "is_processed": True,
                    "in_our_database": True,
                    "resources_checked": len(resources),
                    "resources_available": available_resources_count,
                    "archive_path": dataset_info["harvard_archive_path"],
                    "downloaded": True,
                    # Enhanced tracking fields
                    "is_still_in_datagov": True,  # We're finding it now, so it's still in Data.gov
                    "last_available_in_datagov": last_available_in_datagov,
                    "had_resources": had_resources,
                    "has_usable_resources": has_usable_resources,
                    "resources_gone_bad": resources_gone_bad,
                    "last_check_with_usable_resources": last_check_with_usable_resources,
                    "availability_history": availability_history
                }
            )
            
            # Log important status changes
            if resources_gone_bad:
                self.stats["resources_gone_bad"] += 1
                logger.warning(f"Dataset {dataset_info['dataset_name']} resources have gone bad! "
                               f"Previously had usable resources but now all are unavailable.")
            
            # Clean up temporary files for this dataset
            if self.cleanup:
                logger.info(f"Cleaning up temporary files for dataset {dataset_info['dataset_name']}...")
                self.cleanup_temp_files(dataset_name=dataset_info["dataset_name"], version=dataset_info["version"])
            
            logger.info(f"Processed dataset {dataset_info['dataset_name']} ({dataset_info['version']}): "
                        f"{len(resources)} resources, {sum(1 for r in resources if r.is_available)} available")
            
            self.stats["datasets_processed"] += 1
            return True
            
        except Exception as e:
            logger.error(f"Error processing dataset {metadata_path}: {e}")
            self.stats["errors"] += 1
            return False
    
    def mark_missing_datasets(self, processed_dataset_names):
        """Mark datasets that were previously in Data.gov but are now missing
        
        Args:
            processed_dataset_names: Set of dataset names found in the current run
        """
        # Get all datasets that were previously marked as being in Data.gov
        cutoff_date = timezone.now() - datetime.timedelta(days=30)  # Consider datasets checked within last 30 days
        previously_available = DataGovArchiveCheck.objects.filter(
            is_still_in_datagov=True,
            last_checked_at__gt=cutoff_date
        )
        
        missing_count = 0
        
        # Check each previously available dataset
        for dataset in previously_available:
            if dataset.dataset_name not in processed_dataset_names:
                # This dataset was not found in the current run
                logger.warning(f"Dataset {dataset.dataset_name} is no longer available in Data.gov!")
                
                # Update the record to indicate it's no longer in Data.gov
                dataset.is_still_in_datagov = False
                dataset.save(update_fields=["is_still_in_datagov"])
                
                missing_count += 1
        
        if missing_count > 0:
            logger.info(f"Found {missing_count} datasets that are no longer available in Data.gov")
        
        return missing_count

    def run(self):
        """Run the archive processor"""
        logger.info("Starting Data.gov Archive Processor")
        start_time = time.time()
        
        try:
            processed_dataset_names = set()  # Track dataset names we find
            
            if self.single_path:
                # Process just the single path
                logger.info(f"Processing single file: {self.single_path}")
                local_path = self.download_metadata_file(self.single_path)
                if local_path:
                    dataset_info = self.extract_dataset_info(local_path)
                    if dataset_info:
                        processed_dataset_names.add(dataset_info["dataset_name"])
                    self.process_dataset(local_path)
            else:
                # Get the list of metadata files
                metadata_files = self.list_s3_metadata()
                
                # Store original length before slicing
                original_count = len(metadata_files)
                
                # Apply start index if specified
                if self.start_index > 0:
                    if self.start_index < len(metadata_files):
                        logger.info(f"Starting from file index {self.start_index}")
                        metadata_files = metadata_files[self.start_index:]
                    else:
                        logger.warning(f"Start index {self.start_index} exceeds the number of files {len(metadata_files)}")
                
                # Apply limit if specified
                if self.limit:
                    metadata_files = metadata_files[:self.limit]
                    
                # Process metadata files in parallel
                with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                    # Submit all tasks to the executor
                    future_to_file = {
                        executor.submit(self.process_metadata_file, i + self.start_index, metadata_file, original_count): metadata_file
                        for i, metadata_file in enumerate(metadata_files)
                    }
                    
                    # Process completed tasks as they finish
                    completed_count = 0
                    for future in as_completed(future_to_file):
                        metadata_file = future_to_file[future]
                        try:
                            dataset_name, processed = future.result()
                            if dataset_name:
                                processed_dataset_names.add(dataset_name)
                            
                            # Periodically clean up memory
                            completed_count += 1
                            if completed_count % 100 == 0:
                                logger.info(f"Completed {completed_count} files, cleaning up memory...")
                                self.cleanup_memory()
                                self.check_and_cleanup_disk_space(force=True)
                        except Exception as e:
                            logger.error(f"Error processing {metadata_file}: {e}")
                            self.stats["errors"] += 1
            
            # If not processing a single path, check for missing datasets
            # Skip this check if using a limit to avoid false positives
            if not self.single_path and not self.process_new_only and not self.limit:
                missing_count = self.mark_missing_datasets(processed_dataset_names)
                self.stats["datasets_missing"] = missing_count
            
            # Print final stats
            runtime = time.time() - start_time
            logger.info(f"Finished processing in {runtime:.2f} seconds")
            logger.info(f"Stats: {json.dumps(self.stats, indent=2)}")
            
        except Exception as e:
            logger.error(f"Error in processor: {e}")
            raise
        finally:
            # Clean up if needed
            if self.cleanup:
                logger.info("Cleaning up temporary files...")
                self.cleanup_temp_files()
    
    def check_and_cleanup_disk_space(self, force=False):
        """Check disk space usage and clean up if necessary"""
        try:
            # Get temp directory size
            total_size = 0
            for dirpath, dirnames, filenames in os.walk(TEMP_DIR):
                for filename in filenames:
                    file_path = os.path.join(dirpath, filename)
                    if os.path.exists(file_path):  # Check if file still exists
                        try:
                            total_size += os.path.getsize(file_path)
                        except (FileNotFoundError, OSError):
                            # File might have been deleted by another process
                            pass
            
            # Convert to MB
            total_size_mb = total_size / (1024 * 1024)
            
            # Clean up if over threshold or forced
            if force or total_size_mb > MAX_TEMP_STORAGE_MB:
                logger.info(f"Temp directory size: {total_size_mb:.2f}MB, cleaning up...")
                self.cleanup_temp_files(age_threshold=300 if force else MAX_TEMP_FILE_AGE)  # 5 minutes if forced
                return True
            return False
        except Exception as e:
            logger.error(f"Error checking disk space: {e}")
            return False

    def cleanup_temp_files(self, dataset_name=None, version=None, age_threshold=MAX_TEMP_FILE_AGE):
        """Remove temporary files
        
        If dataset_name and version are provided, only clean up files for that dataset.
        Otherwise, clean up all files that are older than the age threshold.
        
        Args:
            dataset_name: Name of dataset to clean up
            version: Version of dataset to clean up
            age_threshold: Age threshold in seconds (default: MAX_TEMP_FILE_AGE)
        """
        try:
            if dataset_name and version:
                # Clean up specific dataset files
                logger.debug(f"Cleaning up files for dataset {dataset_name}/{version}")
                
                # Clean up metadata file
                metadata_path = TEMP_DIR / dataset_name / f"{version}.json"
                if os.path.exists(metadata_path):
                    logger.debug(f"Removing metadata file: {metadata_path}")
                    os.remove(metadata_path)
                
                # Clean up collection file
                collection_path = TEMP_DIR / f"{S3_COLLECTIONS_PREFIX}/{dataset_name}/{version}.zip"
                if os.path.exists(collection_path):
                    logger.debug(f"Removing collection file: {collection_path}")
                    os.remove(collection_path)
                
                # Clean up extracted files for this dataset
                extracted_dir = TEMP_DIR / "extracted"
                if os.path.exists(extracted_dir):
                    for item in os.listdir(extracted_dir):
                        item_path = os.path.join(extracted_dir, item)
                        # If item contains dataset name, remove it
                        if dataset_name in item:
                            try:
                                if os.path.isfile(item_path):
                                    logger.debug(f"Removing extracted file: {item_path}")
                                    os.remove(item_path)
                                elif os.path.isdir(item_path):
                                    logger.debug(f"Removing extracted directory: {item_path}")
                                    shutil.rmtree(item_path, ignore_errors=True)
                            except Exception as e:
                                logger.debug(f"Error removing {item_path}: {e}")
            else:
                # Clean up all old files
                cutoff_time = time.time() - age_threshold
                logger.debug(f"Cleaning up all files older than {age_threshold} seconds")
                
                # Use a safer approach by processing directories one by one
                for root, dirs, files in os.walk(TEMP_DIR, topdown=False):
                    # Remove old files
                    for file in files:
                        try:
                            file_path = os.path.join(root, file)
                            if os.path.exists(file_path) and os.path.getmtime(file_path) < cutoff_time:
                                logger.debug(f"Removing old file: {file_path}")
                                os.remove(file_path)
                        except (FileNotFoundError, PermissionError, OSError) as e:
                            logger.debug(f"Error removing file {file_path}: {e}")
                    
                    # Try to remove empty directories
                    for dir_name in dirs:
                        try:
                            dir_path = os.path.join(root, dir_name)
                            if os.path.exists(dir_path) and not os.listdir(dir_path):
                                logger.debug(f"Removing empty directory: {dir_path}")
                                os.rmdir(dir_path)
                        except (FileNotFoundError, PermissionError, OSError) as e:
                            logger.debug(f"Error removing directory {dir_path}: {e}")
                
                # Special handling for the extracted directory - be more aggressive
                extracted_dir = TEMP_DIR / "extracted"
                if os.path.exists(extracted_dir):
                    for item in os.listdir(extracted_dir):
                        try:
                            item_path = os.path.join(extracted_dir, item)
                            if os.path.isfile(item_path) and os.path.getmtime(item_path) < cutoff_time:
                                logger.debug(f"Removing old extracted file: {item_path}")
                                os.remove(item_path)
                            elif os.path.isdir(item_path):
                                # For directories, check if all contents are old
                                should_remove = True
                                for subitem in os.listdir(item_path):
                                    subitem_path = os.path.join(item_path, subitem)
                                    if os.path.getmtime(subitem_path) >= cutoff_time:
                                        should_remove = False
                                        break
                                
                                if should_remove:
                                    logger.debug(f"Removing old extracted directory: {item_path}")
                                    shutil.rmtree(item_path, ignore_errors=True)
                        except Exception as e:
                            logger.debug(f"Error processing extracted item {item_path}: {e}")
                
                # Also check for any orphaned temporary files in the system temp directory
                # that might have our prefix but not be in our main directory
                system_temp = Path(tempfile.gettempdir())
                try:
                    for item in os.listdir(system_temp):
                        if 'data_gov_archive' in item:
                            item_path = os.path.join(system_temp, item)
                            if os.path.isfile(item_path) and os.path.getmtime(item_path) < cutoff_time:
                                logger.debug(f"Removing orphaned temp file: {item_path}")
                                os.remove(item_path)
                except Exception as e:
                    logger.debug(f"Error cleaning system temp directory: {e}")
        except Exception as e:
            logger.error(f"Error in cleanup_temp_files: {e}")

    def test_download(self, test_path="fruit-and-vegetable-prices/v1.json"):
        """Test downloading a single metadata file"""
        logger.info(f"Testing download with path: {test_path}")
        
        try:
            # Download the test file
            local_path = self.download_metadata_file(test_path)
            
            if local_path:
                logger.info(f"Successfully downloaded test file to: {local_path}")
                
                # Try to read the file
                with open(local_path, 'r') as f:
                    content = f.read()
                    logger.info(f"File content preview: {content[:200]}...")
                
                return True
            else:
                logger.error("Failed to download test file")
                return False
                
        except Exception as e:
            logger.error(f"Error in test download: {e}")
            return False

    def cleanup_memory(self):
        """Force garbage collection to free up memory"""
        try:
            # Force garbage collection
            collected = gc.collect()
            logger.debug(f"Garbage collector: collected {collected} objects")
            return True
        except Exception as e:
            logger.error(f"Error cleaning up memory: {e}")
            return False

    def process_metadata_file(self, index, metadata_file, total_files):
        """Process a single metadata file (to be used with ThreadPoolExecutor)"""
        # Display index+1 to show 1-based numbering for human readability
        # But keep the absolute index (which includes the start_index)
        logger.info(f"Processing file {index+1}/{total_files}: {metadata_file}")
        
        # Check disk space every 5 files instead of 10
        if index % 5 == 0:
            self.check_and_cleanup_disk_space()
            self.cleanup_memory()
            
        local_path = self.download_metadata_file(metadata_file)
        
        dataset_name = None
        processed = False
        
        if local_path:
            dataset_info = self.extract_dataset_info(local_path)
            if dataset_info:
                dataset_name = dataset_info["dataset_name"]
                processed = self.process_dataset(local_path)
                
                # Clean up this dataset's files immediately after processing
                if self.cleanup and dataset_name:
                    self.cleanup_temp_files(dataset_name=dataset_name, version=dataset_info["version"])
        
        return dataset_name, processed


class DataGovLinkRotChecker:
    """Periodically check resources in our database for link rot"""
    
    def __init__(self, check_interval_days=30, max_resources=None, force_recheck=False):
        self.check_interval_days = check_interval_days
        self.max_resources = max_resources
        self.force_recheck = force_recheck
        self.stats = {
            "resources_checked": 0,
            "resources_available": 0,
            "resources_unavailable": 0,
            "resource_status_changed": 0,
            "errors": 0
        }
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
    
    def get_resources_to_check(self):
        """Get resources that should be checked for availability"""
        cutoff_date = timezone.now() - datetime.timedelta(days=self.check_interval_days)
        
        query = DatasetResource.objects.all()
        
        if not self.force_recheck:
            # Only check resources that haven't been checked recently
            query = query.filter(
                models.Q(last_availability_check__isnull=True) | 
                models.Q(last_availability_check__lt=cutoff_date)
            )
        
        if self.max_resources:
            query = query[:self.max_resources]
            
        return query
    
    def check_resource_availability(self, resource):
        """Check if a resource is available at its URL"""
        try:
            start_time = time.time()
            response = self.session.head(resource.url, timeout=HTTP_TIMEOUT, allow_redirects=True)
            response_time = int((time.time() - start_time) * 1000)  # ms
            
            # Consider it available if not explicitly a 404/403/410 status code
            is_available = response.status_code not in [404, 403, 410]
            
            # Try GET if HEAD doesn't work (some servers don't support HEAD)
            if not is_available or response.status_code == 405:
                start_time = time.time()
                response = self.session.get(resource.url, timeout=HTTP_TIMEOUT, stream=True, allow_redirects=True)
                response.close()  # Don't download the whole file
                response_time = int((time.time() - start_time) * 1000)  # ms
                is_available = response.status_code not in [404, 403, 410]
            
            # Record the check
            check = ResourceAvailabilityCheck.objects.create(
                resource=resource,
                is_available=is_available,
                http_status=response.status_code,
                response_time_ms=response_time
            )
            
            # Update the resource record
            previous_status = resource.is_available
            resource.is_available = is_available
            resource.last_availability_check = timezone.now()
            
            # Update availability history
            if resource.availability_history is None:
                resource.availability_history = []
                
            history_entry = {
                "date": timezone.now().isoformat(),
                "available": is_available,
                "status": response.status_code
            }
            
            resource.availability_history.insert(0, history_entry)
            resource.availability_history = resource.availability_history[:10]  # Keep last 10
            resource.save()
            
            # Update stats
            self.stats["resources_checked"] += 1
            if is_available:
                self.stats["resources_available"] += 1
            else:
                self.stats["resources_unavailable"] += 1
                
            if previous_status != is_available:
                self.stats["resource_status_changed"] += 1
            
            return is_available
            
        except requests.RequestException as e:
            # Only consider timeout errors as "available" - the resource might be slow but still there
            is_timeout = "timeout" in str(e).lower()
            is_available = is_timeout  # Consider timeouts as "available"
            
            # Record the check
            check = ResourceAvailabilityCheck.objects.create(
                resource=resource,
                is_available=is_available,
                error_message=str(e)
            )
            
            # Update the resource record
            previous_status = resource.is_available
            resource.is_available = is_available
            resource.last_availability_check = timezone.now()
            
            # Update availability history
            if resource.availability_history is None:
                resource.availability_history = []
                
            history_entry = {
                "date": timezone.now().isoformat(),
                "available": is_available,
                "error": str(e)
            }
            
            resource.availability_history.insert(0, history_entry)
            resource.availability_history = resource.availability_history[:10]  # Keep last 10
            resource.save()
            
            # Update stats
            self.stats["resources_checked"] += 1
            
            if is_available:
                self.stats["resources_available"] += 1
            else:
                self.stats["resources_unavailable"] += 1
                self.stats["errors"] += 1
            
            if previous_status != is_available:
                self.stats["resource_status_changed"] += 1
                
            return is_available
    
    def run(self):
        """Run the link rot checker"""
        logger.info("Starting Data.gov Link Rot Checker")
        start_time = time.time()
        
        try:
            # Get resources to check
            resources = self.get_resources_to_check()
            logger.info(f"Found {resources.count()} resources to check")
            
            # Process resources in parallel
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                future_to_resource = {
                    executor.submit(self.check_resource_availability, resource): resource
                    for resource in resources
                }
                
                for future in as_completed(future_to_resource):
                    resource = future_to_resource[future]
                    try:
                        is_available = future.result()
                        logger.debug(f"Resource {resource.resource_id}: {'Available' if is_available else 'Unavailable'}")
                    except Exception as e:
                        logger.error(f"Error checking resource {resource.resource_id}: {e}")
                        self.stats["errors"] += 1
            
            # Print final stats
            runtime = time.time() - start_time
            logger.info(f"Finished checking in {runtime:.2f} seconds")
            logger.info(f"Stats: {json.dumps(self.stats, indent=2)}")
            
        except Exception as e:
            logger.error(f"Error in checker: {e}")
            raise


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Data.gov Link Rot Updater")
    
    # Archive processor arguments
    parser.add_argument("--limit", type=int, help="Limit processing to N datasets")
    parser.add_argument("--process-new-only", action="store_true", help="Only process new datasets")
    parser.add_argument("--cleanup", action="store_true", help="Clean up temporary files after processing")
    parser.add_argument("--path", type=str, help="Process a single path instead of listing all files")
    parser.add_argument("--start-index", type=int, help="Start processing from this file index (0-based)")
    
    # Link rot checker arguments
    parser.add_argument("--check-resources", action="store_true", help="Check resources for link rot")
    parser.add_argument("--check-interval", type=int, default=30, help="Days between resource checks")
    parser.add_argument("--max-resources", type=int, help="Maximum number of resources to check")
    parser.add_argument("--force-recheck", action="store_true", help="Force recheck of all resources")
    
    # Test mode
    parser.add_argument("--test", action="store_true", help="Run in test mode with a single file")
    parser.add_argument("--test-path", type=str, default="metadata/data_gov/fruit-and-vegetable-prices/v1.json", 
                       help="Path to test file (default: metadata/data_gov/fruit-and-vegetable-prices/v1.json)")
    
    args = parser.parse_args()
    
    if args.test:
        # Run test mode
        processor = DataGovArchiveProcessor(cleanup=args.cleanup)
        success = processor.test_download(args.test_path)
        if not success:
            sys.exit(1)
    elif args.check_resources:
        # Run link rot checker
        checker = DataGovLinkRotChecker(
            check_interval_days=args.check_interval,
            max_resources=args.max_resources,
            force_recheck=args.force_recheck
        )
        checker.run()
    else:
        # Run archive processor
        processor = DataGovArchiveProcessor(
            limit=args.limit,
            process_new_only=args.process_new_only,
            cleanup=args.cleanup,
            single_path=args.path,
            start_index=args.start_index if args.start_index is not None else 0
        )
        processor.run()


if __name__ == "__main__":
    main()