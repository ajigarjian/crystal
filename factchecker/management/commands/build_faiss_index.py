"""
This module provides a Django management command to build a FAISS index from dataset embeddings.

The command:
1. Collects all dataset embeddings from the main database
2. Processes them in configurable batches to manage memory usage
3. Normalizes the vectors for accurate cosine similarity calculations
4. Builds a FAISS IndexFlatIP for fast similarity searches
5. Saves the index and dataset ID mapping to disk for later use

Usage:
    python manage.py build_faiss_index [--output OUTPUT_DIR] [--batch-size BATCH_SIZE]
"""

import numpy as np
import faiss
import os
import pickle
from django.core.management.base import BaseCommand
from factchecker.models import DatasetCatalog
from tqdm import tqdm

class Command(BaseCommand):
    help = 'Build a FAISS index from dataset embeddings'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output',
            type=str,
            default='faiss_index',
            help='Output directory for the FAISS index files'
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=10000,
            help='Batch size for processing embeddings'
        )

    def handle(self, *args, **options):
        output_dir = options['output']
        batch_size = options['batch_size']
        os.makedirs(output_dir, exist_ok=True)
        
        # Get all datasets with embeddings
        datasets = DatasetCatalog.objects.filter(indexed=True)
        total_datasets = datasets.count()
        
        if total_datasets == 0:
            self.stdout.write(self.style.ERROR("No datasets with embeddings found"))
            return
            
        self.stdout.write(f"Building FAISS index from {total_datasets} datasets")
        
        # Process in batches to avoid memory issues with large datasets
        embeddings = []
        dataset_ids = []
        dimension = None
        
        for i in tqdm(range(0, total_datasets, batch_size), desc="Loading embeddings"):
            batch = datasets[i:i+batch_size]
            
            for dataset in batch:
                if not dataset.embedding:
                    continue
                    
                # Convert binary embedding to numpy array
                embedding = np.frombuffer(dataset.embedding, dtype=np.float32)
                
                # If this is the first embedding, get its dimension
                if dimension is None:
                    dimension = embedding.shape[0]
                    self.stdout.write(f"Embedding dimension: {dimension}")
                    
                # Skip if dimensions don't match (shouldn't happen but just in case)
                if embedding.shape[0] != dimension:
                    self.stdout.write(self.style.WARNING(
                        f"Skipping dataset {dataset.dataset_id} - dimension mismatch: {embedding.shape[0]} vs {dimension}"
                    ))
                    continue
                    
                embeddings.append(embedding)
                dataset_ids.append(dataset.dataset_id)
        
        if not embeddings:
            self.stdout.write(self.style.ERROR("No valid embeddings found"))
            return
            
        # Create a matrix of all embeddings
        self.stdout.write(f"Creating embedding matrix with {len(embeddings)} embeddings")
        embeddings_matrix = np.vstack(embeddings).astype(np.float32)
        
        # Normalize vectors for cosine similarity
        self.stdout.write("Normalizing vectors for cosine similarity")
        faiss.normalize_L2(embeddings_matrix)
        
        # Build the index
        self.stdout.write(f"Building FAISS index with dimension {dimension}")
        index = faiss.IndexFlatIP(dimension)  # Inner product for cosine similarity with normalized vectors
        index.add(embeddings_matrix)
        
        # Save the index and dataset IDs
        self.stdout.write(f"Saving index to {output_dir}")
        faiss.write_index(index, os.path.join(output_dir, 'faiss.index'))
        with open(os.path.join(output_dir, 'dataset_ids.pkl'), 'wb') as f:
            pickle.dump(dataset_ids, f)
            
        self.stdout.write(self.style.SUCCESS(
            f"FAISS index built successfully with {len(dataset_ids)} entries and saved to {output_dir}"
        )) 