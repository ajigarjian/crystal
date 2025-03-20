import { NextRequest, NextResponse } from 'next/server';

export async function GET(request: NextRequest) {
  try {
    // Get query parameters
    const searchParams = request.nextUrl.searchParams;
    
    // Use 127.0.0.1 instead of localhost
    const backendUrl = 'http://127.0.0.1:8000';
    const fullUrl = `${backendUrl}/api/datasets/?${searchParams.toString()}`;
    
    console.log(`[API Route] Proxying request to: ${fullUrl}`);
    
    // Forward the request to Django
    const response = await fetch(fullUrl, {
      // Add a timeout to avoid hanging if Django is unreachable
      signal: AbortSignal.timeout(5000)
    });
    
    console.log(`[API Route] Django response status: ${response.status}`);
    
    if (!response.ok) {
      // Try to get error details from response
      let errorDetails = '';
      try {
        const errorData = await response.text();
        errorDetails = errorData;
        console.error(`[API Route] Django error response: ${errorDetails}`);
      } catch (e) {
        console.error('[API Route] Could not parse error response');
      }
      
      throw new Error(`Backend error: ${response.status} - ${errorDetails}`);
    }
    
    // Get the data from Django
    const data = await response.json();
    console.log('[API Route] Successfully received data from Django');
    
    // Return the data to the frontend
    return NextResponse.json(data);
  } catch (error) {
    console.error('[API Route] Error in datasets API route:', error);
    
    // Provide a more helpful error message
    let errorMessage = 'Failed to connect to Django backend';
    if (error.code === 'ECONNREFUSED') {
      errorMessage = 'Could not connect to Django server. Make sure it\'s running on http://127.0.0.1:8000';
    }
    
    return NextResponse.json(
      { 
        error: errorMessage,
        details: error.message
      },
      { status: 500 }
    );
  }
}
