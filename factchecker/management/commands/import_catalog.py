import json
import os
from django.core.management.base import BaseCommand
from factchecker.models import DatasetCatalog
from tqdm import tqdm
import ijson  # pip install ijson

class Command(BaseCommand):
    help = 'Import dataset catalog from JSON file into database'

    def add_arguments(self, parser):
        parser.add_argument('json_file', type=str, help='Path to the JSON catalog file')
        parser.add_argument('--batch-size', type=int, default=1000, help='Batch size for processing')
        parser.add_argument('--skip-existing', action='store_true', help='Skip existing datasets')

    def handle(self, *args, **options):
        json_file = options['json_file']
        batch_size = options['batch_size']
        skip_existing = options['skip_existing']
        
        if not os.path.exists(json_file):
            self.stdout.write(self.style.ERROR(f"File not found: {json_file}"))
            return
        
        self.stdout.write(f"Importing catalog from {json_file}...")
        
        # Get file size for progress tracking
        file_size = os.path.getsize(json_file)
        self.stdout.write(f"File size: {file_size/1024/1024:.2f} MB")
        
        # Use ijson for streaming JSON parsing (memory efficient)
        batch_data = []
        datasets_processed = 0
        
        # If skip_existing, get existing dataset IDs
        existing_ids = set()
        if skip_existing:
            self.stdout.write("Getting existing dataset IDs...")
            existing_ids = set(DatasetCatalog.objects.values_list('dataset_id', flat=True))
            self.stdout.write(f"Found {len(existing_ids)} existing datasets")
        
        try:
            # Open the file and parse datasets
            with open(json_file, 'rb') as f:
                # Parse the datasets array
                datasets = ijson.items(f, 'datasets.item')
                
                # Process each dataset
                for dataset in tqdm(datasets, desc="Importing datasets"):
                    # Skip if already exists and skip_existing is True
                    if skip_existing and dataset.get('id') in existing_ids:
                        continue
                    
                    # Create search text for basic search
                    search_text = f"{dataset.get('title', '')} {dataset.get('description', '')}"
                    if 'organization' in dataset:
                        search_text += f" {dataset['organization'].get('title', '')}"
                    
                    # Create model instance
                    dataset_obj = DatasetCatalog(
                        dataset_id=dataset.get('id', ''),
                        title=dataset.get('title', ''),
                        description=dataset.get('description', ''),
                        organization_name=dataset.get('organization', {}).get('name', ''),
                        organization_title=dataset.get('organization', {}).get('title', ''),
                        search_text=search_text,
                        indexed=False
                    )
                    
                    batch_data.append(dataset_obj)
                    datasets_processed += 1
                    
                    # Process batch if we've reached batch size
                    if len(batch_data) >= batch_size:
                        DatasetCatalog.objects.bulk_create(
                            batch_data, 
                            update_conflicts=True,
                            unique_fields=['dataset_id'],
                            update_fields=['title', 'description', 'organization_name', 
                                          'organization_title', 'search_text']
                        )
                        self.stdout.write(f"Imported {datasets_processed} datasets so far...")
                        batch_data = []
            
            # Insert any remaining datasets
            if batch_data:
                DatasetCatalog.objects.bulk_create(
                    batch_data, 
                    update_conflicts=True,
                    unique_fields=['dataset_id'],
                    update_fields=['title', 'description', 'organization_name', 
                                  'organization_title', 'search_text']
                )
            
            # Get final dataset count
            total_imported = DatasetCatalog.objects.count()
            self.stdout.write(self.style.SUCCESS(
                f"Import complete! Imported {datasets_processed} datasets. "
                f"Total in database: {total_imported}"
            ))
            
        except json.JSONDecodeError as e:
            self.stdout.write(self.style.ERROR(f"JSON parsing error: {e}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error importing catalog: {e}"))
