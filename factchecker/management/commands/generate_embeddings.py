import numpy as np
from openai import OpenAI
import os
import time
import re
import json
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
            count = datasets.count()
            self.stdout.write(f"Generating embeddings for all datasets (force mode): {count} datasets found")
        else:
            datasets = DatasetCatalog.objects.filter(indexed=False)
            count = datasets.count()
            self.stdout.write(f"Generating embeddings for unindexed datasets: {count} datasets found")
        
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
                # Extract theme from extras
                theme = ''
                if dataset.extras:
                    for extra in dataset.extras:
                        if extra.get('key') == 'theme' and extra.get('value'):
                            theme_value = extra.get('value')
                            if isinstance(theme_value, list):
                                theme = ', '.join(theme_value)
                            else:
                                theme = str(theme_value)
                            break
                
                # Extract groups information
                groups_text = ''
                if dataset.groups:
                    group_names = []
                    for group in dataset.groups:
                        if group.get('title'):
                            group_names.append(group.get('title'))
                        elif group.get('name'):
                            group_names.append(group.get('name'))
                    groups_text = ', '.join(group_names)
                
                # Clean text fields
                clean_title = self.clean_text(dataset.title)
                clean_notes = self.clean_text(self.remove_html_tags(dataset.notes or ''))
                clean_org = self.clean_text(dataset.organization_title or '')
                
                # Extract tag names from the tag dictionaries
                tag_names = []
                if dataset.tags:
                    for tag in dataset.tags:
                        if isinstance(tag, dict) and 'name' in tag:
                            tag_names.append(tag['name'])
                        elif isinstance(tag, str):
                            tag_names.append(tag)
                
                # Create text to embed with all relevant fields
                text_to_embed = f"""Title: {clean_title}
                    Notes: {clean_notes}
                    Organization: {clean_org}
                    Tags: {', '.join(tag_names)}
                    Theme: {theme}
                    Groups: {groups_text}"""
                
                # Truncate if text is too long
                text_to_embed = self.truncate_text(text_to_embed)
                
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
                        indexed=True,
                        search_text=batch_texts[j]  # Store the processed text for reference
                    )
                
                total_processed += len(batch)
                self.stdout.write(f"Processed {total_processed}/{total_datasets} datasets")
                
                # Add a small delay to avoid rate limits
                time.sleep(0.1)
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error generating embeddings for batch: {e}"))
                # Continue with next batch
        
        self.stdout.write(self.style.SUCCESS(f"Embedding generation complete! {total_processed} datasets processed."))
    
    def remove_html_tags(self, text):
        """Remove HTML tags from text"""
        if not text:
            return ""
        return re.sub(r'<[^>]+>', ' ', text)
    
    def clean_text(self, text):
        """Clean and normalize text"""
        if not text:
            return ""
        # Remove special characters but keep important ones
        text = re.sub(r'[^\w\s\-\.,;:#&\'"/()]', ' ', text)
        # Normalize whitespace
        return ' '.join(text.split())
    
    def truncate_text(self, text, max_chars=12000):
        """Truncate text while preserving complete sections"""
        if len(text) <= max_chars:
            return text
            
        sections = text.split('\n')
        result = []
        current_length = 0
        
        for section in sections:
            section_name = section.split(':', 1)[0] if ':' in section else ''
            # Always include title and tags even if we're close to the limit
            if (current_length + len(section) + 1 > max_chars and 
                not section_name in ["Title", "Tags"]):
                break
            result.append(section)
            current_length += len(section) + 1
            
        return '\n'.join(result)