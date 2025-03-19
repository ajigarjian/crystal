"""
Django management command to migrate FAISS index to Pinecone
"""

from django.core.management.base import BaseCommand
from factchecker.search.pinecone_search import migrate_faiss_to_pinecone

class Command(BaseCommand):
    help = 'Migrate FAISS index to Pinecone'

    def add_arguments(self, parser):
        parser.add_argument(
            '--faiss-dir',
            type=str,
            default='faiss_index',
            help='Directory containing FAISS index files'
        )
        parser.add_argument(
            '--api-key',
            type=str,
            help='Pinecone API key (defaults to PINECONE_API_KEY env var)'
        )
        parser.add_argument(
            '--environment',
            type=str,
            help='Pinecone environment (defaults to PINECONE_ENVIRONMENT env var)'
        )
        parser.add_argument(
            '--index-name',
            type=str,
            default='dataset-embeddings',
            help='Name for the Pinecone index'
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=100,
            help='Batch size for uploading vectors'
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting migration from FAISS to Pinecone...'))
        
        migrate_faiss_to_pinecone(
            faiss_index_dir=options['faiss_dir'],
            pinecone_api_key=options['api_key'],
            pinecone_environment=options['environment'],
            pinecone_index_name=options['index_name'],
            batch_size=options['batch_size']
        )
        
        self.stdout.write(self.style.SUCCESS('Migration complete!')) 