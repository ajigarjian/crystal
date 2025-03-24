from typing import Dict, List, Tuple, Any, Union, TypedDict, Optional
import pandas as pd
import numpy as np
import logging
import openai
import json
import os
import time
import uuid
import datetime

from factchecker.models import DatasetCatalog
from factchecker.processing.analysis.dataset_analyzer import ExtendedJSONEncoder
from factchecker.utils.openai_client import chat_completion, reasoning_completion


def ensure_serializable(obj):
    """Convert any non-serializable objects to serializable formats."""
    if isinstance(obj, pd.DataFrame):
        return obj.to_dict(orient="records")
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif hasattr(obj, 'to_dict'):
        return obj.to_dict()
    return obj

def process_result_for_serialization(result_dict):
    """Process the result dictionary to ensure all values are JSON serializable."""
    if isinstance(result_dict, dict):
        return {k: process_result_for_serialization(v) for k, v in result_dict.items()}
    elif isinstance(result_dict, list):
        return [process_result_for_serialization(item) for item in result_dict]
    else:
        return ensure_serializable(result_dict)

def summarize_findings(
    query: str,
    extracted_data_list: List[Dict[str, Any]],
    dataset_analyses: List[Dict[str, Any]] = None
) -> str:
    """
    Summarize findings from multiple datasets into a concise response.
    
    Args:
        query: The original user query
        extracted_data_list: List of dictionaries containing extracted data
        dataset_analyses: List of dataset analysis results
        
    Returns:
        Concise summary of findings
    """
    # Debug print 
    if not extracted_data_list:
        return "No relevant data was found to answer your query."
    
    # Prepare information about each dataset and its extracted data
    dataset_summaries = []
    dataset_ids = []  # Track dataset IDs for the summary
    
    for data in extracted_data_list:
        dataset_title = data.get("dataset_title", "Unnamed Dataset")
        dataset_id = data.get("dataset_id", "Unknown ID")
        
        # Get the extracted data - this is what's missing from the final output
        extracted = data.get("extracted_data")
        extraction_explanation = data.get("explanation", "")
        
        # Create a formatted sample of actual data values
        data_sample = ""
        if isinstance(extracted, pd.DataFrame):
            # For DataFrames, take a sample of rows to include in the summary
            if len(extracted) > 0:
                data_sample = "KEY DATA POINTS:\n"
                # Take up to 5 representative rows
                sample_df = extracted.head(5)
                for idx, row in sample_df.iterrows():
                    data_sample += f"- {', '.join([f'{col}: {val}' for col, val in row.items() if pd.notna(val)])}\n"
                
                # Add summary statistics if numeric columns exist
                numeric_cols = sample_df.select_dtypes(include=[np.number]).columns
                if len(numeric_cols) > 0:
                    data_sample += "\nSTATISTICAL SUMMARY:\n"
                    for col in numeric_cols:
                        if "unemploy" in col.lower():
                            data_sample += f"- {col}: min={extracted[col].min()}, max={extracted[col].max()}, avg={extracted[col].mean():.2f}\n"
        
        dataset_summaries.append(f"Source: {dataset_title} (ID: {dataset_id})\n{extraction_explanation}\n{data_sample}")
    
    # Include dataset analyses if provided
    dataset_context = ""
    if dataset_analyses:
        dataset_context = "DATASET CONTEXT:\n"
        for analysis in dataset_analyses:
            # Include basic dataset information
            dataset_context += f"Dataset: {analysis.get('dataset_title', 'Unknown')}\n"
            dataset_context += f"Dataset ID: {analysis.get('dataset_id', 'Unknown ID')}\n"
            
            # Include row and column counts
            if 'row_count' in analysis and 'column_count' in analysis:
                dataset_context += f"Size: {analysis['row_count']} rows, {analysis['column_count']} columns\n"
            
            # Include categorical summaries
            if 'categorical_summaries' in analysis and analysis['categorical_summaries']:
                dataset_context += "Categories: " + "; ".join(analysis['categorical_summaries']) + "\n"
            
            # Include geographic scope
            if 'geographic_scope' in analysis and analysis['geographic_scope']:
                geo_info = [f"{k}: {v}" for k, v in analysis['geographic_scope'].items()]
                dataset_context += "Geographic scope: " + "; ".join(geo_info) + "\n"
            
            # Include analysis if available
            if 'analysis' in analysis:
                dataset_context += f"Analysis: {analysis['analysis']}\n\n"

    # Create prompt for OpenAI
    prompt = f"""
You are analyzing data to answer: "{query}"

{dataset_context}

DATA POINTS:
{chr(10).join(dataset_summaries)}

INSTRUCTIONS:
1. Present the KEY DATA POINTS that directly answer the query - include SPECIFIC NUMBERS and VALUES
2. Be concise but thorough - include all relevant data in your analysis
3. Format as bullet points where appropriate
4. Always cite the source dataset and calculation strategy in brackets [] for each data point
5. If analyzing trends over time, be sure to include the full time range and specific values in your analysis
6. Pay special attention to the most recent data points when analyzing trends

Finally, provide a "SEARCH SUMMARY" section with 2 paragraphs that:
1. Summarizes the overall context of the datasets analyzed (their scope, limitations, quality)
2. Synthesizes the findings in relation to the query [mentioning date context where applicable]
"""
    
    response = chat_completion(
        prompt,
        system_message="You are a data analyst who provides thorough analysis of data, with special attention to recent data points.",
        max_tokens=2048,
        model_name="gpt-4o" # Let's use the good model for this
        )
    # Return the summary
    return response

