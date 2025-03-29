import { initializeApp } from "firebase/app";
import { getFunctions, httpsCallable, connectFunctionsEmulator } from "firebase/functions";
import { getFirestore, connectFirestoreEmulator } from "firebase/firestore";
import { FIREBASE_CONFIG, SSR_ENABLED, API_ENDPOINTS } from './constants';

// Initialize Firebase only on client side
const app = typeof window !== 'undefined' ? initializeApp(FIREBASE_CONFIG) : null;

// Initialize Cloud Firestore and get a reference to the service
export const db = typeof window !== 'undefined' ? getFirestore(app) : null;

// Initialize Cloud Functions
export const functions = typeof window !== 'undefined' ? getFunctions(app) : null;

// Set up emulator if in development
if (typeof window !== 'undefined' && process.env.NODE_ENV === 'development') {
  console.log(`Using Firebase Functions emulator...`);
  connectFunctionsEmulator(functions, 'localhost', 5002);
  connectFirestoreEmulator(db, 'localhost', 8080);
}

// Export a helper for calling the waitlist registration function
export const registerWaitlist = async (data: { email: string, first_name: string }) => {
  // Get the region and project ID from the functions instance
  const region = functions?.region || 'us-central1';
  const projectId = FIREBASE_CONFIG.projectId || 'crystal-local';
  
  // Construct the URL for the HTTP function
  let baseUrl = '';
  if (process.env.NODE_ENV === 'development') {
    // Use emulator URL in development
    baseUrl = `http://localhost:5002/${projectId}/${region}`;
  } else {
    // Use production URL in production
    baseUrl = `https://${region}-${projectId}.cloudfunctions.net`;
  }
  
  const url = `${baseUrl}/register_waitlist`;
  
  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      mode: 'cors',
      credentials: 'omit', // Don't send credentials
      body: JSON.stringify(data),
    });
    
    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.error || 'Failed to register');
    }
    
    const result = await response.json();
    return { data: result };
  } catch (error: any) {
    console.error('Error calling register_waitlist:', error);
    throw new Error(error.message || 'Failed to register');
  }
};

// Export a helper for calling the stream search datasets function
export const streamSearchDatasets = async (
  data: {
    query: string;
    search_method: string | null;
    similarity_threshold: number;
    max_results?: number;
    census_max_results?: number;
    relevance_threshold?: number;
  },
  onChunk?: (chunk: any) => void // Make callback optional
) => {
  // Create a default onChunk function if none is provided
  const processChunk = typeof onChunk === 'function' 
    ? onChunk 
    : (chunk: any) => {
        console.log('Received chunk:', chunk);
        // Default implementation just logs the chunk
      };

  // Use the API endpoint directly
  let url = '';
  if (process.env.NODE_ENV === 'development') {
    // In development, use the Next.js API route
    console.log("Development environment detected, using emulator URL");
    
    // Make sure to use the absolute URL for the API route
    // Get base URL - crucial for making the request to the correct host
    const baseUrl = window.location.origin;
    url = `${baseUrl}${API_ENDPOINTS.streamSearch}`;
    console.log("Using API endpoint:", url);
  } else {
    // Use production URL in production
    const region = functions?.region || 'us-central1';
    const projectId = FIREBASE_CONFIG.projectId || 'crystal-local';
    url = `https://${region}-${projectId}.cloudfunctions.net/stream_search_datasets`;
    console.log("Using production URL:", url);
  }
  
  console.log("Full request URL:", url);
  
  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(data),
    });
    
    if (!response.ok) {
      const errorText = await response.text();
      console.error('Error response:', errorText);
      throw new Error(errorText || 'Failed to search datasets');
    }
    
    // For streaming responses, we need to process the response as a stream
    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error('Stream reader not available');
    }
    
    // Process the stream and parse each chunk as JSON
    const decoder = new TextDecoder();
    let buffer = '';
    const chunks = []; // Store processed chunks to return
    
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      
      // Decode the chunk and add it to our buffer
      buffer += decoder.decode(value, { stream: true });
      
      // Split the buffer by newlines to get individual JSON objects
      const lines = buffer.split('\n');
      
      // Process all complete lines
      for (let i = 0; i < lines.length - 1; i++) {
        const line = lines[i].trim();
        if (line) {
          try {
            const data = JSON.parse(line);
            // Call the callback with each chunk of data
            processChunk(data);
            chunks.push(data);
          } catch (e) {
            console.error('Error parsing JSON:', e, 'Line:', line);
          }
        }
      }
      
      // Keep the last (potentially incomplete) line in the buffer
      buffer = lines[lines.length - 1];
    }
    
    // Process any remaining data in the buffer
    if (buffer.trim()) {
      try {
        const data = JSON.parse(buffer.trim());
        processChunk(data);
        chunks.push(data);
      } catch (e) {
        console.error('Error parsing final JSON:', e);
      }
    }
    
    return chunks; // Return all processed chunks
  } catch (error: any) {
    console.error('Error calling stream_search_datasets:', error);
    throw new Error(error.message || 'Failed to search datasets');
  }
};

