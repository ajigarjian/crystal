import { initializeApp } from "firebase/app";
import { getFunctions, httpsCallable, connectFunctionsEmulator } from "firebase/functions";
import { getFirestore, connectFirestoreEmulator } from "firebase/firestore";

// Your web app's Firebase configuration
// For Firebase JS SDK v7.20.0 and later, measurementId is optional
const firebaseConfig = {
    apiKey: "AIzaSyC3KIK0ol5TquNaz6-DyVoxzijDNySgrq4",
    authDomain: "crystal-2f87e.firebaseapp.com",
    projectId: "crystal-2f87e",
    storageBucket: "crystal-2f87e.firebasestorage.app",
    messagingSenderId: "422374862387",
    appId: "1:422374862387:web:1a11af2b205c777173bd46",
    measurementId: "G-1CFM4WMH4B"
  };

// Initialize Firebase
const app = initializeApp(firebaseConfig);

// Initialize Cloud Firestore and get a reference to the service
export const db = getFirestore(app);

// Initialize Cloud Functions
export const functions = getFunctions(app);

// Set up emulator if in development
if (process.env.NODE_ENV === 'development') {
  console.log(`Using Firebase Functions emulator...`);
  connectFunctionsEmulator(functions, 'localhost', 5001);
  connectFirestoreEmulator(db, 'localhost', 8080);
}

// Export a helper for calling the waitlist registration function
export const registerWaitlist = async (data: { email: string, first_name: string }) => {
  // Get the region and project ID from the functions instance
  const region = functions.region || 'us-central1';
  const projectId = firebaseConfig.projectId;
  
  // Construct the URL for the HTTP function
  let baseUrl = '';
  if (process.env.NODE_ENV === 'development') {
    // Use emulator URL in development
    baseUrl = `http://localhost:5001/${projectId}/${region}`;
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
        'Access-Control-Allow-Origin': '*',
      },
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

  // Get the region and project ID from the functions instance
  const region = functions.region || 'us-central1';
  const projectId = firebaseConfig.projectId;
  
  // Construct the URL for the HTTP function
  let baseUrl = '';
  if (process.env.NODE_ENV === 'development') {
    // Use emulator URL in development
    baseUrl = `http://localhost:5001/${projectId}/${region}`;
  } else {
    // Use production URL in production
    baseUrl = `https://${region}-${projectId}.cloudfunctions.net`;
  }
  
  const url = `${baseUrl}/stream_search_datasets`;
  
  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
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
            // Extract the JSON part if the line starts with 'data:'
            const jsonStr = line.startsWith('data:') 
              ? line.substring(5).trim() 
              : line;
            
            const data = JSON.parse(jsonStr);
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
        // Extract the JSON part if the line starts with 'data:'
        const jsonStr = buffer.trim().startsWith('data:') 
          ? buffer.trim().substring(5).trim() 
          : buffer.trim();
        
        const data = JSON.parse(jsonStr);
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
  
  const region = functions.region || 'us-central1';
  const projectId = firebaseConfig.projectId;
  
  let baseUrl = '';
  if (process.env.NODE_ENV === 'development') {
    baseUrl = `http://localhost:5001/${projectId}/${region}`;
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
        'Access-Control-Allow-Origin': '*',
      },
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
    const region = functions.region || 'us-central1';
    const projectId = firebaseConfig.projectId;
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
            'Access-Control-Allow-Origin': '*',
          },
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
  data: {
    query: string;
    dataset_ids: string[];
  },
  onChunk?: (chunk: any) => void // Callback for streaming updates
) => {
  // Create a default onChunk function if none is provided
  const processChunk = typeof onChunk === 'function' 
    ? onChunk 
    : (chunk: any) => {
        console.log('Received analysis chunk:', chunk);
      };

  // Get the region and project ID from the functions instance
  const region = functions.region || 'us-central1';
  const projectId = firebaseConfig.projectId;
  
  // Construct the URL for the HTTP function
  let baseUrl = '';
  if (process.env.NODE_ENV === 'development') {
    baseUrl = `http://localhost:5001/${projectId}/${region}`;
  } else {
    baseUrl = `https://${region}-${projectId}.cloudfunctions.net`;
  }
  
  const url = `${baseUrl}/stream_analyze`;

  // If no dataset IDs, throw an error
  if (!data.dataset_ids || data.dataset_ids.length === 0) {
    console.error('No valid dataset IDs provided for analysis');
    throw new Error('No valid dataset IDs provided for analysis');
  }

  // Build payload that matches what the Python function expects
  const payload = {
    query: data.query,
    dataset_ids: data.dataset_ids
  };
  
  console.log('Sending analysis request with payload:', payload);
  
  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
      },
      body: JSON.stringify(payload),
    });
    
    if (!response.ok) {
      const errorText = await response.text();
      console.error('Error response:', errorText);
      throw new Error(errorText || 'Failed to analyze datasets');
    }
    
    // For streaming responses, read as a stream
    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error('Stream reader not available');
    }
    
    const decoder = new TextDecoder();
    let buffer = '';
    const chunks = [];
    
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      for (let i = 0; i < lines.length - 1; i++) {
        const line = lines[i].trim();
        if (line) {
          try {
            // Extract the JSON part if the line starts with 'data:'
            const jsonStr = line.startsWith('data:') 
              ? line.substring(5).trim() 
              : line;
            
            const parsed = JSON.parse(jsonStr);
            processChunk(parsed);
            chunks.push(parsed);
          } catch (e) {
            console.error('Error parsing JSON:', e, 'Line:', line);
          }
        }
      }
      buffer = lines[lines.length - 1];
    }
    
    if (buffer.trim()) {
      try {
        // Extract the JSON part if the line starts with 'data:'
        const jsonStr = buffer.trim().startsWith('data:') 
          ? buffer.trim().substring(5).trim() 
          : buffer.trim();
        
        const parsed = JSON.parse(jsonStr);
        processChunk(parsed);
        chunks.push(parsed);
      } catch (e) {
        console.error('Error parsing final JSON:', e);
      }
    }
    
    return chunks;
  } catch (error: any) {
    console.error('Error calling stream_analyze:', error);
    throw new Error(error.message || 'Failed to analyze datasets');
  }
}; 