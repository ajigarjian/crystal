"""
Vector search implementation for Census datasets.
Includes natural language query processing capabilities.
"""

import numpy as np
import os
import re
import json
from factchecker.models import DatasetCatalog, CensusDataset, CensusVariable, CensusGeography, CensusFIPSCode, CensusTag
from factchecker.search.search_utils import get_usable_resources
from typing import Dict, List, Union, Optional
from factchecker.utils.openai_client import create_embeddings, chat_completion, get_cached_openai_client
from datetime import datetime
from django.db.models import Q, F, Value, FloatField
from django.db.models.functions import Lower

from helpers.db_utils import get_db_session

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
                response_format=response_format
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
        # Get all tags from the CensusTag table directly
        available_tags = [tag.name for tag in CensusTag.objects.values_list('name', flat=True)]
        
        # If no tags found in database, fall back to conceptual tags
        if not available_tags:
            available_tags = list(self.conceptual_tag_keywords.keys())
            
        return available_tags
    
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
        
        return tag_mapping
    
    def search(self, query, similarity_threshold=0.5, year=None, tags=None, geo_level=None, location=None, max_results=None, verbose=False):
        """
        Search Census datasets using vector search
        
        Args:
            query (str): Natural language query
            similarity_threshold (float): Minimum similarity score threshold
            year (int, optional): Filter by specific year/vintage
            tags (list, optional): Filter by specific tags
            geo_level (str, optional): Filter by geographic level
            location (str, optional): Filter by location
            max_results (int, optional): Maximum number of results to return
            verbose (bool): Whether to print detailed logging information
            
        Returns:
            list: Matching datasets with relevance scores
        """
        # Set max_results if provided
        if max_results is not None:
            self.max_results = max_results
            
        # Perform the search
        results = self._census_search(
            query=query,
            similarity_threshold=similarity_threshold,
            year=year,
            tags=tags,
            geo_level=geo_level,
            location=location,
            verbose=verbose
        )
        
        # Ensure results is a list
        if results is None:
            return []
        
        # If results is a generator or other iterable (but not a list), convert to list
        if hasattr(results, '__iter__') and not isinstance(results, list):
            try:
                results = list(results)
            except Exception as e:
                print(f"Error converting search results to list: {e}")
                return []
        
        # Apply recency boost to results
        if results:
            results = self._apply_recency_boost(results)
            
        # Limit to max_results
        return results[:self.max_results]
    
    def _get_embedding(self, text):
        """Get embedding for text"""
        try:
            # Ensure text is properly encoded
            if isinstance(text, bytes):
                text = text.decode('utf-8', errors='replace')
            elif not isinstance(text, str):
                text = str(text)
            
            # Create embedding
            print(f"Creating embedding for text: {text[:50]}...")
            embedding = create_embeddings(text)
            
            # Debug the embedding type and shape
            #print(f"Embedding type: {type(embedding)}")
            if hasattr(embedding, 'shape'):
                print(f"Embedding shape: {embedding.shape}")
            elif isinstance(embedding, list):
                print(f"Embedding length: {len(embedding)}")
            
            # Ensure the embedding is a numpy array, not bytes
            if isinstance(embedding, bytes):
                print("Converting bytes embedding to numpy array")
                embedding = np.frombuffer(embedding, dtype=np.float32)
            elif isinstance(embedding, list):
                print("Converting list embedding to numpy array")
                embedding = np.array(embedding, dtype=np.float32)
            
            return embedding
        except Exception as e:
            print(f"Error creating embedding: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _cosine_similarity(self, vec1, vec2):
        """Calculate cosine similarity between two vectors"""
        try:
            # If either is bytes, check if it's actually ASCII hex like b'\\x4d1a49...'
            if isinstance(vec1, bytes):
                if vec1.startswith(b'\\x'):
                    hex_str = vec1.decode('utf-8')[2:]
                    raw_bin = bytes.fromhex(hex_str)
                    vec1 = np.frombuffer(raw_bin, dtype=np.float32) if len(raw_bin) % 4 == 0 else raw_bin
                else:
                    # If it's raw binary, parse only if length % 4 == 0
                    vec1 = np.frombuffer(vec1, dtype=np.float32) if len(vec1) % 4 == 0 else vec1

            if isinstance(vec2, bytes):
                if vec2.startswith(b'\\x'):
                    hex_str = vec2.decode('utf-8')[2:]
                    raw_bin = bytes.fromhex(hex_str)
                    vec2 = np.frombuffer(raw_bin, dtype=np.float32) if len(raw_bin) % 4 == 0 else raw_bin
                else:
                    vec2 = np.frombuffer(vec2, dtype=np.float32) if len(vec2) % 4 == 0 else vec2

            # If either is still a list, convert to numpy
            if isinstance(vec1, list):
                vec1 = np.array(vec1, dtype=np.float32)
            if isinstance(vec2, list):
                vec2 = np.array(vec2, dtype=np.float32)

            # If they're still raw bytes, bail out or do your fallback
            if not isinstance(vec1, np.ndarray) or not isinstance(vec2, np.ndarray):
                print("Warning: could not parse one of the vectors as float32 array.")
                return 0.0

            dot_product = np.dot(vec1, vec2)
            norm1 = np.linalg.norm(vec1)
            norm2 = np.linalg.norm(vec2)
            return dot_product / (norm1 * norm2)

        except Exception as e:
            print(f"Error computing cosine similarity: {e}")
            return 0.0
    
    def _apply_recency_boost(self, results):
        """Apply a recency boost to the search results"""
        if not results:
            return results
        
        # Sort by similarity first
        results = sorted(results, key=lambda x: x.get("similarity", 0), reverse=True)
        
        # Apply recency boost
        current_year = datetime.now().year
        
        # Create a copy to avoid modifying while iterating
        boosted_results = []
        
        for i, result in enumerate(results):
            # Get the vintage (year) of the dataset
            vintage = result.get("vintage")
            
            # Skip if no vintage
            if not vintage:
                boosted_results.append(result)
                continue
            
            # Convert to int if it's a string
            if isinstance(vintage, str):
                try:
                    vintage = int(vintage)
                except ValueError:
                    boosted_results.append(result)
                    continue
                
            # Calculate age in years
            age = current_year - vintage
            
            # Calculate recency boost (newer datasets get a higher boost)
            recency_boost = max(0, 0.1 * (1 - age / 10))  # 10% max boost, decreasing with age
            
            # Apply the boost to the similarity score
            original_similarity = result.get("similarity", 0)
            boosted_similarity = min(1.0, original_similarity * (1 + recency_boost))
            
            # Create a new result with the boosted score
            boosted_result = result.copy()
            boosted_result["similarity"] = boosted_similarity
            boosted_result["original_similarity"] = original_similarity
            boosted_result["recency_boost"] = recency_boost
            
            boosted_results.append(boosted_result)
        
        # Re-sort by boosted similarity
        boosted_results = sorted(boosted_results, key=lambda x: x.get("similarity", 0), reverse=True)
        
        return boosted_results
    
    def _census_search(self, query, year=None, tags=None, similarity_threshold=0.5, geo_level=None, location=None, verbose=False):
        """Search Census datasets"""
        try:
            print(f"Getting embedding for query: {query}")
            query_embedding = self._get_embedding(query)
            if query_embedding is None:
                print("Failed to get embedding for query, falling back to keyword search")
                return self._census_fallback_keyword_search(query, year, tags, geo_level, location, verbose)

            # Debug: Print out filter parameters
            print(f"Debug => year: {year}, tags: {tags}, geo_level: {geo_level}, location: {location}")

            # Start the base query
            base_query = CensusDataset.objects.exclude(embedding=None)
            print("Debug => Base query for CensusDataset where embedding != None. Testing row count…")
            debug_count = base_query.count()
            print(f"Debug => Row count so far: {debug_count}")

            # Apply optional filters
            if year:
                print(f"Debug => Applying year filter: {year}")
                base_query = base_query.filter(vintage=year)
                debug_count = base_query.count()
                print(f"Debug => Row count after year filter: {debug_count}")

            if tags and isinstance(tags, list):
                print(f"Debug => Applying tags filter: {tags}")
                base_query = base_query.filter(tags__name__in=tags)
                debug_count = base_query.count()
                print(f"Debug => Row count after tags filter: {debug_count}")

            if location:
                print(f"Debug => Potential location filter: {location}")
                # If you have location-based logic, do it here:
                # base_query = base_query.filter(...)
                # debug_count = base_query.count()
                # print(f"Debug => Row count after location filter: {debug_count}")

            if geo_level:
                print(f"Debug => Potential geo_level filter: {geo_level}")
                # If you have geographic level logic, do it here:
                # base_query = base_query.filter(...)
                # debug_count = base_query.count()
                # print(f"Debug => Row count after geo_level filter: {debug_count}")

            # Finally, get the datasets
            datasets = list(base_query.all())
            print(f"Found {len(datasets)} datasets after filtering")

            if not datasets:
                print("No datasets found after filtering, falling back to keyword search")
                return self._census_fallback_keyword_search(query, year, tags, geo_level, location, verbose)

            results = []
            for dataset in datasets:
                try:
                    # Check if embedding exists
                    if dataset.embedding is None:
                        print(f"Dataset {dataset.id} has no embedding, skipping")
                        continue
                        
                    # Debug the embedding
                    if isinstance(dataset.embedding, bytes):
                        print(f"Dataset {dataset.id} embedding is bytes, length: {len(dataset.embedding)}")
                    
                    # Ensure proper conversion from binary to numpy array
                    dataset_embedding = dataset.embedding
                    if isinstance(dataset_embedding, bytes):
                        if dataset_embedding.startswith(b'\\x'):
                            hex_str = dataset_embedding.decode('utf-8')[2:]
                            raw_bin = bytes.fromhex(hex_str)
                            if len(raw_bin) % 4 == 0:
                                try:
                                    dataset_embedding = np.frombuffer(raw_bin, dtype=np.float32)
                                    print(f"Converted dataset {dataset.id} to np array shape {dataset_embedding.shape}")
                                except Exception as e:
                                    print(f"Error converting dataset {dataset.id} embedding: {e}")
                                    continue
                            else:
                                print(f"Dataset {dataset.id} embedding length {len(raw_bin)} not multiple of 4")
                                continue
                        else:
                            # If it's raw binary, parse only if length % 4 == 0
                            if len(dataset_embedding) % 4 == 0:
                                try:
                                    dataset_embedding = np.frombuffer(dataset_embedding, dtype=np.float32)
                                except Exception as e:
                                    print(f"Error converting dataset {dataset.id} embedding: {e}")
                                    continue
                            else:
                                print(f"Dataset {dataset.id} embedding length {len(dataset_embedding)} not multiple of 4")
                                continue
                    
                    # Calculate similarity
                    similarity = self._cosine_similarity(query_embedding, dataset_embedding)
                    
                    # Add to results if above threshold
                    if similarity >= similarity_threshold:
                        results.append({
                            "id": dataset.id,
                            "title": dataset.title,
                            "description": dataset.description if dataset.description else "",
                            "vintage": dataset.vintage,
                            "dataset_path": dataset.dataset_path,
                            "similarity": float(similarity),
                            "search_source": "census_vector"
                        })
                except Exception as e:
                    print(f"Error processing dataset {dataset.id}: {e}")
                    import traceback
                    traceback.print_exc()
                    continue
            
            # Sort by similarity (highest first)
            results = sorted(results, key=lambda x: x["similarity"], reverse=True)
            
            # Limit to max_results
            results = results[:self.max_results]
            
            print(f"Found {len(results)} results with similarity >= {similarity_threshold}")
            
            return results
            
        except Exception as e:
            print(f"Error searching Census datasets: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _census_fallback_keyword_search(self, query, year=None, tags=None, geo_level=None, location=None, verbose=False):
        """Fallback to keyword search when vector search fails"""
        try:
            # Start with all datasets
            base_query = CensusDataset.objects.all()
            
            if verbose:
                print(f"Starting with {base_query.count()} total datasets")
            
            # Step 1: Filter by year if provided
            if year:
                base_query = base_query.filter(vintage=year)
                if verbose:
                    print(f"After year filter: {base_query.count()} datasets")
                    
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
                    geo_dataset_ids = CensusGeography.objects.filter(
                        name__icontains=normalized_geo
                    ).values_list('dataset_id', flat=True)
                    
                    if geo_dataset_ids.exists():
                        base_query = base_query.filter(id__in=geo_dataset_ids)
                        if verbose:
                            print(f"After geography filter: {base_query.count()} datasets")
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
                location_filtered = base_query.filter(
                    Q(title__icontains=location) | 
                    Q(description__icontains=location)
                )
                
                if location_filtered.exists():
                    base_query = location_filtered
                    if verbose:
                        print(f"After location filter: {base_query.count()} datasets")
                else:
                    if verbose:
                        print(f"No datasets found with location '{location}' in metadata. Skipping location filter.")
                        print(f"This is normal for Census datasets which typically don't mention specific locations.")
            
            # Step 4: Map conceptual tags to actual database tags
            if tags and len(tags) > 0:
                # Generate tag mapping once
                tag_mapping = self._generate_tag_mapping(year, verbose)
                
                # Build query for mapped tags
                tag_conditions = Q()
                
                for tag in tags:
                    if tag in tag_mapping:
                        # If it's a conceptual tag, map to actual database tags
                        mapped_tags = tag_mapping[tag]
                        for mapped_tag in mapped_tags:
                            # Add condition for each mapped tag
                            tag_conditions |= Q(title__icontains=mapped_tag) | Q(description__icontains=mapped_tag)
                    else:
                        # If it's already a database tag, use it directly
                        tag_conditions |= Q(title__icontains=tag) | Q(description__icontains=tag)
                
                if tag_conditions:
                    base_query = base_query.filter(tag_conditions)
                    if verbose:
                        print(f"After tag filter: {base_query.count()} datasets")
            
            # Step 5: Keyword search on the filtered dataset
            # Split query into keywords
            keywords = query.lower().split()
            
            # Build the query
            keyword_conditions = Q()
            for keyword in keywords:
                keyword_conditions |= Q(title__icontains=keyword)
                keyword_conditions |= Q(description__icontains=keyword)
                keyword_conditions |= Q(dataset_path__icontains=keyword)
            
            # Apply keyword filtering
            if keyword_conditions:
                base_query = base_query.filter(keyword_conditions)
            
            if verbose:
                print(f"After keyword filter: {base_query.count()} datasets")
            
            # Format results
            results = []
            for dataset in base_query[:self.max_results]:
                # Get available geographies for this dataset
                geo_levels = []
                try:
                    # Get geographies for this dataset
                    geo_levels = list(dataset.geographies.values_list('name', flat=True))
                except Exception as e:
                    print(f"Error getting geographies for dataset {dataset.id}: {e}")
                
                results.append({
                    'dataset': dataset,
                    'score': 0.5,  # Default score for keyword matches
                    'vintage': dataset.vintage,
                    'title': dataset.title,
                    'path': dataset.dataset_path,
                    'variable_count': CensusVariable.objects.filter(dataset_id=dataset.id).count(),
                    'id': dataset.id,
                    'description': dataset.description or '',
                    'geographic_levels': geo_levels,
                    'search_source': 'census'
                })
            
            # Sort by recency
            results = sorted(results, key=lambda x: x['vintage'], reverse=True)
            
            # Ensure we return a list
            return list(results[:self.max_results])
        except Exception as e:
            print(f"Error in fallback search: {e}")
            import traceback
            traceback.print_exc()
            return []

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
        if year is None and (tags is None or len(tags) == 0) and geo_level is None:
            if verbose:
                print("No year, tags, or geo filters specified, searching without filters")
        elif year is None:
            if verbose:
                print("No year specified, searching without year filter")
        elif tags is None or len(tags) == 0:
            if verbose:
                print("No tags specified, searching without tags filter")
            tags = None
    
    try:
        # Ensure query is a string
        if not isinstance(query, str):
            query = str(query)
            
        print(f"Starting vector search with query: {query}")
        results = searcher.search(
            query=query,
            similarity_threshold=similarity_threshold,
            year=year,
            tags=tags,
            geo_level=geo_level,
            location=location,
            max_results=max_results,
            verbose=verbose
        )
        
        print(f"Search returned results of type: {type(results)}")
        if results is None:
            print("Search returned None, returning empty list")
            return []
        elif hasattr(results, '__iter__') and not isinstance(results, list):
            print(f"Converting results of type {type(results)} to list")
            print(f"Results dir: {dir(results)}")  # Print available methods
            try:
                list_results = list(results)
                print(f"Successfully converted to list with {len(list_results)} items")
                return list_results
            except Exception as e:
                print(f"Error converting to list: {str(e)}")
                # ... existing fallback code ...
        
        print(f"Returning {len(results)} search results")
        return results
    except Exception as e:
        print(f"Error searching Census datasets: {str(e)}")
        import traceback
        traceback.print_exc()
        return []