# Contains shared functionality to break circular imports

from typing import Dict, List, Tuple, Any, Union, TypedDict, Optional
import pandas as pd
import logging

# Define TypedDict classes for better typing
class ExtractionPlan(TypedDict):
    strategy: str
    analysis: str
    explanation: str
    code: str

class ExtractedData(TypedDict):
    dataset_id: str
    dataset_title: str
    file_path: str
    results_dict: Dict[str, Any]
    printed_output: str
    extraction_strategy: str
    explanation: str
    code: str
    error: Optional[str]