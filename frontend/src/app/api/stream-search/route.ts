import { NextRequest, NextResponse } from 'next/server';
import { FIREBASE_CONFIG } from '@/lib/constants';
import { getFunctions, connectFunctionsEmulator } from 'firebase/functions';
import { initializeApp } from 'firebase/app';

// Initialize Firebase for server-side
const app = initializeApp(FIREBASE_CONFIG);
const functions = getFunctions(app);

// We need to explicitly connect to the emulator on the server side
if (process.env.NODE_ENV === 'development') {
  try {
    // Default to port 5002 as configured in firebase.json
    const emulatorPort = parseInt(process.env.FUNCTIONS_EMULATOR_PORT || '5002', 10);
    connectFunctionsEmulator(functions, 'localhost', emulatorPort);
    console.log(`Connected to Firebase Functions emulator on port ${emulatorPort} in API route`);
  } catch (error) {
    console.error('Failed to connect to emulator:', error);
  }
}

export async function POST(request: NextRequest) {
  console.log('API route stream-search called');
  
  try {
    const reqBody = await request.json();
    console.log('Received request body:', reqBody);
    
    // In development, call the emulator directly
    if (process.env.NODE_ENV === 'development') {
      const region = 'us-central1';
      const projectId = FIREBASE_CONFIG.projectId || 'crystal-local';
      
      // Default to port 5002 as configured in firebase.json
      const emulatorPort = process.env.FUNCTIONS_EMULATOR_PORT || 5002;
      const url = `http://localhost:${emulatorPort}/${projectId}/${region}/stream_search_datasets`;
      
      console.log('Forwarding request to:', url);
      
      try {
        // Forward the request to the Firebase emulator
        const response = await fetch(url, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(reqBody),
        });
        
        console.log('Firebase response status:', response.status);
        
        if (!response.ok) {
          const errorText = await response.text();
          console.error('Error from Firebase:', errorText);
          return NextResponse.json({ error: errorText || 'Firebase function error' }, 
            { status: response.status });
        }
        
        // Get the response as a ReadableStream to enable streaming
        const responseStream = response.body;
        
        // Return a streaming response
        return new Response(responseStream, {
          headers: {
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
          },
        });
      } catch (fetchError) {
        console.error('Error connecting to emulator on port', emulatorPort, fetchError);
        return NextResponse.json({ 
          error: `Failed to connect to Firebase emulator on port ${emulatorPort}` 
        }, { status: 500 });
      }
      }
    } else {
      // Production handling code would go here
      return NextResponse.json({ error: "Production mode not implemented" }, { status: 501 });
    }
  } catch (error) {
    console.error('Error in stream-search API route:', error);
    return NextResponse.json(
      { error: 'Failed to process stream search request' },
      { status: 500 }
    );
  }
}