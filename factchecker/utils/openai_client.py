import os
import openai
from typing import Dict, List, Any, Optional

# Try to load Azure OpenAI provider, otherwise fall back to OpenAI
try:
    AZURE_OPENAI_KEY = os.environ["AZURE_OPENAI_API_KEY"]
    AZURE_OPENAI_ENDPOINT = os.environ["AZURE_OPENAI_ENDPOINT"]
    provider = "azure"

except KeyError:
    OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
    provider = "openai"

def get_openai_client():
    """
    Create and return an OpenAI client configured for either OpenAI or Azure OpenAI.
        
    Returns:
        An OpenAI client
    """
    # If the Azure OpenAI key is set, let's default to using that as a preferred OpenAI provider
    if provider == "azure":
        if not AZURE_OPENAI_ENDPOINT:
            raise ValueError("Azure endpoint is required when using Azure OpenAI")
        
        # Configure for Azure OpenAI
        client = openai.AzureOpenAI(
            api_key=AZURE_OPENAI_KEY,
            api_version="2025-02-01-preview",  # Update this to the version you're using
            azure_endpoint=AZURE_OPENAI_ENDPOINT
        )
        return client
    else:
        # Configure for regular OpenAI
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        return client

def get_openai_embeddings_client():
    """
    Create and return an OpenAI embeddings client configured for either OpenAI or Azure OpenAI.
        
    Returns:
        An OpenAI client
    """
    # If the Azure OpenAI key is set, let's default to using that as a preferred OpenAI provider
    if provider == "azure":        
        # Configure for Azure OpenAI
        client = openai.AzureOpenAI(
            api_key=AZURE_OPENAI_KEY,
            api_version="2025-02-01-preview",  # Hardcoded for text-embedding-3-small model
            azure_endpoint=AZURE_OPENAI_ENDPOINT
        )
        return client
    else:
        # Configure for regular OpenAI
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        return client

# Add a cache for the OpenAI client to avoid recreating it for each request
_openai_client_cache = {}
_openai_embeddings_client_cache = {}

def get_cached_openai_client():
    """
    Create and return a cached OpenAI client configured for either OpenAI or Azure OpenAI.
    The client is created only once per process and then reused.
        
    Returns:
        An OpenAI client
        A Deployment Name
    """
    global _openai_client_cache
    
    if provider not in _openai_client_cache:
        _openai_client_cache[provider] = get_openai_client()
    
    return _openai_client_cache[provider]

def get_cached_openai_embeddings_client():
    """
    Create and return a cached OpenAI embeddings client.
    The client is created only once per process and then reused.
        
    Returns:
        An OpenAI client
        A Deployment Name
    """
    global _openai_embeddings_client_cache
    
    if provider not in _openai_embeddings_client_cache:
        _openai_embeddings_client_cache[provider] = get_openai_embeddings_client()
    
    return _openai_embeddings_client_cache[provider]

def create_embeddings(query):
    """
    Returns a new embeddings output from OpenAI.
    """
    client = get_cached_openai_embeddings_client()

    response = client.embeddings.create(
        input=query,
        model="text-embedding-3-small"
    )

    return response.data[0].embedding    

def chat_completion(
    prompt: str, 
    system_message: str = "You are a helpful assistant.",
    temperature: float = 0.2,
    max_tokens: int = 800,
    response_format: Optional[Dict[str, str]] = None,
    model_name: Optional[str] = "gpt-4o-mini"
) -> str:
    """
    Get a chat completion from OpenAI or Azure OpenAI.
    
    Args:
        prompt: The user prompt
        system_message: The system message to use
        temperature: The temperature to use for generation
        max_tokens: Maximum tokens
        response_format: Optional format specification for the response
        model_name: Optional model name to use (e.g., "gpt-4o", "gpt-4o-mini")
        
    Returns:
        The generated text
    """
    client = get_cached_openai_client()
    
    try:
        # Create API call with or without response_format based on whether it's provided
        if response_format is not None:
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format
            )
        else:
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                max_tokens=max_tokens
            )
        print("Generated response with model:", model_name)
        return response.choices[0].message.content

    except Exception as e:
        print(f"Error calling OpenAI API: {str(e)}")
        return f"Error generating response: {str(e)}" 

def reasoning_completion(
    prompt: str,
    system_message: str = "You are a helpful AI assistant.",
    reasoning_effort: str = "high",
    model_name: str = "o1",
    max_retries: int = 3,
    retry_delay: int = 5
) -> str:
    """
    Generate completions using OpenAI's API with reasoning models.
    
    Args:
        prompt: The user prompt to send to the model
        system_message: Optional system message to set the context
        reasoning_effort: Level of reasoning effort ("low", "medium", "high")
        model_name: The model to use (default: "gpt-4o")
        max_retries: Maximum number of retry attempts on API error
        retry_delay: Delay between retries in seconds
        
    Returns:
        The generated text response
    """
    import openai
    import time
    import logging
    from django.conf import settings

    logger = logging.getLogger(__name__)
    
    # Configure API key
    if hasattr(settings, 'AZURE_OPENAI_API_KEY') and settings.AZURE_OPENAI_API_KEY:
        # Azure OpenAI setup
        client = openai.AzureOpenAI(
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT
        )
        # Map model names to their Azure deployment IDs if needed
        azure_model_map = {
            "gpt-4o": settings.AZURE_GPT4O_DEPLOYMENT_NAME,
            "gpt-4-turbo": settings.AZURE_GPT4_TURBO_DEPLOYMENT_NAME,
            "gpt-3.5-turbo": settings.AZURE_GPT35_TURBO_DEPLOYMENT_NAME
        }
        model = azure_model_map.get(model_name, model_name)
    else:
        # Standard OpenAI setup
        client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
        model = model_name
    
    # Validate reasoning_effort
    valid_efforts = ["low", "medium", "high"]
    if reasoning_effort not in valid_efforts:
        logger.warning(f"Invalid reasoning_effort '{reasoning_effort}'. Using 'high' instead.")
        reasoning_effort = "high"
    
    # Prepare messages
    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": prompt}
    ]
    
    # Try to generate completion with retries
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                reasoning_effort=reasoning_effort
            )
            return response.choices[0].message.content
            
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"API error: {str(e)}. Retrying in {retry_delay} seconds... (Attempt {attempt + 1}/{max_retries})")
                time.sleep(retry_delay)
            else:
                logger.error(f"Failed after {max_retries} attempts: {str(e)}")
                raise
    
    # This line should never be reached due to the raise in the exception handler
    return "Error generating response." 