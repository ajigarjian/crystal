"""
Vector search implementation for Census datasets.
Includes natural language query processing capabilities.
"""

import numpy as np
import os
import re
import json
from django.db.models import Q
from factchecker.models import DatasetCatalog, CensusDataset, CensusVariable, CensusGeography, CensusFIPSCode
from factchecker.search.search_utils import get_usable_resources
from typing import Dict, List, Union, Optional
from factchecker.utils.openai_client import create_embeddings, chat_completion, get_cached_openai_client
from datetime import datetime

###########################################
# QUERY PROCESSOR
###########################################

class QueryProcessor:
    """
    Processes natural language queries to extract structured parameters.
    Uses a combination of regex patterns and LLM processing.
    """
    
    def __init__(self):
        """Initialize the query processor"""
        # Initialize regex patterns
        self._init_patterns()
        
    def _init_patterns(self):
        """Initialize regex patterns for basic extraction"""
        # Year patterns
        self.year_patterns = [
            r'\b(in|for|from|during|year|data from)\s+(\d{4})\b',
            r'\b(\d{4})\s+(data|census|survey|statistics)\b',
            r'\byear[=:]?\s*(\d{4})\b',
            r'\b(\d{4})$',  # Year at the end of the query
            r'\b(\d{4})\b',  # Any 4-digit number that could be a year
        ]
        
        # Common census tags - using the same structure as VectorSearcher
        self.conceptual_tag_keywords = {
            'demographics': ['demographic', 'demography', 'population', 'people', 'race', 'ethnic', 'ethnicity'],
            'housing': ['housing', 'homes', 'residential', 'households', 'homeowners', 'house', 'apartment'],
            'income': ['income', 'earnings', 'wages', 'salary', 'monetary', 'financial', 'money'],
            'education': ['education', 'school', 'college', 'university', 'degree', 'educational', 'student'],
            'employment': ['jobs', 'employment', 'occupation', 'career', 'work', 'labor', 'workforce', 'workers'],
            'commuting': ['commute', 'transportation', 'travel', 'journey to work', 'transit'],
            'health': ['health', 'healthcare', 'medical', 'insurance', 'disability', 'hospital'],
            'poverty': ['poverty', 'poor', 'low-income', 'impoverished'],
            'language': ['language', 'speak', 'speaking', 'linguistic', 'bilingual'],
            'veterans': ['veteran', 'military', 'armed forces', 'service member'],
            'immigration': ['immigration', 'immigrant', 'foreign-born', 'naturalization', 'citizenship'],
            'computer': ['computer', 'internet', 'digital', 'technology', 'broadband'],
        }
    
    def _extract_year_with_regex(self, query: str) -> Optional[int]:
        """Extract year using regex patterns"""
        for pattern in self.year_patterns:
            matches = re.search(pattern, query, re.IGNORECASE)
            if matches:
                # Get the captured year group - it's either group 1 or 2
                year_str = matches.group(2) if len(matches.groups()) > 1 else matches.group(1)
                try:
                    year = int(year_str)
                    # Validate that it's a reasonable year
                    current_year = datetime.now().year
                    if 1790 <= year <= current_year:
                        return year
                except ValueError:
                    continue
        return None
    
    def _extract_tags_with_keywords(self, query: str) -> List[str]:
        """Extract tags using keyword matching"""
        found_tags = []
        query_lower = query.lower()
        
        for tag, keywords in self.conceptual_tag_keywords.items():
            for keyword in keywords:
                if re.search(r'\b' + re.escape(keyword) + r'\b', query_lower):
                    found_tags.append(tag)
                    break  # Once we've matched a tag, no need to check other keywords
        
        return found_tags
    
    def process_query(self, query: str, use_llm: bool = True) -> Dict:
        """
        Process a natural language query to extract structured parameters
    
    Args:
            query (str): Natural language query like "Hispanic population data from 2020"
            use_llm (bool): Whether to use the LLM for more complex extraction
            
        Returns:
            dict: Structured parameters extracted from the query
        """
        # Initialize result with the original query
        result = {
            "original_query": query,
            "core_query": query,  # Will be updated by LLM if used
            "year": None,
            "tags": [],
            "geo_level": None,
            "location": None,  # New field for specific geographic location
            "filters": {}
        }
        
        # Try regex for basic extraction
        result["year"] = self._extract_year_with_regex(query)
        result["tags"] = self._extract_tags_with_keywords(query)
        
        # Use LLM for more advanced processing if enabled
        if use_llm:
            llm_result = self._process_with_llm(query)
            if llm_result:
                # Update with LLM results, keeping regex results as fallback
                result["core_query"] = llm_result.get("core_query") or result["core_query"]
                result["year"] = llm_result.get("year") or result["year"]
                result["geo_level"] = llm_result.get("geo_level")
                result["location"] = llm_result.get("location")  # Add the specific location
                
                # Merge tags, removing duplicates
                llm_tags = llm_result.get("tags", [])
                if llm_tags:
                    result["tags"] = list(set(result["tags"] + llm_tags))
                
                # Add any extracted filters
                result["filters"] = llm_result.get("filters", {})
        
        return result
    
    def _process_with_llm(self, query: str) -> Optional[Dict]:
        """Process query using the OpenAI LLM"""
        try:
            # Use triple quotes and raw string to avoid issues with braces and formatting
            prompt = r"""
Your task is to extract structured information from a natural language query about census or demographic data.

Query: "{0}"

Extract the following components and return them in JSON format:
1. core_query: The essential search terms, removing any temporal or filtering specifications
2. year: Extract a specific year if mentioned (as integer, or null)
3. tags: Identify relevant census categories (e.g., demographics, housing, income, education, employment, etc.)
4. geo_level: Extract geographic level if specified (e.g., national, state, county, city, tract, block, zip)
   - Be precise about distinguishing between a location (e.g., "California") and a geographic level (e.g., "state")
   - If query mentions a specific location but not a level, infer the appropriate level (e.g., "California" implies state-level)
   - If multiple levels mentioned (e.g., "counties in California"), choose the most granular one (e.g., "county")
   - Common mappings: cities→city, towns→city, counties→county, states→state, ZIP codes→zip
5. location: Extract the specific geographic location mentioned (e.g., "California", "New York City", "Miami-Dade County")
   - Format consistently: states as full names, counties with "County" suffix if mentioned
   - If no specific location is mentioned, set to null
6. filters: Extract any demographic filters as key-value pairs (e.g., {{"age": "18-24", "race": "Hispanic"}})

Format your response as valid JSON with these exact keys. If any component is not mentioned, set it to null.
Respond with ONLY the JSON object, nothing else.
""".format(query)
            
            system_message = "You are a data analysis assistant that extracts structured information from queries about census and demographic data."
            response_format = {"type": "json_object"}
            
            content = chat_completion(
                prompt=prompt,
                system_message=system_message,
                response_format=response_format,
                model_name="gpt-3.5-turbo"
            )
            
            # Parse the JSON
            parsed = json.loads(content)
            return parsed
            
        except Exception as e:
            print(f"Error processing query with LLM: {e}")
            return None

