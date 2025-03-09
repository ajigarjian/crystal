import os
import openai
from typing import Dict, List, Any, Optional

# Try to load Azure OpenAI provider, otherwise fall back to OpenAI
try:
    AZURE_OPENAI_KEY = os.environ["AZURE_OPENAI_API_KEY"]
    AZURE_OPENAI_ENDPOINT = os.environ["AZURE_OPENAI_ENDPOINT"]
    AZURE_OPENAI_DEPLOYMENT = os.environ["AZURE_OPENAI_DEPLOYMENT"]
    provider = "azure"

except KeyError:
    print("Error loading Azure OpenAI provider. Falling back to native OpenAI.")
    OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
    provider = "openai"

def get_openai_client():
    """
    Create and return an OpenAI client configured for either OpenAI or Azure OpenAI.
        
    Returns:
        An OpenAI client
        A Deployment Name
    """
    # If the Azure OpenAI key is set, let's default to using that as a preferred OpenAI provider
    if provider == "azure":
        if not AZURE_OPENAI_ENDPOINT or not AZURE_OPENAI_DEPLOYMENT:
            raise ValueError("Azure endpoint and deployment name are required when using Azure OpenAI")
        
        # Configure for Azure OpenAI
        client = openai.AzureOpenAI(
            api_key=AZURE_OPENAI_KEY,
            api_version="2025-02-01-preview",  # Update this to the version you're using
            azure_endpoint=AZURE_OPENAI_ENDPOINT
        )
        return client, AZURE_OPENAI_DEPLOYMENT
    else:
        # Configure for regular OpenAI
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        return client, "gpt-4o"

def get_openai_embeddings_client():
    """
    Create and return an OpenAI embeddings client configured for either OpenAI or Azure OpenAI.
        
    Returns:
        An OpenAI client
        A Deployment Name
    """
    model = "text-embedding-3-small"

    # If the Azure OpenAI key is set, let's default to using that as a preferred OpenAI provider
    if provider == "azure":        
        # Configure for Azure OpenAI
        client = openai.AzureOpenAI(
            api_key=AZURE_OPENAI_KEY,
            api_version="2023-05-15",  # Hardcoded for text-embedding-3-small model
            azure_endpoint=AZURE_OPENAI_ENDPOINT
        )
        return client, model
    else:
        # Configure for regular OpenAI
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        return client, model

def create_embeddings(query):
    """
    Returns a new embeddings output from OpenAI.
    """
    client, deployment = get_openai_embeddings_client()

    response = client.embeddings.create(
        input=query,
        model=deployment
    )

    return response.data[0].embedding

def chat_completion(
    prompt: str, 
    system_message: str = "You are a helpful assistant.",
    temperature: float = 0.2,
    max_tokens: int = 800,
) -> str:
    """
    Get a chat completion from OpenAI or Azure OpenAI.
    
    Args:
        prompt: The user prompt
        system_message: The system message to use
        temperature: The temperature to use for generation
        max_tokens: Maximum tokens
        
    Returns:
        The generated text
    """
    client, deployment = get_openai_client()
    
    try:
        response = client.chat.completions.create(
            model=deployment,  # For Azure, this is the deployment name
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt}
            ],
            temperature=temperature,
            max_tokens=max_tokens
        )

        return response.choices[0].message.content

    except Exception as e:
        print(f"Error calling OpenAI API: {str(e)}")
        return f"Error generating response: {str(e)}" 