import { NextRequest, NextResponse } from 'next/server';
import { SSR_ENABLED, FIREBASE_CONFIG } from '../../../lib/constants';

export const runtime = 'edge';

export async function POST(request: NextRequest) {
  try {
    const reqBody = await request.json();
    
    // Get the region and project ID
    const region = 'us-central1';
    const projectId = FIREBASE_CONFIG.projectId;
    const baseUrl = `https://${region}-${projectId}.cloudfunctions.net`;
    const url = `${baseUrl}/register_waitlist`;
    
    // Forward the request to the Cloud Function
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(reqBody),
    });
    
    if (!response.ok) {
      const errorData = await response.json();
      return NextResponse.json(
        { error: errorData.error || 'Failed to register' },
        { status: response.status }
      );
    }
    
    const result = await response.json();
    return NextResponse.json(result);
  } catch (error) {
    console.error('Error in waitlist API route:', error);
    return NextResponse.json(
      { error: 'Failed to process waitlist request' },
      { status: 500 }
    );
  }
}