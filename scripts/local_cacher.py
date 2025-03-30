#!/usr/bin/env python3
import os
import sys
import logging

# Make sure "functions" is on your python path if "factchecker" is inside "functions/"
# If your layout is something like:
#   functions/
#       factchecker/
#           __init__.py
#           settings.py
this_dir = os.path.dirname(__file__)
parent_dir = os.path.join(this_dir, "..")
sys.path.append(parent_dir)            # parent of scripts/

# Also add the functions directory to the path so 'factchecker' can be found directly
# This is needed because Django settings.py has 'factchecker' in INSTALLED_APPS
functions_dir = os.path.join(parent_dir, 'functions')
sys.path.append(functions_dir)

import django
import json
import requests
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import tempfile
import shutil
from google.cloud import storage
from io import BytesIO
import time
import urllib.parse
from datetime import datetime, timezone
import concurrent.futures
from functools import partial

# Point DJANGO_SETTINGS_MODULE to the correct module path where settings.py lives.
# If your settings are at "functions/factchecker/settings.py", do:
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'functions.factchecker.settings')

# We've already added the necessary paths earlier

# Now that paths and environment are set up, initialize Django
django.setup()

# Only after django.setup(), import your Django models
from factchecker.models import DatasetResource, DatasetCatalog

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Constants
DATA_GOV_API_URL = "https://catalog.data.gov/api/3/action/package_search"
BUCKET_NAME = "cyrystal-cached-datasets"  # Replace with your actual GCP bucket name
DATA_GOV_FOLDER = "data_gov"
SUPPORTED_FORMATS = ["CSV", "XLS", "XLSX", "JSON"]
MAX_DATASET_SIZE_MB = 500  # Maximum size to download (in MB)

