import numpy as np
from openai import OpenAI
import os
import time
from django.core.management.base import BaseCommand
from factchecker.models import DatasetCatalog
from tqdm import tqdm

class Command(BaseCommand):
    help = 'Generate embeddings for dataset catalog entries using OpenAI'

    def add_arguments(self, parser):
        parser.add_argument(
            '--batch-size',
            type=int,
            default=100,
            help='Number of datasets to process in each batch'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force regeneration of embeddings even if already indexed'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Limit the number of datasets to process (for testing)'
        )

    def handle(self, *args, **options):
        # TODO: Add support for Azure OpenAI for creating embeddings
        batch_size = options['batch_size']
        force = options['force']
        limit = options['limit']
        
        # Get OpenAI API key
        openai_api_key = os.environ.get("OPENAI_API_KEY")
        if not openai_api_key:
            self.stdout.write(self.style.ERROR("OpenAI API key not found. Set OPENAI_API_KEY environment variable."))
            return
            
        client = OpenAI(api_key=openai_api_key)
        
        # Get datasets that need embeddings
        if force:
            datasets = DatasetCatalog.objects.all()
            self.stdout.write(f"Generating embeddings for all datasets (force mode)")
        else:
            datasets = DatasetCatalog.objects.filter(indexed=False)
            self.stdout.write(f"Generating embeddings for unindexed datasets")
        
        # Apply limit if specified
        if limit:
            datasets = datasets[:limit]
            self.stdout.write(f"Limited to {limit} datasets")
            
        total_datasets = datasets.count()
        self.stdout.write(f"Total datasets to process: {total_datasets}")
        
        # Process in batches
        total_processed = 0
        for i in tqdm(range(0, total_datasets, batch_size), desc="Processing batches"):
            batch = datasets[i:i+batch_size]
            batch_texts = []
            batch_ids = []
            
            # Prepare batch of texts to embed
            for dataset in batch:
                # Create text to embed (combine title, description, and organization)
                text_to_embed = f"Title: {dataset.title}\nDescription: {dataset.description or ''}\nOrganization: {dataset.organization_title or ''}"
                batch_texts.append(text_to_embed)
                batch_ids.append(dataset.dataset_id)
            
            try:
                # Generate embeddings for the batch
                response = client.embeddings.create(
                    input=batch_texts,
                    model="text-embedding-3-small"
                )
                
                # Update each dataset with its embedding
                for j, embedding_data in enumerate(response.data):
                    dataset_id = batch_ids[j]
                    embedding_vector = embedding_data.embedding
                    
                    # Convert to numpy array, then to bytes for storage
                    embedding_bytes = np.array(embedding_vector, dtype=np.float32).tobytes()
                    
                    # Update the dataset
                    DatasetCatalog.objects.filter(dataset_id=dataset_id).update(
                        embedding=embedding_bytes,
                        indexed=True
                    )
                
                total_processed += len(batch)
                self.stdout.write(f"Processed {total_processed}/{total_datasets} datasets")
                
                # Add a small delay to avoid rate limits
                time.sleep(0.1)
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error generating embeddings for batch: {e}"))
                # Continue with next batch
        
        self.stdout.write(self.style.SUCCESS(f"Embedding generation complete! {total_processed} datasets processed."))