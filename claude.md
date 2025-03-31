# Dataset Source Attribution Issue Analysis

## Problem Overview

The Crystal data analysis system is experiencing a source attribution issue in the summary report generation. When analyzing datasets, the system correctly retrieves and processes data from different sources, but the final summary report displays generic placeholder values for sources instead of the actual dataset information:

```json
{
  "sources": [
    {"citation_id": "DS-1", "title": "Dataset 1", "organization": "Unknown Source"},
    {"citation_id": "DS-2", "title": "Dataset 2", "organization": "Unknown Source"}
  ]
}
```

This issue occurs despite the fact that correct source information (dataset titles, IDs, and organization names) is initially extracted from the database and available during the early stages of processing. The problem appears to be a data flow issue where dataset identification metadata is lost during the transformation pipeline before it reaches the final summary generation.

## Data Flow and Issue Location

The system follows this general data flow:

1. **Initial Database Query** (`query_datasets_helper` in `stream_analyze.py`)
   - Queries the database for datasets matching requested IDs
   - Creates records with fields including `dataset_organization_title`, `dataset_organization_name`, etc.

2. **Resource Metadata Processing** (`process_resource_metadata` in `stream_analyze.py`)
   - Processes raw database results into a structured `datasets` dictionary
   - Maps fields like `dataset_organization_title` to `organization` in the dataset objects

3. **Dataset Processing and Analysis**
   - Downloads and processes each dataset
   - Initial dataset identification is stored in `dataset_info` object
   - Original metadata (organization, title) may be overwritten with file-based values

4. **Data Extraction and Formatting**
   - Extracts relevant data from datasets (`extract_relevant_data`)
   - Adds dataset metadata to the extracted data
   - Formats the extracted data (`format_extracted_data`)
   - Adds formatted data to `all_formatted_data` list

5. **Summary Generation** (`summarize_findings` in `summarization.py`)
   - Processes `all_formatted_data` to create a summary
   - Creates `sources` list for display in the report

The critical issue appears to be in step 4, where the original dataset identification (title, ID, organization) is lost when formatting the data and adding it to `all_formatted_data`. Specifically, the problem likely happens when `formatted_data['formatted_data']` is added to `all_formatted_data` without preserving the dataset identification fields from the outer `formatted_data` object.

## Relevant Files and Functions

### 1. `functions/helpers/stream_analyze.py`

This is the primary file handling the data processing pipeline. Key functions and areas:

- **`query_datasets_helper(dataset_ids)`**: Initial database query function
- **`process_resource_metadata(resource_metadata)`**: Processes raw DB results into structured dataset objects
- **`stream_analyze_helper(dataset_ids, query, file_path=None)`**: Main function orchestrating the entire process
- **Where `all_formatted_data` is built**: Look for code that adds items to this list
- **Where extracted data is processed**: Look for where dataset metadata is added to extracted data
- **Where `format_extracted_data` is called**: Focus on parameter passing and result handling

The most critical section is likely where formatted data is added to `all_formatted_data`:

```python
# Potential issue: only the inner data is added, losing dataset identity
if isinstance(formatted_data, dict) and 'formatted_data' in formatted_data:
    all_formatted_data.append(formatted_data['formatted_data'])
```

### 2. `functions/factchecker/presentation/summarization.py`

This file handles the final summary generation. Key functions:

- **`summarize_findings(query, formatted_data_list, dataset_analyses=None)`**: Creates the final summary from formatted data
- **`format_findings_for_display(findings)`**: Formats the findings for UI display

The source creation happens in `summarize_findings`:

```python
for i, data in enumerate(formatted_data_list):
    dataset_title = data.get("dataset_title", "Unnamed Dataset")
    dataset_id = data.get("dataset_id", "Unknown ID")
    
    # Extract organization info
    organization = (
        data.get("organization_title") or
        data.get("organization") or
        data.get("dataset_source") or
        data.get("organization_name") or
        "Unknown Source"
    )
    
    sources.append({
        "citation_id": dataset_id[:8] if dataset_id and dataset_id != "Unknown ID" else f"DS-{i+1}",
        "title": dataset_title if dataset_title != "Unnamed Dataset" else f"Dataset {i+1}",
        "organization": organization
    })
```

### 3. `functions/factchecker/models.py`

Contains database model definitions:

- **`DatasetCatalog`**: Main dataset metadata model with fields:
  - `dataset_id`
  - `title`
  - `organization_name`
  - `organization_title`
  - `organization_description`

- **`DatasetResource`**: Resource model with FK to DatasetCatalog

## Observed Errors

Recent logs show an error when attempting to fix the issue:

TypeError: format_extracted_data() got an unexpected keyword argument 'dataset_info'


This indicates that an attempt was made to add dataset identification metadata during the formatting step, but the function doesn't accept those parameters.

## Recent Implementation Attempts

Based on error logs, there was an attempt to modify the code:

```python
formatted_data = format_extracted_data(
    extracted_data,
    analysis_result,
    query,
    dataset_info={  # This parameter doesn't exist in the function
        "title": dataset["title"],
        "id": dataset_id,
        "organization": dataset.get("organization", ""),
        "organization_name": dataset.get("organization_name", "")
    }
)
```

But the `format_extracted_data` function doesn't accept a `dataset_info` parameter.

## Debugging Information

Logs show that correct organization data is being extracted from the database:

organization_description: "Our mission is to protect human health and the environment."
organization_name: "epa-gov"
organization_title: "U.S. Environmental Protection Agency"

But this data is not making it to the final summary output.

## Required Fixes

The solution requires these key changes:

1. **Preserve Dataset Identity**: Modify how `all_formatted_data` is built to preserve dataset identity fields
   - Need to ensure dataset_id, dataset_title, and organization info is preserved

2. **Enhance Logging**: Add targeted logging to track data flow through the system
   - Log what's in `formatted_data` before and after processing
   - Log what's in each item of `all_formatted_data` before it's passed to `summarize_findings`

3. **Fix Data Flow**: Ensure dataset metadata flows correctly through the entire pipeline
   - Avoid overwriting original dataset metadata with file names
   - Properly bubble up organization information through each step

## Recommended Approach

1. Add detailed logging to understand the exact structure and content of data at each step
2. Modify the code that builds `all_formatted_data` to preserve dataset identity fields
3. Ensure organization information is properly passed from database to final summary
4. Add additional fallbacks and validation in summary generation to handle missing data
5. Add the ability to use original dataset title from database rather than file names

## Impact

Fixing this issue will ensure that summary reports correctly attribute information to their source datasets, improving the transparency and trustworthiness of the system's analysis output. Instead of generic "Dataset 1" references, users will see proper citations with actual dataset titles and originating organizations.