# Simple function interface for query processing
def process_query(query: str, use_llm: bool = True) -> Dict:
    """
    Process a natural language query to extract structured parameters
    """
    processor = QueryProcessor()
    return processor.process_query(query, use_llm)

###########################################
# UNIFIED VECTOR SEARCHER
###########################################

class VectorSearcher:
    """
    Vector search service for Census datasets
    """
    
    def __init__(self):
        """Initialize the vector searcher"""
        self.embedding_model = "text-embedding-3-small"
        self.max_results = 5
        
        # Conceptual tag keywords for initial extraction
        self.conceptual_tag_keywords = {
            'demographics': ['demographic', 'demography', 'population', 'people', 'race', 'ethnic', 'ethnicity'],
            'housing': ['housing', 'homes', 'residential', 'households', 'homeowners', 'house', 'apartment'],
            'income': ['income', 'earnings', 'wages', 'salary', 'monetary', 'financial', 'money'],
            'education': ['education', 'school', 'college', 'university', 'degree', 'educational', 'student'],
            'employment': ['jobs', 'employment', 'occupation', 'career', 'work', 'labor', 'workforce', 'workers'],
            'commuting': ['commute', 'transportation', 'travel', 'journey to work', 'transit'],
            'health': ['health', 'healthcare', 'medical', 'insurance', 'disability', 'hospital'],
            'poverty': ['poverty', 'poor', 'low-income', 'impoverished'],
            'language': ['language', 'speak', 'speaking', 'linguistic', 'bilingual'],
            'veterans': ['veteran', 'military', 'armed forces', 'service member'],
            'immigration': ['immigration', 'immigrant', 'foreign-born', 'naturalization', 'citizenship'],
            'computer': ['computer', 'internet', 'digital', 'technology', 'broadband'],
        }
    
    def _get_available_tags(self, year=None):
        """
        Get available tags in the database, optionally filtered by year
        """
        from factchecker.models import CensusTag, CensusDataset
        from django.db.models import Count
        
        # Get all tags from the database
        if year:
            # Get tags that are used by datasets from the specified year
            available_tags = CensusTag.objects.filter(
                datasets__vintage=year
            ).annotate(
                dataset_count=Count('datasets')
            ).filter(
                dataset_count__gt=0
            ).values_list('name', flat=True)
        else:
            # Get all tags
            available_tags = CensusTag.objects.all().values_list('name', flat=True)
        
        return list(available_tags)
    
    def _generate_tag_mapping(self, year=None, verbose=False):
        """
        Generate mapping from conceptual tags to actual database tags
        based on available tags in the database for the specified year
        """
        available_tags = self._get_available_tags(year)
        
        if verbose:
            print(f"Available tags in database{' for year ' + str(year) if year else ''}: {available_tags}")
        
        # Map conceptual tags to available db tags
        tag_mapping = {}
        
        # Helper function to find matching tags
        def find_matching_tags(keywords):
            matched = []
            for tag in available_tags:
                # Check if the tag itself is in the keywords
                if tag.lower() in keywords:
                    matched.append(tag)
                    continue
                    
                # Check if any keyword is contained in the tag
                for keyword in keywords:
                    if keyword.lower() in tag.lower():
                        matched.append(tag)
                        break
            return matched
        
        # Generate mappings for each conceptual tag
        for concept, keywords in self.conceptual_tag_keywords.items():
            matched_tags = find_matching_tags(keywords)
            if matched_tags:
                tag_mapping[concept] = matched_tags
                # if verbose:
                    # print(f"Mapped conceptual tag '{concept}' to database tags: {matched_tags}")
        
        # if verbose:
            # print(f"Final tag mapping: {tag_mapping}")
            
        return tag_mapping
    
    def search(self, query: str, 
              similarity_threshold: float = 0.5,
              year: Optional[int] = None, 
              tags: Optional[List[str]] = None,
              geo_level: Optional[str] = None,
              location: Optional[str] = None,
              max_results: Optional[int] = None,
              verbose: bool = False) -> List[Dict]:
        """
        Search for Census datasets matching the query
        
        Args:
            query (str): Natural language query like "Hispanic population data"
            similarity_threshold (float): Minimum similarity score threshold
            year (int, optional): Filter Census results by specific year/vintage
            tags (list, optional): Filter Census results by specific tags
            geo_level (str, optional): Filter by geographic level (e.g., "state", "county")
            location (str, optional): Filter by specific geographic location
            max_results (int, optional): Maximum number of results to return
            verbose (bool): Whether to print detailed logging information
            
        Returns:
            list: Matching datasets with relevance scores
        """
        if max_results:
            self.max_results = max_results
            
        return self._census_search(query, year, tags, similarity_threshold, geo_level, location, verbose)
    
    def _get_embedding(self, text):
        """Get embedding vector for text using custom client"""
        try:
            return create_embeddings(text)
        except Exception as e:
            print(f"Error getting embedding: {e}")
            return None
    
    def _cosine_similarity(self, vec1, vec2):
        """Calculate cosine similarity between two vectors"""
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        return dot_product / (norm1 * norm2)
    
    def _apply_recency_boost(self, results, threshold=0.05):
        """Boost recent datasets when scores are close"""
        if not results:
            return results
            
        # Group results with similar scores
        groups = []
        current_group = [results[0]]
        
        for i in range(1, len(results)):
            prev_score = results[i-1]['score']
            curr_score = results[i]['score']
            
            if abs(prev_score - curr_score) <= threshold:
                current_group.append(results[i])
            else:
                groups.append(current_group)
                current_group = [results[i]]
        
        if current_group:
            groups.append(current_group)
        
        # Sort each group by recency (using vintage)
        sorted_results = []
        for group in groups:
            sorted_group = sorted(group, key=lambda x: x['vintage'], reverse=True)
            sorted_results.extend(sorted_group)
        
        return sorted_results
    
    def _census_search(self, query, year=None, tags=None, similarity_threshold=0.5, geo_level=None, location=None, verbose=False):
        """Search Census datasets"""
        # Process query to extract geographic info if not already done
        if verbose:
            print(f"Beginning search with query: {query}")
            print(f"Filters - Year: {year}, Tags: {tags}, Geo_level: {geo_level}, Location: {location}")
            
        # Start with a base queryset - all datasets with embeddings
        queryset = CensusDataset.objects.filter(embedding__isnull=False)
        original_count = queryset.count()
        if verbose:
            print(f"Starting with {original_count} datasets with embeddings")
        
        # Step 1: Filter by year if provided
        if year:
            queryset = queryset.filter(vintage=year)
            if verbose:
                print(f"After year filter: {queryset.count()} datasets")
                
        # Step 2: Filter by geography level if provided
        if geo_level:
            if geo_level == 'national':
                # No need to filter further
                pass
            else:
                # Get datasets that support this geography level
                if verbose:
                    print(f"Filtering for geography level: {geo_level}")
                
                # Map common geo levels to Census API geography names
                geo_mapping = {
                    'state': 'state',
                    'county': 'county',
                    'city': 'place',
                    'tract': 'tract',
                    'block': 'block',
                    'zip': 'zcta',
                    'zipcode': 'zcta',
                    'congressional district': 'congressional district',
                    'school district': 'school district',
                }
                
                # Normalize the geo level name using mapping
                normalized_geo = geo_mapping.get(geo_level.lower(), geo_level.lower())
                
                # Find datasets that support this geography
                geo_datasets = CensusGeography.objects.filter(
                    name__icontains=normalized_geo
                ).values_list('dataset_id', flat=True)
                
                if geo_datasets:
                    queryset = queryset.filter(id__in=geo_datasets)
                    if verbose:
                        print(f"After geography filter: {queryset.count()} datasets")
                else:
                    if verbose:
                        print(f"No datasets found supporting geography level: {geo_level}")
        
        # Step 3: Filter by location if provided
        if location:
            if verbose:
                print(f"Filtering for location: {location}")
            
            # Try to find the location in our FIPS codes database
            try:
                # First check if it's a state
                fips_location = CensusFIPSCode.objects.filter(
                    name__icontains=location
                ).first()
                
                if fips_location:
                    if verbose:
                        print(f"Found location in FIPS database: {fips_location.name} ({fips_location.geo_type})")
                    
                    # If the geo_level is 'county' and location is a state, we want datasets that support county-level data
                    # and contain data for that state's counties
                    if geo_level == 'county' and fips_location.geo_type == 'state':
                        # We've already filtered for county-level datasets above, so no additional filtering needed
                        if verbose:
                            print(f"Looking for county-level data in {fips_location.name}")
                    
                    # Otherwise, we'll just note this for information
                    if verbose:
                        print(f"Location filtering is informational only - Census datasets typically contain data for all locations")
                else:
                    if verbose:
                        print(f"Location '{location}' not found in FIPS database, treating as informational")
                        
                # Census datasets typically don't mention specific locations in their metadata
                # They contain data for all locations at a given geographic level
                # So location filtering is purely optional and informational
                location_filtered = queryset.filter(
                    Q(title__icontains=location) | 
                    Q(description__icontains=location)
                )
                
                if location_filtered.count() > 0:
                    if verbose:
                        print(f"Found {location_filtered.count()} datasets mentioning '{location}' in metadata")
                    queryset = location_filtered
                else:
                    if verbose:
                        print(f"No datasets found mentioning '{location}' in metadata, but this is normal.")
                        print(f"Census datasets typically cover all areas and don't mention specific locations in metadata.")
                        
            except Exception as e:
                if verbose:
                    print(f"Error checking location in FIPS database: {e}")
                    print(f"Will treat location filtering as informational only")
        
        # Step 4: Filter by tags if provided
        if tags:
            # Generate tag mapping once
            tag_mapping = self._generate_tag_mapping(year, verbose)
            
            # Build query for mapped tags
            tag_query = Q()
            
            for tag in tags:
                if tag in tag_mapping:
                    # If it's a conceptual tag, map to actual database tags
                    mapped_tags = tag_mapping[tag]
                    for mapped_tag in mapped_tags:
                        tag_query |= Q(tags__name=mapped_tag)
                else:
                    # If it's already a database tag, use it directly
                    tag_query |= Q(tags__name=tag)
            
            if tag_query:
                # Get all dataset IDs that match our tag query
                datasets_with_matching_tags = queryset.filter(tag_query).distinct().values_list('id', flat=True)
                
                # Get all dataset IDs that have no tags
                datasets_with_no_tags = queryset.filter(~Q(tags__isnull=False)).values_list('id', flat=True)
                
                # Combine the IDs and filter the original queryset
                all_dataset_ids = list(datasets_with_matching_tags) + list(datasets_with_no_tags)
                queryset = queryset.filter(id__in=all_dataset_ids)
                
                if verbose:
                    print(f"After tag filter: {queryset.count()} datasets")
        
        # Step 5: Apply similarity search on filtered datasets
        # Get datasets and their embeddings
        datasets = list(queryset)
        if not datasets:
            if verbose:
                print("No datasets found after filtering, falling back to keyword search")
            return self._census_fallback_keyword_search(query, year, tags, geo_level, location, verbose)
            
        # Get embedding for the core query
        query_embedding = self._get_embedding(query)
        
        if not query_embedding:
            if verbose:
                print("Could not generate embedding for query, falling back to keyword search")
            return self._census_fallback_keyword_search(query, year, tags, geo_level, location, verbose)
            
        # Calculate similarity scores
        results = []
        for dataset in datasets:
            # Convert binary embedding back to numpy array
            dataset_embedding = np.frombuffer(dataset.embedding, dtype=np.float32)
            
            # Calculate cosine similarity
            similarity = self._cosine_similarity(query_embedding, dataset_embedding)
            
            # Get available geographies for this dataset
            geo_levels = list(dataset.geographies.all().values_list('name', flat=True))
            
            results.append({
                'dataset': dataset,
                'score': similarity,
                'vintage': dataset.vintage,
                'title': dataset.title,
                'path': dataset.dataset_path,
                'variable_count': dataset.variables.count(),
                'id': dataset.id,
                'description': dataset.description or '',
                'geographic_levels': geo_levels,
                'search_source': 'census'
            })
        
        # Filter by threshold
        results = [r for r in results if r['score'] >= similarity_threshold]
        
        if verbose:
            print(f"After similarity threshold filter: {len(results)} datasets")
        
        # Sort by similarity score (descending)
        results = sorted(results, key=lambda x: x['score'], reverse=True)
        
        # Apply recency boost for similarly scored datasets
        results = self._apply_recency_boost(results)
        
        # Limit results
        return results[:self.max_results]
    
    def _census_fallback_keyword_search(self, query, year=None, tags=None, geo_level=None, location=None, verbose=False):
        """Fallback to keyword search if embedding search fails for Census data"""
        if verbose:
            print("Using fallback keyword search")
            print(f"Filters - Year: {year}, Tags: {tags}, Geo_level: {geo_level}, Location: {location}")
            
        # Start with all datasets
        queryset = CensusDataset.objects.all()
        if verbose:
            print(f"Starting with {queryset.count()} total datasets")
        
        # Step 1: Filter by year if provided
        if year:
            queryset = queryset.filter(vintage=year)
            if verbose:
                print(f"After year filter: {queryset.count()} datasets")
                
        # Step 2: Filter by geography level if provided
        if geo_level:
            if geo_level == 'national':
                # No need to filter further
                pass
            else:
                # Get datasets that support this geography level
                if verbose:
                    print(f"Filtering for geography level: {geo_level}")
                
                # Map common geo levels to Census API geography names
                geo_mapping = {
                    'state': 'state',
                    'county': 'county',
                    'city': 'place',
                    'tract': 'tract',
                    'block': 'block',
                    'zip': 'zcta',
                    'zipcode': 'zcta',
                    'congressional district': 'congressional district',
                    'school district': 'school district',
                }
                
                # Normalize the geo level name using mapping
                normalized_geo = geo_mapping.get(geo_level.lower(), geo_level.lower())
                
                # Find datasets that support this geography
                geo_datasets = CensusGeography.objects.filter(
                    name__icontains=normalized_geo
                ).values_list('dataset_id', flat=True)
                
                if geo_datasets:
                    queryset = queryset.filter(id__in=geo_datasets)
                    if verbose:
                        print(f"After geography filter: {queryset.count()} datasets")
                else:
                    if verbose:
                        print(f"No datasets found supporting geography level: {geo_level}")
                        
        # Step 3: Filter by location if provided
        if location:
            if verbose:
                print(f"Filtering for location: {location}")
            
            # Census datasets typically don't mention specific locations in their metadata
            # They contain data for all locations at a given geographic level
            # So location filtering is purely optional and should never eliminate all results
            location_filtered = queryset.filter(
                Q(title__icontains=location) | 
                Q(description__icontains=location)
            )
            
            if location_filtered.count() > 0:
                queryset = location_filtered
                if verbose:
                    print(f"After location filter: {queryset.count()} datasets")
            else:
                if verbose:
                    print(f"No datasets found with location '{location}' in metadata. Skipping location filter.")
                    print(f"This is normal for Census datasets which typically don't mention specific locations.")
        
        # Step 4: Map conceptual tags to actual database tags
        if tags:
            # Generate tag mapping once
            tag_mapping = self._generate_tag_mapping(year, verbose)
            
            # Build query for mapped tags
            tag_query = Q()
            
            for tag in tags:
                if tag in tag_mapping:
                    # If it's a conceptual tag, map to actual database tags
                    mapped_tags = tag_mapping[tag]
                    for mapped_tag in mapped_tags:
                        tag_query |= Q(tags__name=mapped_tag)
                else:
                    # If it's already a database tag, use it directly
                    tag_query |= Q(tags__name=tag)
            
            if tag_query:
                queryset = queryset.filter(tag_query).distinct()
                if verbose:
                    print(f"After tag filter: {queryset.count()} datasets")
        
        # Step 5: Keyword search on the filtered dataset
        # Split query into keywords
        keywords = query.lower().split()
        
        # Build the query
        q_objects = Q()
        for keyword in keywords:
            q_objects |= Q(title__icontains=keyword) 
            q_objects |= Q(description__icontains=keyword)
            q_objects |= Q(dataset_path__icontains=keyword)
        
        # Apply keyword filtering
        queryset = queryset.filter(q_objects)
        
        if verbose:
            print(f"After keyword filter: {queryset.count()} datasets")
        
        # Format results
        results = []
        for dataset in queryset[:self.max_results]:
            # Get available geographies for this dataset
            geo_levels = list(dataset.geographies.all().values_list('name', flat=True))
            
            results.append({
                'dataset': dataset,
                'score': 0.5,  # Default score for keyword matches
                'vintage': dataset.vintage,
                'title': dataset.title,
                'path': dataset.dataset_path,
                'variable_count': dataset.variables.count(),
                'id': dataset.id,
                'description': dataset.description or '',
                'geographic_levels': geo_levels,
                'search_source': 'census'
            })
        
        # Sort by recency
        results = sorted(results, key=lambda x: x['vintage'], reverse=True)
        
        return results[:self.max_results]