def summarize_findings_alternate(
    query: str,
    extracted_data_list: List[Dict[str, Any]],
    dataset_analyses: List[Dict[str, Any]] = None
) -> str:
    """
    Alternative version that generates JSON output with full extracted data.
    
    Args:
        query: The original user query
        extracted_data_list: List of dictionaries containing extracted data
        dataset_analyses: List of dataset analysis results
        
    Returns:
        JSON-formatted string containing comprehensive findings and extracted data
    """
    start_time = time.time()
    
    # Get the text summary from the original function
    summary_text = summarize_findings(query, extracted_data_list, dataset_analyses)
    
    # Initialize the result structure
    result = {
        "query": query,
        "status": "completed",
        "request_id": str(uuid.uuid4())[:8],
        "timestamp": datetime.datetime.now().isoformat(),
        "relevant_datasets": [],
        "extracted_data": [],
        "dataset_context": [],  # New field for dataset context
        "summary": {
            "text": summary_text,
            "confidence": 0.85
        },
        "analysis_steps": {
            "extraction_time_sec": 0,
            "processing_notes": ""
        }
    }
    
    # Add dataset information to the result
    for data in extracted_data_list:
        dataset_info = {
            "dataset_id": data.get("dataset_id", "Unknown ID"),
            "title": data.get("dataset_title", "Unnamed Dataset"),
            "source": data.get("dataset_source", "Unknown Source"),
            "files": []
        }
        
        # Add file information
        if "file_path" in data:
            dataset_info["files"].append({
                "path": data.get("file_path", ""),
                "format": os.path.splitext(data.get("file_path", ""))[1][1:].upper()
            })
        
        # Add all file paths if available
        if "all_file_paths" in data and data["all_file_paths"]:
            for path in data["all_file_paths"]:
                if path != data.get("file_path", ""):  # Skip the main file that's already added
                    dataset_info["files"].append({
                        "path": path,
                        "format": os.path.splitext(path)[1][1:].upper()
                    })
        
        result["relevant_datasets"].append(dataset_info)
        
        # Process the extracted data for serialization
        processed_data = process_result_for_serialization(data)
        
        # Include subset_df in the extracted data if it exists
        if "subset_df" in data:
            processed_data["subset_df"] = process_result_for_serialization(data["subset_df"])
        
        result["extracted_data"].append(processed_data)
    
    # Add dataset context from analyses
    if dataset_analyses:
        for analysis in dataset_analyses:
            dataset_context = {
                "dataset_id": analysis.get("dataset_id", "Unknown ID"),
                "title": analysis.get("dataset_title", "Unnamed Dataset"),
                "overview": analysis.get("analysis", "No analysis available"),
                "row_count": analysis.get("row_count", 0),
                "column_count": analysis.get("column_count", 0),
                "missing_values_summary": analysis.get("missing_values_summary", []),
                "temporal_scope": analysis.get("temporal_scope", {}),
                "geographic_scope": analysis.get("geographic_scope", {}),
                "categorical_summaries": analysis.get("categorical_summaries", []),
                "column_info": analysis.get("column_info", {}),
                "numerical_stats": analysis.get("numerical_stats", {}),
                "temporal_coverage": analysis.get("temporal_coverage", {}),
                "missing_values": analysis.get("missing_values", {}),
                "data_quality": analysis.get("data_quality", {})
            }
            
            # Add any additional metadata that might be useful
            if "dataset_metadata" in analysis:
                dataset_context["metadata"] = analysis["dataset_metadata"]
                
            # Add any dataset statistics
            if "dataset_stats" in analysis:
                dataset_context["statistics"] = analysis["dataset_stats"]
                
            result["dataset_context"].append(dataset_context)
    
    # Add analysis steps info
    result["analysis_steps"]["extraction_time_sec"] = round(time.time() - start_time, 1)
    
    # Include dataset IDs in processing notes
    dataset_ids = [data.get("dataset_id", "unknown") for data in extracted_data_list]
    result["analysis_steps"]["processing_notes"] = f"Analysis based on {len(dataset_ids)} datasets: {', '.join(dataset_ids)}"
    
    # Add query processing details
    result["analysis_steps"]["query_processing"] = {
        "original_query": query,
        "datasets_analyzed": len(dataset_ids),
        "extraction_methods_used": [data.get("extraction_strategy", "Unknown strategy") 
                                   for data in extracted_data_list if "extraction_strategy" in data]
    }
    
    # Return formatted JSON string
    return json.dumps(result, indent=2, cls=ExtendedJSONEncoder)