class DataGovCacher:
    def __init__(self):
        try:
            self.client = storage.Client()
            # Check if bucket exists, create if not
            if not self.client.bucket(BUCKET_NAME).exists():
                print("No bucket exists")
                #self.client.create_bucket(BUCKET_NAME)
            self.bucket = self.client.bucket(BUCKET_NAME)
        except Exception as e:
            logger.error(f"Error initializing GCP client: {e}")
            logger.info("Will run without GCP storage capabilities")
            self.client = None
            self.bucket = None

    def query_top_datasets(self, limit=250):
        """
        Query the data.gov API for the top viewed datasets.
        
        Args:
            limit: Number of datasets to retrieve (default: 250)
            
        Returns:
            List of dataset objects from data.gov
        """
        params = {
            "sort": "views_recent desc",
            "rows": limit
        }
        
        logger.info(f"Querying data.gov API for top {limit} datasets...")
        
        try:
            response = requests.get(DATA_GOV_API_URL, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            datasets = data.get('result', {}).get('results', [])
            logger.info(f"Retrieved {len(datasets)} datasets from data.gov")
            
            return datasets
        except requests.exceptions.RequestException as e:
            logger.error(f"Error querying data.gov API: {e}")
            return []

    def get_resource_size(self, resource):
        """
        Get the size of a resource in bytes.
        Try to get from the size field, or make a HEAD request if not available.
        
        Args:
            resource: Resource object from data.gov
            
        Returns:
            Size in bytes or None if not available
        """
        # Check if size is already in the resource metadata
        if 'size' in resource and resource['size']:
            try:
                return int(resource['size'])
            except (ValueError, TypeError):
                # Size might be a string or something else
                pass
            
        # Try to get size from a HEAD request
        try:
            headers = {
                'User-Agent': 'Crystal-DataGov-Cacher/1.0',
                'Accept': '*/*'
            }
            
            # Skip URLs that are likely web pages, not data files
            url = resource.get('url', '')
            if any(ext in url.lower() for ext in ['.aspx', '.html', '.htm', '/www.']):
                logger.warning(f"Skipping URL that appears to be a webpage: {url}")
                return None
                
            # Make HEAD request with timeout and redirects
            response = requests.head(
                url, 
                headers=headers, 
                timeout=10, 
                allow_redirects=True
            )
            
            if response.status_code >= 400:
                logger.warning(f"URL returned status code {response.status_code}: {url}")
                return None
                
            # Check content type to avoid HTML pages
            content_type = response.headers.get('Content-Type', '').lower()
            if 'html' in content_type and not url.lower().endswith(('.csv', '.xls', '.xlsx', '.json')):
                logger.warning(f"URL returns HTML content, not data: {url}")
                return None
                
            # Get content length
            if 'Content-Length' in response.headers:
                return int(response.headers['Content-Length'])
        except Exception as e:
            logger.warning(f"Could not determine size for resource {resource.get('id', 'unknown')}: {str(e)[:100]}")
            
        # If we can't determine the size, use a small default to allow processing
        # but put it at the end of the priority list
        return 1

    def find_largest_csv(self, resources):
        """
        Find the largest CSV resource from a list of resources.
        
        Args:
            resources: List of resource objects from data.gov
            
        Returns:
            The resource object for the largest CSV, or None if no suitable resource found
        """
        largest_resource = None
        largest_size = 0
        
        for resource in resources:
            # Skip if format is not in supported formats
            resource_format = resource.get('format', '').upper()
            if resource_format not in SUPPORTED_FORMATS:
                continue
                
            # Get resource size
            size = self.get_resource_size(resource)
            if not size:
                continue
                
            # Skip if resource is too large
            if size > MAX_DATASET_SIZE_MB * 1024 * 1024:
                logger.info(f"Skipping resource {resource.get('id', 'unknown')} - too large ({size/(1024*1024):.2f} MB)")
                continue
                
            # Find the largest resource
            if size > largest_size:
                largest_size = size
                largest_resource = resource
        
        return largest_resource

    def download_and_convert_to_parquet(self, resource):
        """
        Download a resource and convert it to parquet format.
        
        Args:
            resource: Resource object from data.gov
            
        Returns:
            Tuple of (success, local_path) where success is a boolean and local_path is the path to the 
            downloaded and converted file, or None if not successful
        """
        resource_id = resource.get('id', 'unknown')
        resource_url = resource.get('url', '')
        resource_format = resource.get('format', '').upper()
        
        logger.info(f"Downloading resource {resource_id} from {resource_url}")
        
        # Create a temporary directory outside the context manager to preserve the file
        temp_dir = tempfile.mkdtemp()
        output_path = None
        
        try:
            # Check if URL is likely a data file or a webpage
            if any(ext in resource_url.lower() for ext in ['.aspx', '.html', '.htm']) and not resource_url.lower().endswith(('.csv', '.xls', '.xlsx', '.json')):
                logger.warning(f"URL appears to be a webpage, not data: {resource_url}")
                return False, None
                
            # Download the resource with timeout and proper headers
            headers = {
                'User-Agent': 'Crystal-DataGov-Cacher/1.0',
                'Accept': '*/*'
            }
            
            try:
                response = requests.get(
                    resource_url, 
                    stream=True, 
                    headers=headers, 
                    timeout=30, 
                    allow_redirects=True
                )
                response.raise_for_status()
            except requests.exceptions.RequestException as e:
                logger.error(f"Error downloading {resource_url}: {str(e)[:100]}")
                # This is a clear download error case
                return False, None
            
            # Determine file extension
            if resource_format == "CSV":
                file_ext = ".csv"
            elif resource_format == "XLS":
                file_ext = ".xls"
            elif resource_format == "XLSX":
                file_ext = ".xlsx"
            elif resource_format == "JSON":
                file_ext = ".json"
            else:
                logger.warning(f"Unsupported format: {resource_format}")
                return False, None
            
            # Save the downloaded file
            input_path = os.path.join(temp_dir, f"input{file_ext}")
            with open(input_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            # Convert to a DataFrame based on format
            if resource_format == "CSV":
                try:
                    # Try with default encoding
                    df = pd.read_csv(input_path, low_memory=False)
                except Exception as e:
                    # Try with different encoding
                    try:
                        df = pd.read_csv(input_path, encoding='latin1', low_memory=False)
                    except Exception as e2:
                        # Try with more options
                        try:
                            df = pd.read_csv(input_path, encoding='latin1', engine='python', sep=None, on_bad_lines='skip')
                        except Exception as e3:
                            logger.error(f"Error reading CSV with multiple methods: {e}, {e2}, {e3}")
                            # This is a resource parsing error
                            return False, None
            elif resource_format in ["XLS", "XLSX"]:
                try:
                    # Try with auto-detection
                    df = pd.read_excel(input_path)
                except Exception as e:
                    # Try with explicit engine
                    try:
                        if resource_format == "XLS":
                            df = pd.read_excel(input_path, engine='xlrd')
                        else:
                            df = pd.read_excel(input_path, engine='openpyxl')
                    except Exception as e2:
                        # Try with CSV parser in case it's mislabeled
                        try:
                            df = pd.read_csv(input_path, encoding='latin1', engine='python', sep=None, on_bad_lines='skip')
                        except Exception as e3:
                            logger.error(f"Error reading Excel file with multiple methods: {e}, {e2}, {e3}")
                            # This is a resource parsing error
                            return False, None
            elif resource_format == "JSON":
                try:
                    df = pd.read_json(input_path)
                except Exception as e:
                    # Try as records
                    try:
                        with open(input_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        if isinstance(data, list):
                            df = pd.DataFrame(data)
                        else:
                            df = pd.DataFrame([data])
                    except Exception as e2:
                        # Try with different encoding
                        try:
                            with open(input_path, 'r', encoding='latin1') as f:
                                data = json.load(f)
                            if isinstance(data, list):
                                df = pd.DataFrame(data)
                            else:
                                df = pd.DataFrame([data])
                        except Exception as e3:
                            logger.error(f"Error reading JSON with multiple methods: {e}, {e2}, {e3}")
                            # This is a resource parsing error
                            return False, None
            
            # Write to parquet
            output_path = os.path.join(temp_dir, f"{resource_id}.parquet")
            table = pa.Table.from_pandas(df)
            pq.write_table(table, output_path, compression='snappy')
            
            # Check if the file was actually written
            if not os.path.exists(output_path):
                logger.error(f"Parquet file was not created at {output_path}")
                return False, None
                
            logger.info(f"Successfully converted resource {resource_id} to parquet at {output_path}")
            return True, output_path
            
        except Exception as e:
            logger.error(f"Error processing resource {resource_id}: {str(e)[:200]}")
            return False, None

    def upload_to_gcp(self, local_path, resource_id):
        """
        Upload a file to GCP bucket.
        
        Args:
            local_path: Path to the local file to upload
            resource_id: ID of the resource
            
        Returns:
            The GCS URI of the uploaded file or None if upload failed
        """
        # Check if GCP client is available
        if not self.client or not self.bucket:
            logger.warning("GCP client not available, skipping upload")
            # Return a local URI for testing
            return f"file://{local_path}"
            
        try:
            # Verify the file exists
            if not os.path.isfile(local_path):
                logger.error(f"File does not exist: {local_path}")
                return None
                
            # Create destination path in GCP bucket
            destination_blob_name = f"{DATA_GOV_FOLDER}/{resource_id}/{os.path.basename(local_path)}"
            
            # Upload file
            blob = self.bucket.blob(destination_blob_name)
            blob.upload_from_filename(local_path)
            
            # Return the GCS URI
            gcs_uri = f"gs://{BUCKET_NAME}/{destination_blob_name}"
            logger.info(f"File uploaded to: {gcs_uri}")
            
            return gcs_uri
        except Exception as e:
            logger.error(f"Error uploading to GCP: {str(e)[:200]}")
            # Return file URI for testing if GCP upload fails
            return f"file://{local_path}"

    def update_resource_in_db(self, resource_id, cache_uri):
        """
        Update the resource in the database with cache information.
        
        Args:
            resource_id: ID of the resource
            cache_uri: URI of the cached resource in GCP
            
        Returns:
            Boolean indicating success
        """
        try:
            # Get the resource from the database
            resource = DatasetResource.objects.get(resource_id=resource_id)
            
            # Update cache information
            resource.is_cached = True
            resource.cache_uri = cache_uri
            resource.resource_download_error = False  # Clear any previous error flag
            resource.last_cached = datetime.now(timezone.utc)  # Set the last_cached timestamp
            resource.save()
            
            logger.info(f"Updated database record for resource {resource_id}")
            return True
        except DatasetResource.DoesNotExist:
            logger.error(f"Resource {resource_id} not found in database")
        except Exception as e:
            logger.error(f"Error updating database: {str(e)[:200]}")
        
        return False
        
    def mark_resource_download_error(self, resource_id):
        """
        Mark a resource as having a download error in the database.
        
        Args:
            resource_id: ID of the resource
            
        Returns:
            Boolean indicating success
        """
        try:
            # Get the resource from the database
            resource = DatasetResource.objects.get(resource_id=resource_id)
            
            # Set the download error flag
            resource.resource_download_error = True
            resource.save()
            
            logger.info(f"Marked resource {resource_id} as having a download error")
            return True
        except DatasetResource.DoesNotExist:
            logger.error(f"Resource {resource_id} not found in database")
        except Exception as e:
            logger.error(f"Error updating database: {str(e)[:200]}")
        
        return False

    def save_dataset_to_db_if_not_exists(self, dataset):
        """
        Save a dataset to the database if it does not exist.
        
        Args:
            dataset: Dataset object from data.gov
            
        Returns:
            DatasetCatalog object
        """
        dataset_id = dataset.get('id', '')
        if not dataset_id:
            logger.warning("Dataset missing ID, cannot save to database")
            return None
            
        try:
            # Check if dataset already exists
            db_dataset = DatasetCatalog.objects.get(dataset_id=dataset_id)
            logger.info(f"Dataset {dataset_id} already exists in database")
            return db_dataset
        except DatasetCatalog.DoesNotExist:
            # Create a new dataset record
            logger.info(f"Creating new dataset record for {dataset_id}")
            
            try:
                db_dataset = DatasetCatalog(
                    dataset_id=dataset_id,
                    title=dataset.get('title', ''),
                    notes=dataset.get('notes', ''),
                    organization_name=dataset.get('organization', {}).get('name', ''),
                    organization_title=dataset.get('organization', {}).get('title', ''),
                    organization_description=dataset.get('organization', {}).get('description', '')
                )
                
                # Handle tags
                if 'tags' in dataset:
                    tags = [tag.get('name', '') for tag in dataset.get('tags', [])]
                    db_dataset.tags = tags
                
                # Additional fields
                db_dataset.license_id = dataset.get('license_id', '')
                db_dataset.license_title = dataset.get('license_title', '')
                db_dataset.license_url = dataset.get('license_url', '')
                db_dataset.maintainer = dataset.get('maintainer', '')
                db_dataset.maintainer_email = dataset.get('maintainer_email', '')
                
                # Parse datetime fields - use UTC timezone to avoid warning
                if 'metadata_created' in dataset and dataset['metadata_created']:
                    try:
                        # Parse the datetime and make it timezone-aware if needed
                        dt = datetime.fromisoformat(dataset['metadata_created'].replace('Z', '+00:00'))
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        db_dataset.metadata_created = dt
                    except Exception as e:
                        logger.warning(f"Could not parse metadata_created: {e}")
                
                if 'metadata_modified' in dataset and dataset['metadata_modified']:
                    try:
                        dt = datetime.fromisoformat(dataset['metadata_modified'].replace('Z', '+00:00'))
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        db_dataset.metadata_modified = dt
                    except Exception as e:
                        logger.warning(f"Could not parse metadata_modified: {e}")
                
                # Save the dataset
                db_dataset.save()
                
                return db_dataset
            except Exception as e:
                logger.error(f"Error creating dataset record: {str(e)[:200]}")
                return None

    def save_resource_to_db_if_not_exists(self, resource, dataset_obj):
        """
        Save a resource to the database if it does not exist.
        
        Args:
            resource: Resource object from data.gov
            dataset_obj: DatasetCatalog object
            
        Returns:
            DatasetResource object
        """
        resource_id = resource.get('id', '')
        if not resource_id:
            logger.warning("Resource missing ID, cannot save to database")
            return None
            
        try:
            # Check if resource already exists
            db_resource = DatasetResource.objects.get(resource_id=resource_id)
            logger.info(f"Resource {resource_id} already exists in database")
            return db_resource
        except DatasetResource.DoesNotExist:
            # Create a new resource record
            logger.info(f"Creating new resource record for {resource_id}")
            
            try:
                db_resource = DatasetResource(
                    resource_id=resource_id,
                    dataset=dataset_obj,
                    name=resource.get('name', ''),
                    description=resource.get('description', ''),
                    format=resource.get('format', ''),
                    url=resource.get('url', ''),
                    size=resource.get('size', None),
                    mimetype=resource.get('mimetype', ''),
                    mimetype_inner=resource.get('mimetype_inner', ''),
                    position=resource.get('position', None),
                    state=resource.get('state', ''),
                    hash=resource.get('hash', '')
                )
                
                # Parse datetime fields with proper timezone handling
                if 'created' in resource and resource['created']:
                    try:
                        dt = datetime.fromisoformat(resource['created'].replace('Z', '+00:00'))
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        db_resource.created = dt
                    except Exception as e:
                        logger.warning(f"Could not parse created date: {e}")
                
                if 'last_modified' in resource and resource['last_modified']:
                    try:
                        dt = datetime.fromisoformat(resource['last_modified'].replace('Z', '+00:00'))
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        db_resource.last_modified = dt
                    except Exception as e:
                        logger.warning(f"Could not parse last_modified date: {e}")
                
                # Save the resource
                db_resource.save()
                
                return db_resource
            except Exception as e:
                logger.error(f"Error creating resource record: {str(e)[:200]}")
                return None

    def process_datasets(self, limit=250, max_workers=10):
        """
        Process the top datasets from data.gov in parallel.
        
        Args:
            limit: Number of datasets to process (default: 250)
            max_workers: Maximum number of parallel workers (default: 10)
            
        Returns:
            Number of successfully cached resources
        """
        # Query top datasets
        datasets = self.query_top_datasets(limit)
        
        if not datasets:
            logger.warning("No datasets retrieved from data.gov")
            return 0
        
        cached_count = 0
        
        # Process datasets in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_dataset = {
                executor.submit(self.process_single_dataset, dataset): dataset 
                for dataset in datasets
            }
            
            # Process results as they complete
            for future in concurrent.futures.as_completed(future_to_dataset):
                dataset = future_to_dataset[future]
                dataset_id = dataset.get('id', 'unknown')
                
                try:
                    success = future.result()
                    if success:
                        cached_count += 1
                        logger.info(f"Successfully processed dataset {dataset_id}")
                    else:
                        logger.info(f"No suitable resources found or processing failed for dataset {dataset_id}")
                except Exception as e:
                    logger.error(f"Exception processing dataset {dataset_id}: {str(e)[:200]}")
        
        return cached_count
    
    def process_single_dataset(self, dataset):
        """
        Process a single dataset from data.gov.
        
        Args:
            dataset: Dataset object from data.gov
            
        Returns:
            Boolean indicating if a resource was successfully cached
        """
        dataset_id = dataset.get('id', 'unknown')
        resources = dataset.get('resources', [])
        
        logger.info(f"Processing dataset {dataset_id} with {len(resources)} resources")
        
        # Save dataset to database if not exists
        dataset_obj = self.save_dataset_to_db_if_not_exists(dataset)
        if not dataset_obj:
            logger.warning(f"Skipping dataset {dataset_id} - could not save to database")
            return False
        
        # Find the largest suitable resource
        resource = self.find_largest_csv(resources)
        if not resource:
            logger.info(f"No suitable resources found for dataset {dataset_id}")
            return False
        
        # Save resource to database if not exists
        resource_obj = self.save_resource_to_db_if_not_exists(resource, dataset_obj)
        if not resource_obj:
            logger.warning(f"Skipping resource {resource.get('id', 'unknown')} - could not save to database")
            return False
        
        # Check if resource is already cached
        if resource_obj.is_cached and resource_obj.cache_uri:
            logger.info(f"Resource {resource.get('id', 'unknown')} is already cached at {resource_obj.cache_uri}")
            return True
        
        # Download and convert to parquet
        temp_path = None
        try:
            success, temp_path = self.download_and_convert_to_parquet(resource)
            if not success or not temp_path:
                logger.warning(f"Failed to download/convert resource {resource.get('id', 'unknown')}")
                # Mark resource as having a download error
                self.mark_resource_download_error(resource.get('id', 'unknown'))
                return False
            
            # Upload to GCP bucket
            cache_uri = self.upload_to_gcp(temp_path, resource.get('id', 'unknown'))
            if not cache_uri:
                logger.warning(f"Failed to upload resource {resource.get('id', 'unknown')} to GCP")
                # Mark resource as having a download error
                self.mark_resource_download_error(resource.get('id', 'unknown'))
                return False
            
            # Update resource in database
            if self.update_resource_in_db(resource.get('id', 'unknown'), cache_uri):
                logger.info(f"Successfully cached resource {resource.get('id', 'unknown')}")
                return True
            return False
        except Exception as e:
            # Mark resource as having a download error
            logger.error(f"Error processing resource {resource.get('id', 'unknown')}: {str(e)[:200]}")
            self.mark_resource_download_error(resource.get('id', 'unknown'))
            return False
        finally:
            # Clean up temp files
            if temp_path and os.path.exists(os.path.dirname(temp_path)):
                try:
                    shutil.rmtree(os.path.dirname(temp_path), ignore_errors=True)
                except Exception as e:
                    logger.warning(f"Error cleaning up temp directory: {e}")

def main():
    """Main function to run the data.gov cacher."""
    logger.info("Starting data.gov cacher")
    
    cacher = DataGovCacher()
    
    # Process datasets 250-500 with parallel execution (up to 10 workers)
    # First get datasets 0-500
    all_datasets = cacher.query_top_datasets(limit=500)
    
    # Take only datasets from index 250 to 499
    datasets_to_process = all_datasets[250:500] if len(all_datasets) > 250 else []
    
    logger.info(f"Processing datasets 250-500 ({len(datasets_to_process)} datasets)")
    
    # Process the selected datasets in parallel
    cached_count = 0
    if datasets_to_process:
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            # Submit all tasks
            future_to_dataset = {
                executor.submit(cacher.process_single_dataset, dataset): dataset 
                for dataset in datasets_to_process
            }
            
            # Process results as they complete
            for future in concurrent.futures.as_completed(future_to_dataset):
                dataset = future_to_dataset[future]
                dataset_id = dataset.get('id', 'unknown')
                
                try:
                    success = future.result()
                    if success:
                        cached_count += 1
                        logger.info(f"Successfully processed dataset {dataset_id}")
                    else:
                        logger.info(f"No suitable resources found or processing failed for dataset {dataset_id}")
                except Exception as e:
                    logger.error(f"Exception processing dataset {dataset_id}: {str(e)[:200]}")
    
    logger.info(f"Completed processing. Successfully cached {cached_count} resources.")

if __name__ == "__main__":
    main()