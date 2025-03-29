import { NextRequest, NextResponse } from 'next/server';
import { FIREBASE_CONFIG } from '../../../lib/constants';

export const runtime = 'edge';

export async function POST(request: NextRequest) {
  try {
    const reqBody = await request.json();
    
    // Different handling for development vs production
    let url = '';
    if (process.env.NODE_ENV === 'development') {
      // In development, call the emulator directly
      const region = 'us-central1';
      const projectId = FIREBASE_CONFIG.projectId || 'crystal-local';
      
      // Default to port 5002 as configured in firebase.json
      const emulatorPort = process.env.FUNCTIONS_EMULATOR_PORT || 5002;
      url = `http://localhost:${emulatorPort}/${projectId}/${region}/stream_analyze`;
      console.log('Forwarding to emulator:', url);
      
      try {
        // Try the connection
        const response = await fetch(url, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(reqBody),
        });
        
        // Check for errors in the response
        if (!response.ok) {
          const errorText = await response.text();
          console.error('Error from Firebase:', errorText);
          return NextResponse.json({ error: errorText || 'Firebase function error' }, 
            { status: response.status });
        }
        
        // Get the response and create a stream
        const stream = response.body;
        
        // Return the stream response
        return new Response(stream, {
          headers: {
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
          },
        });
      } catch (fetchError) {
        console.error(`Error connecting to emulator on port ${emulatorPort}:`, fetchError);
        return NextResponse.json({ 
          error: `Failed to connect to Firebase emulator on port ${emulatorPort}` 
        }, { status: 500 });
      }
      }
    } else {
      // Production URL
      const region = 'us-central1';
      const projectId = FIREBASE_CONFIG.projectId;
      const baseUrl = `https://${region}-${projectId}.cloudfunctions.net`;
      url = `${baseUrl}/stream_analyze`;
    }
    
    // Forward the request to the Cloud Function
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(reqBody),
    });
    
    // Check for errors in the response
    if (!response.ok) {
      const errorText = await response.text();
      console.error('Error from Firebase:', errorText);
      return NextResponse.json({ error: errorText || 'Firebase function error' }, 
        { status: response.status });
    }
    
    // Get the response and create a stream
    const stream = response.body;
    
    // Return the stream response
    return new Response(stream, {
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
      },
    });
  } catch (error) {
    console.error('Error in stream-analyze API route:', error);
    return NextResponse.json(
      { error: 'Failed to process stream analyze request' },
      { status: 500 }
    );
  }
}