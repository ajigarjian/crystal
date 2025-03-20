import requests
import json
from django.core.management.base import BaseCommand
from django.conf import settings
from factchecker.models import CensusDataset, CensusVariable, CensusFIPSCode


class Command(BaseCommand):
    help = 'Test Census API queries using our database models'

    def add_arguments(self, parser):
        parser.add_argument(
            '--query',
            type=str,
            default='hispanic population under 14 in california',
            help='Natural language query to test'
        )
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

    def handle(self, *args, **options):
        query = options['query']
        vintage = options['vintage']
        dataset_path = options['dataset']
        
        self.stdout.write(self.style.SUCCESS(f'Testing Census API query: "{query}"'))
        
        # Step 1: Parse the query (simplified for this test)
        parsed_query = self._parse_query(query)
        self.stdout.write('Parsed query:')
        for key, value in parsed_query.items():
            self.stdout.write(f'  {key}: {value}')
        
        # Step 2: Find the dataset
        dataset = self._get_dataset(vintage, dataset_path)
        if not dataset:
            self.stdout.write(self.style.ERROR(f'Dataset not found: {vintage} {dataset_path}'))
            return
        
        # Step 3: Find relevant variables
        variables = self._find_variables(dataset, parsed_query)
        if not variables:
            self.stdout.write(self.style.ERROR('No relevant variables found'))
            return
        
        self.stdout.write('Found relevant variables:')
        for var in variables[:10]:  # Limit to 10 for display
            self.stdout.write(f'  {var.variable_name}: {var.label}')
        
        if len(variables) > 10:
            self.stdout.write(f'  ... and {len(variables) - 10} more')
        
        # Step 4: Get geography code
        geography = self._get_geography(parsed_query)
        if not geography:
            self.stdout.write(self.style.ERROR(f'Geography not found: {parsed_query["geography"]}'))
            return
        
        # Step 5: Execute API call
        self.stdout.write('\nExecuting Census API call...')
        api_key = getattr(settings, 'CENSUS_API_KEY', '')
        if not api_key:
            self.stdout.write(self.style.WARNING('No CENSUS_API_KEY found in settings. Using empty key.'))
        
        results = self._execute_api_call(dataset, variables[:5], geography, api_key)
        
        # Step 6: Display results
        self.stdout.write('\nResults:')
        self.stdout.write(json.dumps(results, indent=2))
    
    def _parse_query(self, query):
        """
        Simple parsing of the query into components
        In a real implementation, this would use an LLM
        """
        # Hardcoded parsing for our test query
        if "hispanic" in query.lower() and "under 14" in query.lower() and "california" in query.lower():
            return {
                "demographic_group": "Hispanic",
                "age_range": "under 14",
                "geography": "California",
                "geography_type": "state"
            }
        
        # Very simple parsing for other queries
        parts = {}
        
        # Extract demographic group (simplistic)
        for demo in ["hispanic", "black", "white", "asian"]:
            if demo in query.lower():
                parts["demographic_group"] = demo.title()
                break
        
        # Extract geography (simplistic)
        for state in ["california", "new york", "texas", "florida"]:
            if state in query.lower():
                parts["geography"] = state.title()
                parts["geography_type"] = "state"
                break
        
        # Add defaults if not found
        if "demographic_group" not in parts:
            parts["demographic_group"] = "Total"
        
        if "geography" not in parts:
            parts["geography"] = "United States"
            parts["geography_type"] = "us"
        
        return parts
    
    def _get_dataset(self, vintage, dataset_path):
        """Get the dataset from database"""
        try:
            return CensusDataset.objects.get(vintage=vintage, dataset_path=dataset_path)
        except CensusDataset.DoesNotExist:
            return None
    
    def _find_variables(self, dataset, parsed_query):
        """Find relevant variables based on the parsed query"""
        demographic = parsed_query.get("demographic_group", "").lower()
        age_range = parsed_query.get("age_range", "").lower()
        
        # Start with a base query
        query = CensusVariable.objects.filter(dataset=dataset)
        
        # Filter by demographic group
        if demographic == "hispanic":
            # Look for Hispanic/Latino variables
            query = query.filter(
                concept__icontains="hispanic"
            ) | query.filter(
                label__icontains="hispanic"
            )
        elif demographic == "black":
            # Look for Black/African American variables
            query = query.filter(
                concept__icontains="black"
            ) | query.filter(
                label__icontains="black"
            )
        elif demographic == "asian":
            # Look for Asian variables
            query = query.filter(
                concept__icontains="asian"
            ) | query.filter(
                label__icontains="asian"
            )
        
        # Filter by age if specified
        if "under" in age_range:
            # Extract the age number
            try:
                age = int(''.join(filter(str.isdigit, age_range)))
                
                # Find age-related variables
                query = query.filter(
                    concept__icontains="age"
                ) | query.filter(
                    label__icontains="age"
                )
                
                # Further refine to specific age groups based on common patterns
                if age <= 5:
                    query = query.filter(
                        label__icontains="under 5"
                    ) | query.filter(
                        label__icontains="0 to 4"
                    )
                elif age <= 10:
                    query = query.filter(
                        label__icontains="5 to 9"
                    ) | query.filter(
                        label__icontains="under 10"
                    )
                elif age <= 15:
                    query = query.filter(
                        label__icontains="10 to 14"
                    ) | query.filter(
                        label__icontains="under 15"
                    )
            except ValueError:
                pass
        
        return list(query.order_by('variable_name')[:50])  # Limit to 50 for testing
    
    def _get_geography(self, parsed_query):
        """Get geography code from the database"""
        geo_name = parsed_query.get("geography", "")
        geo_type = parsed_query.get("geography_type", "")
        
        # Special case for US (no FIPS needed)
        if geo_type.lower() == "us":
            return {
                "type": "us",
                "code": "1"
            }
        
        try:
            # Look up in our FIPS database
            geo = CensusFIPSCode.objects.filter(
                geo_type=geo_type.lower(),
                name__icontains=geo_name
            ).first()
            
            if geo:
                return {
                    "type": geo.geo_type,
                    "code": geo.fips_code
                }
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error finding geography: {str(e)}'))
        
        return None
    
    def _execute_api_call(self, dataset, variables, geography, api_key):
        """Execute the Census API call"""
        # Construct the API URL
        api_url = f"https://api.census.gov/data/{dataset.vintage}/{dataset.dataset_path}"
        
        # Prepare variable names for the GET parameter
        variable_names = [v.variable_name for v in variables]
        variable_param = ",".join(["NAME"] + variable_names)
        
        # Construct the geography parameter
        geo_param = f"{geography['type']}:{geography['code']}"
        
        # Make the API request
        params = {
            "get": variable_param,
            "for": geo_param,
            "key": api_key
        }
        
        self.stdout.write(f"API URL: {api_url}")
        self.stdout.write(f"Params: {params}")
        
        try:
            response = requests.get(api_url, params=params)
            response.raise_for_status()
            data = response.json()
            
            # Process the response
            if not data or len(data) < 2:
                return {"error": "No data returned"}
            
            # Extract headers and data
            headers = data[0]
            values = data[1]
            
            # Create a dictionary of results
            results = {}
            for i, header in enumerate(headers):
                if i < len(values):
                    # For variable names, include their labels
                    if header in variable_names:
                        var = next((v for v in variables if v.variable_name == header), None)
                        if var:
                            # Clean up the label
                            label = var.label.replace("Estimate!!", "").replace("!!", ", ")
                            results[label] = values[i]
                    else:
                        results[header] = values[i]
            
            return results
            
        except requests.exceptions.RequestException as e:
            return {"error": f"API request failed: {str(e)}"}
        except json.JSONDecodeError:
            return {"error": "Invalid JSON response", "response": response.text} 