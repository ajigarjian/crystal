from django.shortcuts import render
from rest_framework import viewsets, status
from rest_framework.decorators import api_view, action
from rest_framework.response import Response
from factchecker.models import DatasetCatalog
from factchecker.serializers import DatasetCatalogSerializer
from factchecker.search import vector_search_datasets, preprocess_query, search_datasets
from factchecker.analysis import load_dataset, assess_dataset_relevance, extract_relevant_data, summarize_findings
from django.conf import settings
import os
from django.core.management import call_command
from io import StringIO
import sys
from factchecker.download import download_resource

# Create your views here.

class DatasetCatalogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint that allows datasets to be viewed.
    """
    queryset = DatasetCatalog.objects.all()
    serializer_class = DatasetCatalogSerializer

@api_view(['POST'])
def process_query(request):
    """
    Process a natural language query to find and analyze relevant datasets.
    """
    # Get parameters from request
    query = request.data.get('query', '')
    top_n = request.data.get('top_n', 3)  # Default to fewer datasets for API response
    search_method = request.data.get('search_method', 'vector')
    relevance_threshold = request.data.get('relevance_threshold', 0.4)
    
    if not query:
        return Response({'error': 'Query is required'}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        # 1. Search for datasets
        if search_method == 'vector':
            datasets = vector_search_datasets(
                query=query, 
                openai_api_key=settings.OPENAI_API_KEY, 
                top_n=top_n
            )
        else:
            processed_query = preprocess_query(query, settings.OPENAI_API_KEY)
            datasets = search_datasets(
                api_key=settings.DATA_GOV_API_KEY,
                query=processed_query,
                rows=top_n
            )
        
        if not datasets:
            return Response({
                'query': query,
                'message': 'No relevant datasets found',
                'results': []
            })
        
        # 2. Download and analyze datasets
        output_dir = os.path.join(settings.BASE_DIR, 'downloads')
        os.makedirs(output_dir, exist_ok=True)
        
        dataset_results = []
        extracted_data_list = []
        dataset_analyses = []
        
        for dataset in datasets:
            # Download the dataset
            dataset_id = dataset['id']
            output_path = download_resource(settings.DATA_GOV_API_KEY, dataset_id, output_dir=output_dir)
            
            if not output_path:
                dataset_results.append({
                    'id': dataset_id,
                    'title': dataset['title'],
                    'error': 'Download failed'
                })
                continue
            
            # Load the dataset
            dataset_content = load_dataset(output_path, settings.OPENAI_API_KEY)
            
            # Prepare dataset info
            dataset_info = {
                'id': dataset_id,
                'title': dataset['title'],
                'description': dataset.get('description', ''),
                'similarity': dataset.get('similarity', 0),
                'file_path': output_path
            }
            
            # Assess relevance
            is_relevant, score, reasoning = assess_dataset_relevance(
                dataset_content, 
                query, 
                dataset_info,
                settings.OPENAI_API_KEY,
                relevance_threshold
            )
            
            dataset_info['relevance_score'] = score
            dataset_info['relevance_reasoning'] = reasoning
            
            # Extract data if relevant
            if is_relevant:
                extracted_data = extract_relevant_data(
                    dataset_content, 
                    query, 
                    dataset_info,
                    settings.OPENAI_API_KEY
                )
                
                extracted_data['dataset_title'] = dataset_info['title']
                extracted_data['dataset_source'] = dataset_info.get('description', 'Data.gov dataset')
                extracted_data['dataset_id'] = dataset_info['id']
                
                extracted_data_list.append(extracted_data)
            
            dataset_results.append(dataset_info)
        
        # 3. Generate summary if we have extracted data
        summary = None
        if extracted_data_list:
            summary = summarize_findings(query, extracted_data_list, settings.OPENAI_API_KEY, dataset_analyses)
        
        # 4. Return all results
        return Response({
            'query': query,
            'summary': summary,
            'datasets': dataset_results,
            'extracted_data': extracted_data_list if extracted_data_list else None
        })
        
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