// Add a helper function to process dataset chunks for UI display
export const processDatasetChunks = (chunks: any[]) => {
  // Extract all datasets, including non-relevant ones
  const datasets = chunks
    .filter(chunk => chunk.type === 'dataset' || 
                    (chunk.type === 'dataset_update' && chunk.data))
    .map(chunk => {
      // For dataset_update chunks, use the updated data which includes relevance score
      if (chunk.type === 'dataset_update') {
        return {
          ...chunk.data,
          timestamp: chunk.timestamp
        };
      }
      // For initial dataset chunks
      return {
        ...chunk.data,
        timestamp: chunk.timestamp
      };
    });
  
  // Get the final status from the complete chunk
  const completeChunk = chunks.find(chunk => chunk.type === 'complete');
  const finalStatus = completeChunk ? completeChunk.message : '';
  
  // Get all status messages for progress display
  const statusMessages = chunks
    .filter(chunk => chunk.type === 'status' || 
                    chunk.type === 'discovery' || 
                    chunk.type === 'phase_complete' ||
                    chunk.type === 'complete')
    .map(chunk => ({
      message: chunk.message,
      timestamp: chunk.timestamp,
      type: chunk.type
    }));
  
  return {
    datasets,
    finalStatus,
    statusMessages
  };
};

// Add this function after your other export functions
export const submitFeedback = async (data: {
  feedback_type: string;
  title: string;
  description: string;
  email?: string;
  page_url: string;
  tags?: string[];
  metadata?: any;
}) => {
  console.log("Starting submitFeedback with data:", data);
  
  const region = functions?.region || 'us-central1';
  const projectId = FIREBASE_CONFIG.projectId || 'crystal-local';
  
  let baseUrl = '';
  if (process.env.NODE_ENV === 'development') {
    baseUrl = `http://localhost:5002/${projectId}/${region}`;
    console.log("Using development URL:", baseUrl);
  } else {
    baseUrl = `https://${region}-${projectId}.cloudfunctions.net`;
    console.log("Using production URL:", baseUrl);
  }
  
  const url = `${baseUrl}/submit_feedback`;
  console.log("Full request URL:", url);
  
  try {
    console.log("Making fetch request...");
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      mode: 'cors',
      credentials: 'omit', // Don't send credentials
      body: JSON.stringify(data),
    });
    
    console.log("Fetch response received. Status:", response.status);
    
    let responseText;
    try {
      responseText = await response.text();
      console.log("Response text:", responseText);
    } catch (textError) {
      console.error("Error reading response text:", textError);
      responseText = "Unable to read response";
    }
    
    if (!response.ok) {
      let errorData;
      try {
        errorData = JSON.parse(responseText);
      } catch (jsonError) {
        console.error("Error parsing JSON response:", jsonError);
        errorData = { error: responseText || "Unknown error" };
      }
      throw new Error(errorData.error || 'Failed to submit feedback');
    }
    
    let result;
    try {
      result = JSON.parse(responseText);
    } catch (jsonError) {
      console.error("Error parsing success response:", jsonError);
      throw new Error("Invalid response format");
    }
    
    console.log("Submission successful:", result);
    return { data: result };
  } catch (error: any) {
    console.error('Error submitting feedback:', error);
    throw new Error(error.message || 'Failed to submit feedback');
  }
};

