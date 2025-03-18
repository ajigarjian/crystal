import { NextRequest } from 'next/server';

export async function POST(request: NextRequest) {
  try {
    // Get the request body
    const body = await request.json();
    console.log('Streaming search request body:', body);
    
    // Use explicit IPv4 address instead of localhost with the correct path
    // The path is /api/stream-search/ because in crystalproject/urls.py, 
    // factchecker.urls is included under the 'api/' prefix
    const backendUrl = 'http://127.0.0.1:8000/api/stream-search/';
    console.log('Forwarding streaming request to:', backendUrl);
    
    // Get the base URL of the request
    const origin = request.headers.get('origin') || '';
    console.log('Request origin:', origin);
    
    // Create a new ReadableStream for forwarding the Django response
    const encoder = new TextEncoder();
    
    // Create a stream that will be sent to the client
    const stream = new ReadableStream({
      async start(controller) {
        try {
          // Make the request to Django
          const response = await fetch(backendUrl, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify(body),
          });
          
          if (!response.ok || !response.body) {
            let errorMessage = `Backend error: ${response.status}`;
            try {
              const errorText = await response.text();
              errorMessage += ` - ${errorText}`;
            } catch (e) {
              // Ignore error reading response
            }
            
            // Send error message to client and close the stream
            const errorData = JSON.stringify({ type: 'error', message: errorMessage }) + '\n';
            controller.enqueue(encoder.encode(errorData));
            controller.close();
            return;
          }
          
          // Create a reader from Django's response
          const reader = response.body.getReader();
          
          // Process the stream from Django
          while (true) {
            const { done, value } = await reader.read();
            if (done) {
              break;
            }
            
            // Forward the chunk directly to the client
            controller.enqueue(value);
          }
          
          // Close the stream when Django is done
          controller.close();
        } catch (error: any) {
          console.error('Error in streaming process:', error);
          
          // Send error to client
          const errorData = JSON.stringify({
            type: 'error',
            message: `Internal server error: ${error.message || String(error)}`
          }) + '\n';
          controller.enqueue(encoder.encode(errorData));
          controller.close();
        }
      }
    });
    
    // Return a streaming response
    return new Response(stream, {
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'Access-Control-Allow-Origin': origin,
      },
    });
  } catch (error: any) {
    console.error('Error setting up streaming search:', error);
    
    // Return an error response if we can't even start the stream
    const encoder = new TextEncoder();
    const errorData = JSON.stringify({
      type: 'error',
      message: `Failed to set up streaming: ${error.message || String(error)}`
    }) + '\n';
    
    return new Response(encoder.encode(errorData), {
      status: 500,
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
      },
    });
  }
} 