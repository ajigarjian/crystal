import numpy as np
from openai import OpenAI
import os
import time
import re
from django.core.management.base import BaseCommand
from factchecker.models import CensusDataset, CensusVariable
from tqdm import tqdm
from django.db.models import Count

class Command(BaseCommand):
    help = 'Generate embeddings for Census datasets and variables using OpenAI'

    def add_arguments(self, parser):
        parser.add_argument(
            '--batch-size',
            type=int,
            default=100,
            help='Number of items to process in each batch'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force regeneration of embeddings even if already indexed'
        )
        parser.add_argument(
            '--datasets-only',
            action='store_true',
            help='Only generate embeddings for datasets (skip variables)'
        )
        parser.add_argument(
            '--variables-only',
            action='store_true',
            help='Only generate embeddings for variables (skip datasets)'
        )
        parser.add_argument(
            '--dataset',
            type=str,
            help='Process only variables from a specific dataset (format: vintage/path, e.g. 2020/acs/acs5)'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Limit the number of items to process (for testing)'
        )

    def handle(self, *args, **options):
        batch_size = options['batch_size']
        force = options['force']
        limit = options['limit']
        datasets_only = options['datasets_only']
        variables_only = options['variables_only']
        specific_dataset = options['dataset']
        
        # Get OpenAI API key
        openai_api_key = os.environ.get("OPENAI_API_KEY")
        if not openai_api_key:
            self.stdout.write(self.style.ERROR("OpenAI API key not found. Set OPENAI_API_KEY environment variable."))
            return
            
        client = OpenAI(api_key=openai_api_key)
        
        # Process datasets (unless variables-only flag is set)
        if not variables_only:
            self.process_datasets(client, batch_size, force, limit)
        
        # Process variables (unless datasets-only flag is set)
        if not datasets_only:
            self.process_variables(client, batch_size, force, limit, specific_dataset)
            
        self.stdout.write(self.style.SUCCESS("Embedding generation complete!"))
    
    def process_datasets(self, client, batch_size, force, limit):
        """Generate embeddings for Census datasets"""
        # Get datasets that need embeddings
        if force:
            datasets = CensusDataset.objects.all()
            count = datasets.count()
            self.stdout.write(f"Generating embeddings for all Census datasets (force mode): {count} datasets found")
        else:
            datasets = CensusDataset.objects.filter(embedding__isnull=True)
            count = datasets.count()
            self.stdout.write(f"Generating embeddings for unindexed Census datasets: {count} datasets found")
        
        # Apply limit if specified
        if limit:
            datasets = datasets[:limit]
            self.stdout.write(f"Limited to {limit} datasets")
            
        total_datasets = datasets.count()
        if total_datasets == 0:
            self.stdout.write("No datasets to process.")
            return
            
        self.stdout.write(f"Total Census datasets to process: {total_datasets}")
        
        # Process in batches
        total_processed = 0
        for i in tqdm(range(0, total_datasets, batch_size), desc="Processing dataset batches"):
            batch = datasets[i:i+batch_size]
            batch_texts = []
            batch_ids = []
            
            # Prepare batch of texts to embed
            for dataset in batch:
                # Get tags as a list of names
                tag_names = list(dataset.tags.values_list('name', flat=True))
                
                # Get variable count for context
                variable_count = dataset.variables.count()
                
                # Create text to embed with all relevant fields
                text_to_embed = f"""Title: {dataset.title}
                    Description: {dataset.description or ''}
                    Year: {dataset.vintage}
                    Dataset type: {dataset.dataset_path}
                    Reference period: {dataset.reference_period or ''}
                    Variables available: {variable_count}
                    Tags: {', '.join(tag_names)}"""
                
                # Truncate if text is too long
                text_to_embed = self.truncate_text(text_to_embed)
                
                batch_texts.append(text_to_embed)
                batch_ids.append(dataset.id)
            
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
                    CensusDataset.objects.filter(id=dataset_id).update(
                        embedding=embedding_bytes
                    )
                
                total_processed += len(batch)
                self.stdout.write(f"Processed {total_processed}/{total_datasets} datasets")
                
                # Add a small delay to avoid rate limits
                time.sleep(0.1)
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error generating embeddings for dataset batch: {e}"))
                # Continue with next batch
        
        self.stdout.write(self.style.SUCCESS(f"Dataset embedding generation complete! {total_processed} datasets processed."))
    
    def process_variables(self, client, batch_size, force, limit, specific_dataset=None):
        """Generate embeddings for Census variables"""
        # Get variables that need embeddings
        variables_query = CensusVariable.objects.all()
        
        # Filter by dataset if specified
        if specific_dataset:
            try:
                vintage, path = specific_dataset.split('/', 1)
                dataset = CensusDataset.objects.get(vintage=vintage, dataset_path=path)
                variables_query = variables_query.filter(dataset=dataset)
                self.stdout.write(f"Processing only variables from dataset: {vintage}/{path}")
            except (ValueError, CensusDataset.DoesNotExist):
                self.stdout.write(self.style.ERROR(f"Dataset not found: {specific_dataset}"))
                return
        
        if force:
            variables = variables_query
            count = variables.count()
            self.stdout.write(f"Generating embeddings for all Census variables (force mode): {count} variables found")
        else:
            variables = variables_query.filter(embedding__isnull=True)
            count = variables.count()
            self.stdout.write(f"Generating embeddings for unindexed Census variables: {count} variables found")
        
        # Apply limit if specified
        if limit:
            variables = variables[:limit]
            self.stdout.write(f"Limited to {limit} variables")
            
        total_variables = variables.count()
        if total_variables == 0:
            self.stdout.write("No variables to process.")
            return
            
        self.stdout.write(f"Total Census variables to process: {total_variables}")
        
        # Process in batches
        total_processed = 0
        for i in tqdm(range(0, total_variables, batch_size), desc="Processing variable batches"):
            batch = variables[i:i+batch_size]
            batch_texts = []
            batch_ids = []
            
            # Prepare batch of texts to embed
            for variable in batch:
                # Create text to embed with all relevant fields
                text_to_embed = f"""Label: {variable.label}
                    Concept: {variable.concept or ''}
                    Code: {variable.variable_name}
                    Group: {variable.group_name or ''}
                    Type: {variable.predicate_type or ''}
                    From dataset: {variable.dataset.vintage} {variable.dataset.dataset_path}"""
                
                # Truncate if text is too long
                text_to_embed = self.truncate_text(text_to_embed)
                
                batch_texts.append(text_to_embed)
                batch_ids.append(variable.id)
            
            try:
                # Generate embeddings for the batch
                response = client.embeddings.create(
                    input=batch_texts,
                    model="text-embedding-3-small"
                )
                
                # Update each variable with its embedding
                for j, embedding_data in enumerate(response.data):
                    variable_id = batch_ids[j]
                    embedding_vector = embedding_data.embedding
                    
                    # Convert to numpy array, then to bytes for storage
                    embedding_bytes = np.array(embedding_vector, dtype=np.float32).tobytes()
                    
                    # Update the variable
                    CensusVariable.objects.filter(id=variable_id).update(
                        embedding=embedding_bytes
                    )
                
                total_processed += len(batch)
                if total_processed % 1000 == 0 or total_processed == total_variables:
                    self.stdout.write(f"Processed {total_processed}/{total_variables} variables")
                
                # Add a small delay to avoid rate limits
                time.sleep(0.1)
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error generating embeddings for variable batch: {e}"))
                # Continue with next batch
        
        self.stdout.write(self.style.SUCCESS(f"Variable embedding generation complete! {total_processed} variables processed."))
    
    def clean_text(self, text):
        """Clean and normalize text"""
        if not text:
            return ""
        # Remove special characters but keep important ones
        text = re.sub(r'[^\w\s\-\.,;:#&\'"/()]', ' ', text)
        # Normalize whitespace
        return ' '.join(text.split())
    
    def truncate_text(self, text, max_chars=8000):
        """Truncate text while preserving complete sections"""
        if len(text) <= max_chars:
            return text
            
        sections = text.split('\n')
        result = []
        current_length = 0
        
        for section in sections:
            section_name = section.split(':', 1)[0] if ':' in section else ''
            # Always include essential info even if we're close to the limit
            if (current_length + len(section) + 1 > max_chars and 
                not section_name.strip() in ["Label", "Code", "Title", "Year", "Dataset type"]):
                break
            result.append(section)
            current_length += len(section) + 1
            
        return '\n'.join(result)