// Base API URL - adjust based on your setup
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api';

// Function to process a natural language query
export async function processQuery(query: string, options = {}) {
  const defaultOptions = {
    top_n: 3,
    search_method: 'vector',
    relevance_threshold: 0.3
  };
  
  const requestOptions = { ...defaultOptions, ...options, query };
  
  try {
    const response = await fetch(`${API_BASE_URL}/query/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(requestOptions),
    });
    
    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.error || 'Failed to process query');
    }
    
    return await response.json();
  } catch (error) {
    console.error('API error:', error);
    throw error;
  }
}