def summarize_findings_structured(
    query: str,
    extracted_data_list: List[Dict[str, Any]],
    dataset_analyses: List[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Generate a structured summary of findings suitable for formal research, journalism or consulting,
    with citations for all key claims.
    
    Args:
        query: The original user query
        extracted_data_list: List of dictionaries containing extracted data
        dataset_analyses: List of dataset analysis results
        
    Returns:
        Dictionary containing structured findings with formal research elements and citations
    """
    # Basic initial logging
    print(f"[DEBUG] Beginning structured summary generation for query: '{query}'")
    print(f"[DEBUG] Processing {len(extracted_data_list)} datasets")
    
    # Prepare information about each dataset and its extracted data
    usable_datasets = []
    key_data_points = []
    key_sources = []
    source_details = {}
    
    # Track if we found any usable data
    found_usable_data = False
    
    # First, collect all datasets with usable data without assigning citation IDs yet
    for data in extracted_data_list:
        dataset_title = data.get("title", data.get("dataset_title", "Unnamed Dataset"))
        dataset_id = data.get("dataset_id", "Unknown ID")
        dataset_source = data.get("dataset_source", "Unknown Source")
        organization = data.get("organization", "")
        
        print(f"\n[DEBUG] Processing dataset: {dataset_title} (ID: {dataset_id})")
        
        # Use the recursive extract_usable_data function to find any usable data
        results_dict = data.get('results_dict')
        if results_dict is not None:
            # Search for usable data starting from results_dict
            extracted = extract_usable_data(results_dict, dataset_title)
        else:
            print(f"[WARNING] No results_dict found for dataset {dataset_title}")
            extracted = None
        
        # If no data found in results_dict, try searching the entire data structure
        if extracted is None:
            print(f"[DEBUG] Trying to find data in other fields")
            # Search the entire data dictionary excluding results_dict to avoid recursion
            data_copy = {k: v for k, v in data.items() if k != 'results_dict'}
            extracted = extract_usable_data(data_copy, dataset_title)
        
        # If we still don't have data, log and continue
        if extracted is None:
            print(f"[WARNING] Could not locate any usable data for dataset {dataset_title}")
            continue
        
        # We found usable data
        found_usable_data = True
        print(f"[DEBUG] Successfully found usable data for {dataset_title}")
        
        # Add to temporary sources list (without citation ID yet)
        source_details[dataset_id] = {
            "title": dataset_title,
            "id": dataset_id,
            "organization": organization or "Unknown",
            "source": dataset_source[:100] + "..." if len(dataset_source) > 100 else dataset_source,
            "data": extracted
        }
        
        # Look for aggregations in the results_dict
        if isinstance(results_dict, dict):
            # Check for aggregations directly in results_dict
            if 'aggregations' in results_dict:
                aggregations = results_dict['aggregations']
                # Add aggregation data to key_data_points
                for key, value in aggregations.items():
                    if isinstance(value, (int, float, str)):
                        key_data_points.append({
                            "dataset_id": dataset_id,
                            "dataset_title": dataset_title,
                            "metric_name": key,
                            "value": value
                        })
            
            # Also check for aggregations nested in 'data'
            if 'data' in results_dict and isinstance(results_dict['data'], dict) and 'aggregations' in results_dict['data']:
                aggregations = results_dict['data']['aggregations']
                # Add aggregation data to key_data_points
                for key, value in aggregations.items():
                    if isinstance(value, (int, float, str)):
                        key_data_points.append({
                            "dataset_id": dataset_id,
                            "dataset_title": dataset_title,
                            "metric_name": key,
                            "value": value
                        })
    
    # Now assign sequential citation IDs to all usable datasets
    for idx, (dataset_id, source_info) in enumerate(source_details.items(), 1):
        # Create a sequential citation ID starting from 1
        source_id = str(idx)
        
        # Add to key_sources with proper sequential numbering
        key_sources.append({
            "citation_id": source_id,
            "title": source_info["title"],
            "id": source_info["id"],
            "organization": source_info["organization"],
            "source": source_info["source"]
        })
        
        # Add to usable datasets with the same citation ID
        usable_datasets.append({
            "source_id": source_id,
            "title": source_info["title"],
            "data": source_info["data"]
        })
    
    # If we found no usable data, return a clear message
    if not found_usable_data or len(usable_datasets) == 0:
        return {
            "query": query,
            "summary": "Unable to extract relevant information from the provided datasets to answer this query.",
            "key_findings": ["No usable data could be extracted from the datasets."],
            "sources": [{
                "citation_id": "1",
                "title": "No usable data sources",
                "organization": "None"
            }]
        }
    
    # If we have usable data, generate a proper summary
    print(f"[DEBUG] Generating citations-included summary and key findings for {len(usable_datasets)} usable datasets")
    
    # Now create a prompt for the LLM that requests numeric citations in the summary
    citation_prompt = f"""
        You are analyzing data to answer: "{query}"

        Your task is to write two sections:
        1. A detailed SUMMARY of the findings (250-400 words). Do not include a word count in your output.
        2. 3-5 KEY FINDINGS (1-2 sentences each)

        IMPORTANT: For both sections, you MUST cite the source of each claim using the citation format [N] where N is the source number.

        Available sources to cite:
        {chr(10).join([f'[{s["citation_id"]}] {s["title"]} ({s["organization"]})' for s in key_sources])}

        For example: "Vaccination rates increased by 30% since 2018 [1]. However, some neighborhoods still experience lower coverage [2]."

        Make sure EVERY factual claim has a citation based on the dataset description or extracted data. Do not make up citations. If multiple sources support a claim, you can list them like [1, 2].
        Be specific with numbers and data points.
        """
    
    # Get citations-included summary and key findings using reasoning_completion
    try:
        cited_content = reasoning_completion(
            prompt=citation_prompt,
            system_message="You are a professional data analyst who provides rigorous, citation-supported research for journalists and policy researchers.",
            reasoning_effort="high",
            model_name="o3-mini"
        )
    except Exception as e:
        print(f"[WARNING] Error calling reasoning client: {e}")
        cited_content = """
        SUMMARY
        Based on the available data, I'm unable to provide a comprehensive analysis for this query.

        KEY FINDINGS
        1. The available datasets do not contain sufficient information to address the query directly.
        """
    
    # Extract summary and key findings from the response
    summary_with_citations = ""
    findings_with_citations = []
    
    # Try to split content into summary and key findings
    if "SUMMARY" in cited_content and "KEY FINDINGS" in cited_content:
        parts = cited_content.split("KEY FINDINGS")
        summary_with_citations = parts[0].replace("SUMMARY", "").strip()
        findings_part = parts[1].strip()
    else:
        # If we can't split cleanly, use the whole text as summary
        summary_with_citations = cited_content.strip()
        findings_part = ""
    
    # Parse findings with flexible format handling
    if findings_part:
        # Try multiple pattern matching approaches
        import re
        numbered_findings = re.findall(r'\d+\.[\s\:]+(.*?)(?=\d+\.|$)', findings_part, re.DOTALL)
        if numbered_findings and all(finding.strip() for finding in numbered_findings):
            findings_with_citations = [finding.strip() for finding in numbered_findings]
        elif '•' in findings_part:
            bullet_findings = re.findall(r'•\s+(.*?)(?=•|\Z)', findings_part, re.DOTALL)
            if bullet_findings:
                findings_with_citations = [finding.strip() for finding in bullet_findings]
        else:
            findings_with_citations = [line.strip() for line in findings_part.split('\n') 
                                      if line.strip() and not line.strip().startswith(('KEY', 'FINDINGS'))]
    
    # Format the sources for the final output - fetch organization from the database
    from factchecker.models import DatasetCatalog
    
    formatted_sources = []
    for source in key_sources:
        dataset_id = source["id"]
        
        # Try to fetch the organization from the database
        try:
            db_dataset = DatasetCatalog.objects.get(dataset_id=dataset_id)
            organization = db_dataset.organization_title or db_dataset.organization_name or "Unknown"
        except Exception as e:
            # If there's an error or the dataset isn't found, use what we have
            print(f"[WARNING] Could not get organization for {dataset_id} from database: {str(e)}")
            organization = source["organization"] or "Unknown"
            
        formatted_source = {
            "citation_id": source["citation_id"],
            "title": source["title"],
            "organization": organization
        }
        formatted_sources.append(formatted_source)
    
    print(f"[DEBUG] Building final structured output")
    
    # Build and return the simplified structured output
    result = {
        "query": query,
        "summary": summary_with_citations,
        "key_findings": findings_with_citations,
        "sources": formatted_sources
    }
    
    print(f"[DEBUG] Structured summary generation complete")
    return result

def format_citation(organization, year, title, source):
    """Format a citation according to standard academic style."""
    if organization and year:
        return f"{organization} ({year}). {title}."
    elif organization:
        return f"{organization}. {title}."
    elif year:
        return f"{title} ({year})."
    else:
        return f"{title}."

def extract_usable_data(data_structure, dataset_title):
    """
    Recursively search through any data structure to find usable data.
    Returns the first DataFrame, non-empty list, or meaningful dictionary found.
    """
    print(f"[DEBUG] Examining data structure: {type(data_structure)}")
    
    # Base case: If we have a DataFrame, use it
    if isinstance(data_structure, pd.DataFrame):
        if not data_structure.empty:
            print(f"[DEBUG] Found usable DataFrame with shape {data_structure.shape}")
            return data_structure
        else:
            print(f"[DEBUG] Found empty DataFrame, continuing search")
            return None
    
    # If we have a list with content, use it
    elif isinstance(data_structure, list):
        if len(data_structure) > 0:
            print(f"[DEBUG] Found usable list with {len(data_structure)} items")
            return data_structure
        else:
            print(f"[DEBUG] Found empty list, continuing search")
            return None
    
    # If we have a dictionary, recursively search its values
    elif isinstance(data_structure, dict):
        print(f"[DEBUG] Searching dictionary with keys: {list(data_structure.keys())}")
        
        # First, look for DataFrames
        for key, value in data_structure.items():
            if isinstance(value, pd.DataFrame) and not value.empty:
                print(f"[DEBUG] Found DataFrame in key '{key}' with shape {value.shape}")
                return value
        
        # Next, look for non-empty lists
        for key, value in data_structure.items():
            if isinstance(value, list) and len(value) > 0:
                print(f"[DEBUG] Found non-empty list in key '{key}' with {len(value)} items")
                return value
        
        # Then, recursively search nested dictionaries
        for key, value in data_structure.items():
            if isinstance(value, dict):
                nested_result = extract_usable_data(value, dataset_title)
                if nested_result is not None:
                    print(f"[DEBUG] Found usable data in nested key '{key}'")
                    return nested_result
        
        # If dictionary has content but no nested structures, it might be usable itself
        if len(data_structure) > 0:
            print(f"[DEBUG] Using dictionary itself as data")
            return data_structure
    
    # Check other types that might be directly usable
    elif isinstance(data_structure, pd.Series):
        if not data_structure.empty:
            print(f"[DEBUG] Found usable Series with length {len(data_structure)}")
            return data_structure
    
    # If nothing usable found
    print(f"[WARNING] No usable data found in this structure for dataset {dataset_title}")
    return None