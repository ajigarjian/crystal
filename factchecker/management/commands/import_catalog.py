import json
import os
import warnings
from django.core.management.base import BaseCommand
from factchecker.models import DatasetCatalog, DatasetResource
from django.utils.dateparse import parse_datetime
from tqdm import tqdm
import ijson

class Command(BaseCommand):
    help = 'Import dataset catalog from JSON file into database'

    def add_arguments(self, parser):
        parser.add_argument('json_file', type=str, help='Path to the JSON catalog file')
        parser.add_argument('--batch-size', type=int, default=500, help='Batch size for processing')
        parser.add_argument('--skip-existing', action='store_true', help='Skip existing datasets')

    def handle(self, *args, **options):
        # Suppress datetime warnings
        warnings.filterwarnings('ignore', category=RuntimeWarning, module='django.db.models.fields')
        
        json_file = options['json_file']
        batch_size = options['batch_size']
        skip_existing = options['skip_existing']
        
        if not os.path.exists(json_file):
            self.stdout.write(self.style.ERROR(f"File not found: {json_file}"))
            return
        
        self.stdout.write(self.style.SUCCESS(f"\nStarting import from {json_file}..."))
        file_size = os.path.getsize(json_file)
        self.stdout.write(self.style.SUCCESS(f"File size: {file_size/1024/1024:.2f} MB"))
        
        batch_data = []
        resource_batch = []
        datasets_processed = 0
        
        existing_ids = set()
        if skip_existing:
            self.stdout.write("Getting existing dataset IDs...")
            existing_ids = set(DatasetCatalog.objects.values_list('dataset_id', flat=True))
            self.stdout.write(f"Found {len(existing_ids)} existing datasets")
        
        def safe_parse_datetime(dt_str):
            """Safely parse datetime string, returning None if invalid"""
            if not dt_str or not isinstance(dt_str, str):
                return None
            try:
                return parse_datetime(dt_str)
            except (ValueError, TypeError):
                return None

        try:
            with open(json_file, 'rb') as f:
                # First, count total datasets for progress bar
                self.stdout.write("Counting total datasets (this might take a minute)...")
                total_datasets = sum(1 for _ in ijson.items(f, 'datasets.item'))
                f.seek(0)  # Reset file pointer
                
                self.stdout.write(self.style.SUCCESS(f"\nFound {total_datasets} datasets to process"))
                self.stdout.write("Starting import (you should see progress bar below):")
                self.stdout.flush()  # Force output to show
                
                # Now process with progress bar
                datasets = ijson.items(f, 'datasets.item')
                for dataset in tqdm(datasets, total=total_datasets, desc="Importing datasets"):
                    if skip_existing and dataset.get('id') in existing_ids:
                        continue
                    
                    # Create search text including all relevant fields
                    search_text = self.build_search_text(dataset)

                    # Create dataset object with all fields
                    dataset_obj = DatasetCatalog(
                        dataset_id=dataset.get('id', ''),
                        title=dataset.get('title', ''),
                        description=dataset.get('description', ''),
                        notes=dataset.get('notes', ''),
                        organization_name=dataset.get('organization', {}).get('name', ''),
                        organization_title=dataset.get('organization', {}).get('title', ''),
                        search_text=search_text,
                        license_id=dataset.get('license_id'),
                        license_title=dataset.get('license_title'),
                        license_url=dataset.get('license_url'),
                        maintainer=dataset.get('maintainer'),
                        maintainer_email=dataset.get('maintainer_email'),
                        metadata_created=safe_parse_datetime(dataset.get('metadata_created')),
                        metadata_modified=safe_parse_datetime(dataset.get('metadata_modified')),
                        tags_json=json.dumps(dataset.get('tags', [])),
                        extras_json=json.dumps(dataset.get('extras', [])),
                        groups_json=json.dumps(dataset.get('groups', [])),
                        indexed=False,
                        image_url=dataset.get('image_url'),
                    )
                    
                    batch_data.append(dataset_obj)
                    
                    # Prepare resources for this dataset
                    for resource in dataset.get('resources', []):
                        resource_obj = DatasetResource(
                            resource_id=resource.get('id', ''),
                            dataset_id=dataset.get('id', ''),
                            name=resource.get('name', ''),
                            description=resource.get('description', ''),
                            format=resource.get('format'),
                            url=resource.get('url', ''),
                            size=resource.get('size'),
                            created=safe_parse_datetime(resource.get('created')),
                            last_modified=safe_parse_datetime(resource.get('last_modified')),
                            mimetype=resource.get('mimetype'),
                            mimetype_inner=resource.get('mimetype_inner'),
                            position=resource.get('position'),
                            state=resource.get('state'),
                            hash=resource.get('hash')
                        )
                        resource_batch.append(resource_obj)
                    
                    datasets_processed += 1
                    
                    # Process batches if we've reached batch size
                    if len(batch_data) >= batch_size:
                        # Create datasets
                        DatasetCatalog.objects.bulk_create(
                            batch_data,
                            update_conflicts=True,
                            unique_fields=['dataset_id'],
                            update_fields=['title', 'description', 'notes', 'organization_name', 
                                        'organization_title', 'search_text', 'license_id',
                                        'license_title', 'license_url', 'maintainer',
                                        'maintainer_email', 'metadata_created',
                                        'metadata_modified', 'tags_json', 'extras_json',
                                        'groups_json', 'image_url']
                        )
                        
                        # Create resources
                        if resource_batch:
                            DatasetResource.objects.bulk_create(
                                resource_batch,
                                update_conflicts=True,
                                unique_fields=['resource_id'],
                                update_fields=['name', 'description', 'format', 'url',
                                            'size', 'created', 'last_modified', 'mimetype',
                                            'mimetype_inner', 'position', 'state', 'hash']
                            )
                        
                        self.stdout.write(self.style.SUCCESS(
                            f"\nBatch complete - {datasets_processed}/{total_datasets} datasets processed"
                            f"\nDatasets in this batch: {len(batch_data)}"
                            f"\nResources in this batch: {len(resource_batch)}\n"
                        ))
                        self.stdout.flush()
                        
                        batch_data = []
                        resource_batch = []
            
            # Insert any remaining datasets and resources
            if batch_data:
                DatasetCatalog.objects.bulk_create(
                    batch_data,
                    update_conflicts=True,
                    unique_fields=['dataset_id'],
                    update_fields=['title', 'description', 'notes', 'organization_name',
                                'organization_title', 'search_text', 'license_id',
                                'license_title', 'license_url', 'maintainer',
                                'maintainer_email', 'metadata_created',
                                'metadata_modified', 'tags_json', 'extras_json',
                                'groups_json', 'image_url']
                )
                
            if resource_batch:
                DatasetResource.objects.bulk_create(
                    resource_batch,
                    update_conflicts=True,
                    unique_fields=['resource_id'],
                    update_fields=['name', 'description', 'format', 'url',
                                'size', 'created', 'last_modified', 'mimetype',
                                'mimetype_inner', 'position', 'state', 'hash']
                )
            
            total_datasets = DatasetCatalog.objects.count()
            total_resources = DatasetResource.objects.count()
            self.stdout.write(self.style.SUCCESS(
                f"Import complete! Processed {datasets_processed} datasets.\n"
                f"Total in database: {total_datasets} datasets, {total_resources} resources"
            ))
            
        except json.JSONDecodeError as e:
            self.stdout.write(self.style.ERROR(f"JSON parsing error: {e}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error importing catalog: {e}"))

    def build_search_text(self, dataset):
        components = [
            # Core dataset information
            f"Title: {dataset.get('title', '')}",
            f"Description: {dataset.get('notes', '')}",
            
            # Organization context
            f"Organization: {dataset.get('organization', {}).get('title', '')}",
            f"Organization Description: {dataset.get('organization', {}).get('description', '')}",
            
            # Tags (very important for search)
            f"Tags: {' '.join(tag.get('name', '') for tag in dataset.get('tags', []))}",
            
            # Resource summaries (include format and brief description)
            "Resources: " + ' '.join(
                f"{res.get('name', '')} ({res.get('format', '')})"
                for res in dataset.get('resources', [])[:3]  # Limit to first 3 resources
            ),
            
            # Groups/Categories
            f"Categories: {' '.join(group.get('title', '') for group in dataset.get('groups', []))}",
            
            # Key extras that might help search
            f"Theme: {next((extra.get('value') for extra in dataset.get('extras', []) if extra.get('key') == 'theme'), '')}"
        ]
        
        return "\n".join(filter(None, components))
