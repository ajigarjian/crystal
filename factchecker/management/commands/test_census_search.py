from django.core.management.base import BaseCommand
from factchecker.search.census_search import process_query, vector_search
import json
from django.core.serializers.json import DjangoJSONEncoder
import os
from datetime import datetime

class Command(BaseCommand):
    help = 'Test Census dataset search with natural language query processing'

    def add_arguments(self, parser):
        parser.add_argument('--query', type=str, help='Natural language query to search for')
        parser.add_argument('--verbose', action='store_true', help='Print verbose output')
        parser.add_argument('--use_filters', action='store_true', help='Whether to use extracted filters (year, tag, geo) (default: False)')
        parser.add_argument('--similarity', type=float, default=0.2, help='Similarity threshold (lower value = more results)')
        parser.add_argument('--max_results', type=int, default=5, help='Maximum number of results to return')
        parser.add_argument('--run_all', action='store_true', help='Run all predefined test queries and save results to file')
        parser.add_argument('--output_file', type=str, default='census_search_report.txt', help='Output file for test results')

    def handle(self, *args, **options):
        if options['run_all']:
            self.run_test_suite(options)
        else:
            self.run_single_query(options)

    def run_single_query(self, options):
        if not options['query']:
            self.stdout.write(self.style.ERROR("Error: --query is required unless --run_all is specified"))
            return
            
        query = options['query']
        verbose = options['verbose']
        use_filters = options['use_filters']
        similarity_threshold = options['similarity']
        max_results = options['max_results']
        
        self.stdout.write(self.style.SUCCESS(f"Processing query: {query}"))
        
        # Step 1: Process the query to extract structured parameters
        processed_query = process_query(query, use_llm=True)
        
        self.stdout.write(self.style.SUCCESS("Processed query parameters:"))
        self.stdout.write(json.dumps(processed_query, indent=2, cls=DjangoJSONEncoder))
        
        # Step 2: Use the processed parameters to search Census datasets
        self.stdout.write(self.style.SUCCESS("\nSearching Census datasets..."))
        
        core_query = processed_query.get('core_query', query)
        year = processed_query.get('year')
        tags = processed_query.get('tags')
        geo_level = processed_query.get('geo_level')
        location = processed_query.get('location')
        
        self.stdout.write(f"Core query: {core_query}")
        self.stdout.write(f"Year filter: {year}")
        self.stdout.write(f"Tags filter: {tags}")
        self.stdout.write(f"Geographic level: {geo_level}")
        self.stdout.write(f"Location: {location}")
        self.stdout.write(f"Using filters: {use_filters}")
        
        # Only use filters if explicitly requested
        if not use_filters:
            year = None
            tags = None
            geo_level = None
            location = None
            self.stdout.write(self.style.SUCCESS("Filters disabled, searching without filters"))
        
        results = vector_search(
            query=core_query,
            similarity_threshold=similarity_threshold,
            year=year,
            tags=tags,
            geo_level=geo_level,
            location=location,
            max_results=max_results,
            verbose=verbose,
            skip_empty_filters=True
        )
        
        # Print results
        self.stdout.write(self.style.SUCCESS(f"\nFound {len(results)} matching datasets"))
        
        if not results:
            self.stdout.write(self.style.WARNING("No results found matching your query."))
            return
            
        for i, result in enumerate(results):
            self.stdout.write("=" * 80)
            self.stdout.write(self.style.SUCCESS(f"Result {i+1}:"))
            self.stdout.write(f"Title: {result['title']}")
            self.stdout.write(f"ID: {result['id']}")
            self.stdout.write(f"Vintage: {result['vintage']}")
            self.stdout.write(f"Score: {result['score']:.4f}")
            self.stdout.write(f"Variable count: {result['variable_count']}")
            self.stdout.write(f"Path: {result['path']}")
            
            if 'geographic_levels' in result and result['geographic_levels']:
                self.stdout.write(f"Geographic levels: {', '.join(result['geographic_levels'])}")
            
            if 'description' in result and result['description']:
                desc = result['description']
                # Truncate if too long
                if len(desc) > 300:
                    desc = desc[:297] + "..."
                self.stdout.write(f"Description: {desc}")
                
            self.stdout.write("=" * 80)
        
        return results  # Return results for use in run_test_suite
        
    def run_test_suite(self, options):
        verbose = options['verbose']
        use_filters = True  # Always use filters for test suite
        similarity_threshold = options['similarity']
        max_results = options['max_results']
        output_file = options['output_file']
        
        # Define a diverse set of test queries covering different tags, geographies, years, etc.
        test_queries = [
            "Income inequality in New York City 2019",
            "Hispanic population in California counties 2020",
            "Poverty rates in rural areas 2018",
            "Educational attainment in metropolitan areas 2021",
            "Housing affordability in Chicago 2022",
            "Veterans in Texas counties",
            "Language spoken at home in Hawaii 2017",
            "Employment statistics for women in Florida 2019",
            "Commuting patterns in Seattle metropolitan area",
            "Health insurance coverage in Appalachian region 2020"
        ]
        
        # Create or open the output file
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(output_file, 'w') as f:
            f.write(f"CENSUS DATASET SEARCH TEST REPORT\n")
            f.write(f"Generated: {timestamp}\n")
            f.write(f"Configuration: similarity={similarity_threshold}, max_results={max_results}\n")
            f.write("=" * 100 + "\n\n")
            
            # Process each query and append results to the file
            for i, query in enumerate(test_queries):
                self.stdout.write(self.style.SUCCESS(f"Running test query {i+1}/{len(test_queries)}: {query}"))
                
                # Process the query and get structured parameters
                processed_query = process_query(query, use_llm=True)
                core_query = processed_query.get('core_query', query)
                year = processed_query.get('year')
                tags = processed_query.get('tags')
                geo_level = processed_query.get('geo_level')
                location = processed_query.get('location')
                
                # Search for datasets
                results = vector_search(
                    query=core_query,
                    similarity_threshold=similarity_threshold,
                    year=year,
                    tags=tags,
                    geo_level=geo_level,
                    location=location,
                    max_results=max_results,
                    verbose=verbose,
                    skip_empty_filters=True
                )
                
                # Write query and parameters to the file
                f.write(f"TEST QUERY {i+1}: {query}\n\n")
                f.write("Extracted Parameters:\n")
                f.write(f"  Core Query: {core_query}\n")
                f.write(f"  Year: {year}\n")
                f.write(f"  Tags: {tags}\n")
                f.write(f"  Geographic Level: {geo_level}\n")
                f.write(f"  Location: {location}\n\n")
                
                # Write the results
                if not results:
                    f.write(f"NO MATCHING DATASETS FOUND\n\n")
                else:
                    f.write(f"FOUND {len(results)} MATCHING DATASETS:\n\n")
                    
                    for j, result in enumerate(results):
                        f.write(f"Result {j+1}:\n")
                        f.write(f"  Title: {result['title']}\n")
                        f.write(f"  ID: {result['id']}\n")
                        f.write(f"  Vintage: {result['vintage']}\n")
                        f.write(f"  Score: {result['score']:.4f}\n")
                        f.write(f"  Variable Count: {result['variable_count']}\n")
                        
                        if 'geographic_levels' in result and result['geographic_levels']:
                            f.write(f"  Geographic Levels: {', '.join(result['geographic_levels'])}\n")
                        
                        if 'description' in result and result['description']:
                            f.write(f"  Description: {result['description']}\n")
                        
                        f.write("\n")
                
                f.write("-" * 100 + "\n\n")
                
                # Also output to console
                self.stdout.write(self.style.SUCCESS(f"Found {len(results)} datasets for query: {query}"))
            
            # Write summary at the end
            f.write("\nTEST SUMMARY:\n")
            f.write(f"Total queries tested: {len(test_queries)}\n")
            f.write(f"Report saved to: {os.path.abspath(output_file)}\n")
        
        self.stdout.write(self.style.SUCCESS(f"\nTest suite completed!"))
        self.stdout.write(self.style.SUCCESS(f"Detailed report saved to: {os.path.abspath(output_file)}")) 