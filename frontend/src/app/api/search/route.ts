import { NextRequest, NextResponse } from 'next/server';

export async function POST(request: NextRequest) {
  try {
    // Get the request body
    const body = await request.json();
    console.log('Search request body:', body);
    
    // Use explicit IPv4 address instead of localhost
    const backendUrl = 'http://127.0.0.1:8000/api/search/';
    console.log('Forwarding request to:', backendUrl);
    
    const response = await fetch(backendUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    });

    // If the response is not ok, throw an error
    if (!response.ok) {
      const errorText = await response.text();
      console.error(`Error from backend: ${response.status} ${response.statusText}`, errorText);
      return NextResponse.json(
        { error: `Backend error: ${response.status} ${response.statusText}`, details: errorText },
        { status: response.status }
      );
    }

    // Parse the response as JSON
    const data = await response.json();
    console.log('Search response received:', data);
    
    // Return the data
    return NextResponse.json(data);
  } catch (error) {
    console.error('Error in search API route:', error);
    return NextResponse.json(
      { error: `Internal server error: ${error.message}`, stack: error.stack },
      { status: 500 }
    );
  }
}
