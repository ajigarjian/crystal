import requests
import json
import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone
from factchecker.models import (
    CensusDataset, CensusVariable, CensusGroup, 
    CensusGeography, CensusTag, CensusFIPSCode
)


class Command(BaseCommand):
    help = 'Import Census API metadata for 2020 ACS 5-year estimates'

    def add_arguments(self, parser):
        parser.add_argument(
            '--vintage',
            type=int,
            default=2020,
            help='Census data vintage year (default: 2020)'
        )
        parser.add_argument(
            '--dataset',
            type=str,
            default='acs/acs5',
            help='Dataset path (default: acs/acs5)'
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing data before importing'
        )

    def handle(self, *args, **options):
        vintage = options['vintage']
        dataset_path = options['dataset']
        clear_data = options.get('clear', False)
        
        self.stdout.write(self.style.SUCCESS(f'Starting import of Census API metadata for {vintage} {dataset_path}'))
        
        # Clear existing data if requested
        if clear_data:
            self._clear_existing_data(vintage, dataset_path)
        
        # Step 1: Fetch and store dataset metadata
        self.stdout.write('1. Importing dataset metadata...')
        dataset = self._import_dataset_metadata(vintage, dataset_path)
        
        # Step 2: Fetch and store geography metadata
        self.stdout.write('2. Importing geography metadata...')
        self._import_geography_metadata(dataset)
        
        # Step 3: Fetch and store variables metadata
        self.stdout.write('3. Importing variables metadata...')
        self._import_variables_metadata(dataset)
        
        # Step 4: Fetch and store groups metadata
        self.stdout.write('4. Importing groups metadata...')
        self._import_groups_metadata(dataset)
        
        # Step 5: Fetch and store tags metadata
        self.stdout.write('5. Importing tags metadata...')
        self._import_tags_metadata(dataset)
        
        # Step 6: Update stats after import
        self._print_import_stats(dataset)
        
        self.stdout.write(self.style.SUCCESS('Census API metadata import completed!'))
    
    def _clear_existing_data(self, vintage, dataset_path):
        """Clear existing data for this dataset"""
        try:
            dataset = CensusDataset.objects.get(vintage=vintage, dataset_path=dataset_path)
            
            # Delete related objects
            CensusVariable.objects.filter(dataset=dataset).delete()
            CensusGroup.objects.filter(dataset=dataset).delete()
            CensusGeography.objects.filter(dataset=dataset).delete()
            
            # Remove many-to-many relationships with tags
            dataset.tags.clear()
            
            # Delete the dataset itself
            dataset.delete()
            
            self.stdout.write(self.style.SUCCESS(f'Cleared existing data for {vintage} {dataset_path}'))
        except CensusDataset.DoesNotExist:
            self.stdout.write(f'No existing data found for {vintage} {dataset_path}')
    
    def _import_dataset_metadata(self, vintage, dataset_path):
        """Import dataset metadata"""
        url = f"https://api.census.gov/data/{vintage}/{dataset_path}.json"
        
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            
            # Get the dataset info from the response
            dataset_info = None
            for dataset_entry in data.get('dataset', []):
                # Find the matching dataset in the response
                if (
                    dataset_entry.get('c_vintage') == vintage and
                    '/'.join(dataset_entry.get('c_dataset', [])) == dataset_path
                ):
                    dataset_info = dataset_entry
                    break
            
            if not dataset_info:
                self.stdout.write(self.style.ERROR(f'Dataset info not found for {vintage} {dataset_path}'))
                return None
            
            # Extract metadata
            title = dataset_info.get('title', f'{vintage} {dataset_path}')
            description = dataset_info.get('description', '')
            is_aggregate = dataset_info.get('c_isAggregate', False)
            is_microdata = dataset_info.get('c_isMicrodata', False)
            
            # Parse modified date if available
            modified_date = None
            if 'modified' in dataset_info:
                try:
                    modified_date = datetime.datetime.strptime(
                        dataset_info['modified'].split()[0], '%Y-%m-%d'
                    )
                except (ValueError, IndexError):
                    pass
            
            # Get API endpoint
            api_endpoint = None
            for dist in dataset_info.get('distribution', []):
                if dist.get('format') == 'API':
                    api_endpoint = dist.get('accessURL', '')
                    break
            
            # Create or update dataset
            dataset, created = CensusDataset.objects.update_or_create(
                vintage=vintage,
                dataset_path=dataset_path,
                defaults={
                    'title': title,
                    'description': description,
                    'is_aggregate': is_aggregate,
                    'is_microdata': is_microdata,
                    'reference_period': dataset_info.get('temporal', ''),
                    'modified_date': modified_date,
                    'api_endpoint': api_endpoint or f"https://api.census.gov/data/{vintage}/{dataset_path}"
                }
            )
            
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created dataset {vintage} {dataset_path}'))
            else:
                self.stdout.write(self.style.SUCCESS(f'Updated dataset {vintage} {dataset_path}'))
            
            return dataset
        
        except requests.exceptions.RequestException as e:
            self.stdout.write(self.style.ERROR(f'Error fetching dataset metadata: {str(e)}'))
            return None
    
    def _import_geography_metadata(self, dataset):
        """Import geography metadata for the dataset"""
        if not dataset:
            return
        
        url = f"https://api.census.gov/data/{dataset.vintage}/{dataset.dataset_path}/geography.json"
        
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            
            # Process each geography
            for geo in data.get('fips', []):
                name = geo.get('name', '')
                geo_level_display = geo.get('geoLevelDisplay', '')
                
                # Parse reference date if available
                reference_date = None
                if 'referenceDate' in geo:
                    try:
                        reference_date = datetime.datetime.strptime(
                            geo['referenceDate'], '%Y-%m-%d'
                        ).date()
                    except ValueError:
                        pass
                
                # Create or update geography
                geography, created = CensusGeography.objects.update_or_create(
                    dataset=dataset,
                    name=name,
                    defaults={
                        'geo_level_display': geo_level_display,
                        'reference_date': reference_date,
                    }
                )
                
                # Set requires and wildcard properties
                geography.requires = geo.get('requires', [])
                geography.wildcard = geo.get('wildcard', [])
                geography.save()
                
                action = 'Created' if created else 'Updated'
                self.stdout.write(f'  {action} geography: {name}')
            
            self.stdout.write(self.style.SUCCESS(f'Imported {data.get("fips", []).__len__()} geographies'))
        
        except requests.exceptions.RequestException as e:
            self.stdout.write(self.style.ERROR(f'Error fetching geography metadata: {str(e)}'))
    
    def _import_variables_metadata(self, dataset):
        """Import variables metadata for the dataset"""
        if not dataset:
            return
        
        url = f"https://api.census.gov/data/{dataset.vintage}/{dataset.dataset_path}/variables.json"
        
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            
            # Process variables in batches for efficiency
            variables_to_create = []
            count = 0
            batch_size = 500
            
            for var_name, var_info in data.get('variables', {}).items():
                # Skip non-data variables (like NAME, GEO_ID)
                if var_name in ['NAME', 'GEO_ID', 'for', 'in']:
                    continue
                
                # Create variable object
                variables_to_create.append(
                    CensusVariable(
                        dataset=dataset,
                        variable_name=var_name,
                        label=var_info.get('label', ''),
                        concept=var_info.get('concept', ''),
                        group_name=var_info.get('group', ''),
                        predicate_type=var_info.get('predicateType', '')
                    )
                )
                
                count += 1
                
                # Insert in batches
                if len(variables_to_create) >= batch_size:
                    CensusVariable.objects.bulk_create(
                        variables_to_create, 
                        ignore_conflicts=True
                    )
                    self.stdout.write(f'  Imported {count} variables...')
                    variables_to_create = []
            
            # Insert any remaining variables
            if variables_to_create:
                CensusVariable.objects.bulk_create(
                    variables_to_create,
                    ignore_conflicts=True
                )
            
            self.stdout.write(self.style.SUCCESS(f'Imported {count} variables'))
        
        except requests.exceptions.RequestException as e:
            self.stdout.write(self.style.ERROR(f'Error fetching variables metadata: {str(e)}'))
    
    def _import_groups_metadata(self, dataset):
        """Import groups metadata for the dataset"""
        if not dataset:
            return
        
        url = f"https://api.census.gov/data/{dataset.vintage}/{dataset.dataset_path}/groups.json"
        
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            
            # Process each group
            for group_name, group_info in data.get('groups', {}).items():
                # Create or update group
                group, created = CensusGroup.objects.update_or_create(
                    dataset=dataset,
                    group_name=group_name,
                    defaults={
                        'title': group_info.get('name', ''),
                        'description': group_info.get('description', ''),
                        'universe': group_info.get('universe', '')
                    }
                )
                
                action = 'Created' if created else 'Updated'
                self.stdout.write(f'  {action} group: {group_name}')
            
            self.stdout.write(self.style.SUCCESS(f'Imported {data.get("groups", {}).__len__()} groups'))
        
        except requests.exceptions.RequestException as e:
            self.stdout.write(self.style.ERROR(f'Error fetching groups metadata: {str(e)}'))
    
    def _import_tags_metadata(self, dataset):
        """Import tags metadata for the dataset"""
        if not dataset:
            return
        
        url = f"https://api.census.gov/data/{dataset.vintage}/{dataset.dataset_path}/tags.json"
        
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            
            # Process each tag
            for tag_name in data.get('tags', []):
                # Create tag if it doesn't exist
                tag, created = CensusTag.objects.get_or_create(name=tag_name)
                
                # Associate tag with dataset
                dataset.tags.add(tag)
                
                if created:
                    self.stdout.write(f'  Created tag: {tag_name}')
            
            self.stdout.write(self.style.SUCCESS(f'Imported {data.get("tags", []).__len__()} tags'))
        
        except requests.exceptions.RequestException as e:
            self.stdout.write(self.style.ERROR(f'Error fetching tags metadata: {str(e)}'))
    
    def _print_import_stats(self, dataset):
        """Print statistics about the imported data"""
        if not dataset:
            return
        
        var_count = CensusVariable.objects.filter(dataset=dataset).count()
        group_count = CensusGroup.objects.filter(dataset=dataset).count()
        geo_count = CensusGeography.objects.filter(dataset=dataset).count()
        tag_count = dataset.tags.count()
        
        self.stdout.write(self.style.SUCCESS('\nImport Statistics:'))
        self.stdout.write(f'  Dataset: {dataset.vintage} {dataset.title}')
        self.stdout.write(f'  Variables: {var_count}')
        self.stdout.write(f'  Groups: {group_count}')
        self.stdout.write(f'  Geographies: {geo_count}')
        self.stdout.write(f'  Tags: {tag_count}') 