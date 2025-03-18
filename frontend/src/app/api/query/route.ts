import { NextRequest, NextResponse } from 'next/server';

export async function POST(request: NextRequest) {
  try {
    // Get the request body
    const body = await request.json();
    const query = body.query || 'unknown query';
    
    console.log(`[API Route] Processing mock query: "${query}"`);
    
    // Create mock dataset results
    const mockDatasets = [
      {
        id: "mock-dataset-1",
        title: "Air Quality Measurements in Major US Cities",
        description: "This dataset contains air quality measurements including PM2.5, PM10, and ozone levels across major US metropolitan areas.",
        similarity: 0.95,
        relevance_score: 0.95,
        organization_name: "epa-gov",
        organization_title: "Environmental Protection Agency",
        resources: [
          {
            id: "resource-1",
            name: "Air Quality Data 2023",
            url: "https://example.com/data.csv",
            description: "CSV file with air quality measurements",
            format: "CSV"
          }
        ],
        tags: ["air quality", "pollution", "environment", "health"],
        dataset_analysis: `This dataset is highly relevant to your query about "${query}". It contains comprehensive air quality measurements.`
      },
      {
        id: "mock-dataset-2",
        title: "Climate Change Impact on Urban Air Quality",
        description: "Analysis of how climate change affects air quality in urban environments over the past decade.",
        similarity: 0.85,
        relevance_score: 0.85,
        organization_name: "noaa-gov",
        organization_title: "National Oceanic and Atmospheric Administration",
        resources: [
          {
            id: "resource-2",
            name: "Climate and Air Quality Report",
            url: "https://example.com/report.pdf",
            description: "PDF report with analysis",
            format: "PDF"
          }
        ],
        tags: ["climate", "air quality", "urban", "research"],
        dataset_analysis: `This dataset provides insights into how climate change impacts air quality, relevant to your query about "${query}".`
      },
      {
        id: "mock-dataset-3",
        title: "Health Effects of Air Pollution",
        description: "Research data on the correlation between air pollution levels and respiratory health issues.",
        similarity: 0.78,
        relevance_score: 0.78,
        organization_name: "cdc-gov",
        organization_title: "Centers for Disease Control and Prevention",
        resources: [
          {
            id: "resource-3",
            name: "Health Data 2022",
            url: "https://example.com/health.xlsx",
            description: "Excel file with health statistics",
            format: "XLSX"
          }
        ],
        tags: ["health", "air pollution", "respiratory", "public health"],
        dataset_analysis: `This dataset examines health impacts of air pollution, which relates to your query about "${query}".`
      }
    ];
    
    // Add more mock datasets with decreasing relevance
    for (let i = 4; i <= 10; i++) {
      mockDatasets.push({
        id: `mock-dataset-${i}`,
        title: `Sample Dataset ${i}`,
        description: `This is a sample dataset #${i} that might be somewhat relevant to your query.`,
        similarity: Math.max(0.3, 0.9 - (i * 0.06)),
        relevance_score: Math.max(0.3, 0.9 - (i * 0.06)),
        organization_name: "sample-org",
        organization_title: "Sample Organization",
        resources: [
          {
            id: `resource-${i}`,
            name: `Resource ${i}`,
            url: `https://example.com/data${i}.json`,
            description: "Sample data file",
            format: "JSON"
          }
        ],
        tags: ["sample", "data", `tag-${i}`],
        dataset_analysis: `This dataset has some information that might be tangentially related to your query about "${query}".`
      });
    }
    
    // Create a mock response
    const mockResponse = {
      query: query,
      summary: {
        query: query,
        findings: `Found ${mockDatasets.length} datasets that might be relevant to your query about '${query}'.`
      },
      datasets: mockDatasets,
      execution_time: 0.5
    };
    
    console.log('[API Route] Returning mock query results');
    
    // Return the mock data
    return NextResponse.json(mockResponse);
  } catch (error) {
    console.error('[API Route] Error in mock query API route:', error);
    
    return NextResponse.json(
      { 
        error: 'Failed to process query',
        details: error.message,
        datasets: [] // Always include an empty datasets array
      },
      { status: 500 }
    );
  }
}