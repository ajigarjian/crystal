from django.core.management.base import BaseCommand
import requests
import json
import os
import time
import random
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from django.conf import settings

class Command(BaseCommand):
    help = 'Download metadata for Data.gov datasets and save as a JSON catalog'

    def add_arguments(self, parser):
        parser.add_argument(
            "--output", 
            default="data_gov_catalog.json", 
            help="Output JSON file path"
        )
        parser.add_argument(
            "--batch-size", 
            type=int, 
            default=500, 
            help="Number of datasets per request"
        )
        parser.add_argument(
            "--limit", 
            type=int, 
            help="Limit the total number of datasets (for testing)"
        )
        parser.add_argument(
            "--include-resources", 
            action="store_true", 
            help="Include resource/file information"
        )
        parser.add_argument(
            "--include-tags", 
            action="store_true", 
            help="Include dataset tags"
        )
        parser.add_argument(
            "--api-key", 
            help="Data.gov API key (will check DATA_GOV_API_KEY env var if not provided)"
        )
        parser.add_argument(
            "--resume-from", 
            type=int, 
            default=0, 
            help="Resume downloading from a specific index"
        )
        parser.add_argument(
            "--save-interval", 
            type=int, 
            default=5000, 
            help="Save progress after this many datasets"
        )

    def handle(self, *args, **options):
        try:
            api_key = self.init_api_key(options['api_key'])
            result = self.download_dataset_catalog(
                api_key=api_key,
                output_file=options['output'],
                batch_size=options['batch_size'],
                include_resources=options['include_resources'],
                include_tags=options['include_tags'],
                limit=options['limit'],
                resume_from=options['resume_from'],
                save_interval=options['save_interval']
            )
            
            if 'error' in result:
                self.stderr.write(self.style.ERROR(f"Error: {result['error']}"))
                self.stdout.write(f"To resume, run: python manage.py build_dataset_catalog --resume-from {result['last_processed_index']}")
            else:
                self.stdout.write(self.style.SUCCESS(f"Successfully downloaded catalog with {result['total_count']} datasets"))
                
        except ValueError as e:
            self.stderr.write(self.style.ERROR(f"Error: {e}"))
        except KeyboardInterrupt:
            self.stdout.write("\nProcess interrupted by user. You can resume later with --resume-from")

    def init_api_key(self, api_key: Optional[str] = None) -> str:
        """Initialize the Data.gov API key."""
        data_gov_key = api_key or settings.DATA_GOV_API_KEY or os.environ.get("DATA_GOV_API_KEY")
        
        if not data_gov_key:
            raise ValueError("Data.gov API key is required. Set DATA_GOV_API_KEY in settings.py or environment variable, or pass it directly.")
        
        return data_gov_key

    def fetch_with_retry(self, url: str, params: Dict, headers: Dict, max_retries: int = 3) -> Dict:
        """Fetch data with retry logic."""
        retries = 0
        backoff_factor = 1.5
        
        while retries <= max_retries:
            try:
                response = requests.get(url, params=params, headers=headers)
                response.raise_for_status()
                return response.json()
            except requests.exceptions.RequestException as e:
                retries += 1
                if retries > max_retries:
                    raise
                
                # Exponential backoff with jitter
                wait_time = (backoff_factor ** retries) * (0.5 + random.random())
                self.stdout.write(f"Request failed: {e}. Retrying in {wait_time:.1f} seconds...")
                time.sleep(wait_time)
        
        # This should never happen due to the raise in the except block
        raise RuntimeError("Failed to fetch data after retries")

    def save_progress(self, output_file: str, datasets: List[Dict]) -> None:
        """Save current progress to file."""
        catalog = {
            "last_updated": datetime.now().isoformat(),
            "total_count": len(datasets),
            "datasets": datasets
        }
        
        # Save to file with a temporary name first to avoid corruption
        temp_file = output_file + ".tmp"
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(catalog, f, indent=2, ensure_ascii=False)
        
        # Rename to final filename
        if os.path.exists(output_file):
            os.replace(temp_file, output_file)
        else:
            os.rename(temp_file, output_file)

    def download_dataset_catalog(
        self,
        api_key: str, 
        output_file: str = "data_gov_catalog.json", 
        batch_size: int = 500,
        include_resources: bool = False,
        include_tags: bool = True,
        limit: Optional[int] = None,
        resume_from: int = 0,
        save_interval: int = 5000
    ) -> Dict:
        """
        Download metadata for Data.gov datasets and save as a JSON catalog.
        
        Args:
            api_key: Data.gov API key
            output_file: File to save the catalog to
            batch_size: Number of datasets to retrieve in each request
            include_resources: Whether to include resource (file) information
            include_tags: Whether to include dataset tags
            limit: Optional limit on total number of datasets to fetch (for testing)
            resume_from: Index to resume downloading from (default: 0)
            save_interval: Save progress after processing this many datasets
            
        Returns:
            Dictionary with dataset information and stats
        """
        base_url = "https://catalog.data.gov/api/3"
        headers = {"Authorization": api_key}
        
        # Make output path absolute if it's not already
        if not os.path.isabs(output_file):
            output_file = os.path.join(settings.BASE_DIR, output_file)
            
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(output_file) or '.', exist_ok=True)
        
        # Load existing data if resuming and file exists
        all_datasets = []
        if resume_from > 0 and os.path.exists(output_file):
            try:
                with open(output_file, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
                    all_datasets = existing_data.get("datasets", [])
                    self.stdout.write(f"Loaded {len(all_datasets)} existing datasets from {output_file}")
            except (json.JSONDecodeError, KeyError) as e:
                self.stdout.write(self.style.WARNING(f"Could not load existing data from {output_file}: {e}"))
                resume_from = 0
        
        # Get total count first
        params = {
            "q": "",  # Empty query to match all datasets
            "rows": 1  # Just need to get the total count
        }
        
        try:
            self.stdout.write("Retrieving dataset count...")
            data = self.fetch_with_retry(f"{base_url}/action/package_search", params, headers)
            
            total_datasets = data["result"]["count"]
            
            # If limit is set, cap the total
            if limit and limit < total_datasets:
                total_datasets = limit
                
            self.stdout.write(f"Found {total_datasets} total datasets" + 
                  (f" (limited to {limit})" if limit else ""))
            
            if resume_from > 0:
                self.stdout.write(f"Resuming from dataset {resume_from}")
            
            start = resume_from
            last_save = start
            
            while start < total_datasets:
                end_point = min(start + batch_size, total_datasets)
                self.stdout.write(f"Downloading metadata for datasets {start+1} to {end_point} of {total_datasets}...")
                
                params = {
                    "q": "",
                    "rows": min(batch_size, total_datasets - start),
                    "start": start
                }
                
                batch_data = self.fetch_with_retry(f"{base_url}/action/package_search", params, headers)
                
                # Extract simplified dataset info
                for dataset in batch_data["result"]["results"]:
                    simplified = {
                        "id": dataset.get("id"),
                        "title": dataset.get("title"),
                        "description": dataset.get("notes", "")
                    }
                    
                    # Add organization if available
                    if dataset.get("organization"):
                        simplified["organization"] = {
                            "name": dataset.get("organization", {}).get("name"),
                            "title": dataset.get("organization", {}).get("title"),
                            "description": dataset.get("organization", {}).get("description", "")
                        }
                    
                    # Add tags if requested
                    if include_tags and dataset.get("tags"):
                        simplified["tags"] = [tag.get("name") for tag in dataset.get("tags", [])]
                    
                    # Add resource info if requested
                    if include_resources and dataset.get("resources"):
                        simplified["resources"] = [
                            {
                                "id": r.get("id"),
                                "name": r.get("name"),
                                "format": r.get("format", "").lower(),
                                "size": r.get("size")
                            }
                            for r in dataset.get("resources", [])
                        ]
                    
                    all_datasets.append(simplified)
                
                # Move to next batch
                start += batch_size
                
                # Save progress periodically
                if start - last_save >= save_interval:
                    self.save_progress(output_file, all_datasets)
                    last_save = start
                    self.stdout.write(f"Progress saved: {len(all_datasets)} datasets processed so far")
                
                # Add a small delay to avoid rate limits
                time.sleep(1.0)
            
            # Final save
            self.save_progress(output_file, all_datasets)
            self.stdout.write(f"Catalog with {len(all_datasets)} datasets saved to {output_file}")
            self.stdout.write(f"File size: {os.path.getsize(output_file) / (1024*1024):.2f} MB")
            
            return {
                "last_updated": datetime.now().isoformat(),
                "total_count": len(all_datasets),
                "datasets": all_datasets
            }
            
        except requests.exceptions.RequestException as e:
            self.stderr.write(self.style.ERROR(f"Error downloading dataset catalog: {e}"))
            # Save what we have so far
            if all_datasets:
                self.save_progress(output_file, all_datasets)
                self.stdout.write(f"Partial catalog with {len(all_datasets)} datasets saved to {output_file}")
            return {"error": str(e), "last_processed_index": start} 