###########################################
# PUBLIC FUNCTION INTERFACES
###########################################

def vector_search(query: str,
                 similarity_threshold: float = 0.5,
                 year: Optional[int] = None, 
                 tags: Optional[List[str]] = None,
                 geo_level: Optional[str] = None,
                 location: Optional[str] = None,
                 max_results: Optional[int] = None,
                 verbose: bool = False,
                 skip_empty_filters: bool = True) -> List[Dict]:
    """
    Vector search for Census datasets
    
    Args:
        query (str): Natural language query
        similarity_threshold (float): Minimum similarity score threshold
        year (int, optional): Filter Census results by specific year/vintage
        tags (list, optional): Filter Census results by specific tags
        geo_level (str, optional): Filter by geographic level (e.g., "state", "county")
        location (str, optional): Location information (e.g., "California")
            This is mainly informational as datasets typically 
            contain data for all locations at their supported geographic levels
        max_results (int, optional): Maximum number of results to return
        verbose (bool): Whether to print detailed logging information
        skip_empty_filters (bool): If True, ignore empty year and tags filters
        
    Returns:
        list: Matching datasets with relevance scores
    """
    searcher = VectorSearcher()
    
    # Process the query if geo_level or location are not explicitly provided
    if skip_empty_filters and (geo_level is None or location is None):
        if verbose:
            print("Extracting geographic information from query")
            
        processor = QueryProcessor()
        processed = processor.process_query(query)
        
        # Use extracted geo_level if not explicitly provided
        if geo_level is None and processed.get('geo_level'):
            geo_level = processed.get('geo_level')
            if verbose:
                print(f"Extracted geo_level from query: {geo_level}")
                
        # Use extracted location if not explicitly provided
        if location is None and processed.get('location'):
            location = processed.get('location')
            if verbose:
                print(f"Extracted location from query: {location}")
    
    # Skip filters if they're empty and skip_empty_filters is True
    if skip_empty_filters:
        if year is None and tags is None and geo_level is None:
            if verbose:
                print("No year, tags, or geo filters specified, searching without filters")
        elif year is None:
            if verbose:
                print("No year specified, searching without year filter")
        elif not tags:
            if verbose:
                print("No tags specified, searching without tags filter")
            tags = None
    
    return searcher.search(
        query=query,
        similarity_threshold=similarity_threshold,
        year=year,
        tags=tags,
        geo_level=geo_level,
        location=location,
        max_results=max_results,
        verbose=verbose
    )