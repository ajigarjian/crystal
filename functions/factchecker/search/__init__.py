# Import necessary functions for use in other modules
from factchecker.search.gov_api_search import search_datasets, filter_relevant_datasets
from factchecker.search.census_search import process_query, vector_search
from factchecker.search.pinecone_search import vector_search_datasets_pinecone