// Update warmFunctions to include the new function
export const warmFunctions = async () => {
  if (process.env.NODE_ENV === 'development') {
    console.log('Skipping function warming in development mode');
    return;
  }
  
  try {
    // Get the region and project ID
    const region = functions?.region || 'us-central1';
    const projectId = FIREBASE_CONFIG.projectId || 'crystal-local';
    const baseUrl = `https://${region}-${projectId}.cloudfunctions.net`;
    
    // List of functions to warm
    const functionsToWarm = [
      'register_waitlist',
      'stream_search_datasets',
      'stream_analyze',
      'submit_feedback'
    ];
    
    // Warm each function with a minimal payload
    functionsToWarm.forEach(async (functionName) => {
      const url = `${baseUrl}/${functionName}`;
      
      try {
        await fetch(url, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          mode: 'cors',
          credentials: 'omit', // Don't send credentials
          body: JSON.stringify({ warming: true }),
        });
        console.log(`Warmed function: ${functionName}`);
      } catch (e) {
        // Silently ignore errors during warming
      }
    });
  } catch (error) {
    // Don't let warming errors affect the user experience
    console.log('Function warming failed silently');
  }
};

// Export a helper for calling the stream analyze datasets function
export const streamAnalyzeDatasets = async (
  params: {
    query: string;
    datasets: Dataset[];
  },
  processChunk: (data: any) => void
) => {
  try {
    // Get the base URL
    let url = '';
    if (process.env.NODE_ENV === 'development') {
      // For development, use the API route with the correct origin
      const baseUrl = window.location.origin;
      url = `${baseUrl}${API_ENDPOINTS.streamAnalyze}`;
      console.log("Using API endpoint:", url);
    } else {
      // Production URL
      const region = functions?.region || 'us-central1';
      const projectId = FIREBASE_CONFIG.projectId || 'crystal-local';
      url = `https://${region}-${projectId}.cloudfunctions.net/stream_analyze`;
    }
    
    console.log("Full request URL:", url);
    
    // Prepare the payload with the correct structure
    const payload = {
      query: params.query,
      dataset_ids: params.datasets.map(dataset => dataset.id)
    };
    
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });
    
    if (!response.ok) {
      const errorText = await response.text();
      console.error('Error response:', errorText);
      throw new Error(errorText || 'Failed to analyze datasets');
    }
    
    if (!response.body) {
      throw new Error('Response body is null');
    }

    // Process the stream
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      
      if (done) break;

      // Append new data to buffer and process complete lines
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || ''; // Keep the last incomplete line

      for (const line of lines) {
        if (line.trim()) {
          try {
            // Remove the "data: " prefix if it exists
            const jsonStr = line.startsWith('data: ') ? line.slice(5) : line;
            const data = JSON.parse(jsonStr);
            processChunk(data);
          } catch (e) {
            console.warn('Failed to parse line:', line);
            processChunk({
              type: 'error',
              message: 'Failed to parse server response',
              error: String(e)
            });
          }
        }
      }
    }

    // Process any remaining data in buffer
    if (buffer.trim()) {
      try {
        const jsonStr = buffer.startsWith('data: ') ? buffer.slice(5) : buffer;
        const data = JSON.parse(jsonStr);
        processChunk(data);
      } catch (e) {
        console.warn('Failed to parse remaining buffer:', buffer);
      }
    }

  } catch (error) {
    console.error('Error in stream analyze:', error);
    throw error;
  }
}; 