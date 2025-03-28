#!/usr/bin/env python3
import os
import sys
import django
import json
import datetime

# This line will add the project's root folder to sys.path
sys.path.append(
    os.path.join(os.path.dirname(__file__), "../../")
)

# Set the DJANGO_SETTINGS_MODULE environment variable
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'factchecker.settings')

# Initialize Django
django.setup()

# Import models after Django setup
from factchecker.models import DatasetResource


def query_dataset(dataset_id):
    """
    Query the database for all records matching the given dataset_id
    and return the results as a dictionary.
    
    Args:
        dataset_id: The dataset ID to search for
        
    Returns:
        A dictionary where keys are row IDs and values are the row data
    """
    results = {}
    
    try:
        # Query all records matching the dataset_id
        queryset = DatasetResource.objects.filter(dataset__dataset_id=dataset_id)
        
        print(f"Found {queryset.count()} records matching dataset_id: {dataset_id}")
        
        # Convert QuerySet to dictionary
        for record in queryset:
            # Create a dict from the model instance
            record_dict = {
                'id': record.resource_id,
                'dataset_id': record.dataset.dataset_id,
                'url': record.url,
                'name': record.name,
                'format': record.format,
                'size': record.size,
                'last_modified': record.last_modified.isoformat() if record.last_modified else None,
                'is_cached': record.is_cached,
                'cache_uri': record.cache_uri,
            }
            
            # Add to results dict with ID as key
            results[record.resource_id] = record_dict
            
    except Exception as e:
        print(f"Error querying the database: {e}")
            
    return results

def main():
    
    # Check if dataset_id was provided as command-line argument
    if len(sys.argv) != 2:
        print("Usage: python query_django.py <dataset_id>")
        sys.exit(1)
    
    dataset_id = sys.argv[1]
    results = query_dataset(dataset_id)
    
    # Print the results
    if results:
        print("\nResults:")
        for row_id, data in results.items():
            print(f"\nRecord ID: {row_id}")
            for key, value in data.items():
                if key != 'id':  # Skip printing ID again
                    print(f"  {key}: {value}")
    else:
        print(f"No records found for dataset_id: {dataset_id}")

    # Optional: Output as JSON
    # print(json.dumps(results, indent=2, default=str))

if __name__ == "__main__":
    main()