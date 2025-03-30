"use client";

import { Button } from "@/components/ui/button";
import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import Link from "next/link";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

// Placeholder dataset structure
interface Dataset {
  id: string;
  title: string;
  description: string;
  organization: string;
  resources?: Array<{
    name: string;
    url: string;
  }>;
  lastUpdated?: string;
  tags?: string[];
}

export default function DatasetsPage() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [selectedDataset, setSelectedDataset] = useState<Dataset | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    // Simulate loading datasets from API
    setTimeout(() => {
      const mockDatasets: Dataset[] = [
        {
          id: "1",
          title: "NYC Air Quality Data (2018-2023)",
          description: "Comprehensive air quality measurements across all NYC boroughs, including PM2.5, Ozone, and NO2 levels.",
          organization: "NYC Department of Environmental Protection",
          lastUpdated: "2023-12-15",
          tags: ["air-quality", "environment", "public-health", "new-york"]
        },
        {
          id: "2",
          title: "San Francisco Housing Prices (2010-2023)",
          description: "Median housing prices by neighborhood in San Francisco, including rental and ownership data.",
          organization: "San Francisco Housing Authority",
          lastUpdated: "2023-11-30",
          tags: ["housing", "real-estate", "san-francisco", "economics"]
        },
        {
          id: "3",
          title: "Chicago Public School Vaccination Rates",
          description: "Vaccination rates for required immunizations across Chicago public schools by neighborhood.",
          organization: "Chicago Department of Public Health",
          lastUpdated: "2023-10-22",
          tags: ["health", "education", "vaccines", "chicago"]
        },
        {
          id: "4",
          title: "Boston Public Transit Ridership (2015-2023)",
          description: "Monthly ridership statistics for Boston's public transportation system, including pre and post-COVID comparisons.",
          organization: "Massachusetts Bay Transportation Authority",
          lastUpdated: "2023-12-01",
          tags: ["transportation", "transit", "boston", "covid-19"]
        },
        {
          id: "5",
          title: "Los Angeles Urban Green Space Distribution",
          description: "Mapping of parks, green spaces, and tree coverage across Los Angeles neighborhoods with asthma rate correlations.",
          organization: "LA Parks and Recreation Department",
          lastUpdated: "2023-09-28",
          tags: ["environment", "urban-planning", "health", "los-angeles"]
        }
      ];
      
      setDatasets(mockDatasets);
      setIsLoading(false);
    }, 1500);
  }, []);

  const handleDatasetSelect = (dataset: Dataset) => {
    setSelectedDataset(dataset);
  };

  const handleAnalyze = () => {
    // This would normally navigate to a chat interface with the dataset loaded
    if (selectedDataset) {
      window.location.href = `/beta?dataset=${selectedDataset.id}`;
    }
  };

  return (
    <div className="flex min-h-screen bg-neutral-50 dark:bg-neutral-950 p-4">
      <div className="w-full max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex justify-between items-center mb-8">
          <div className="flex items-center">
            <Link href="/">
              <Button variant="ghost" className="mr-4">
                <svg 
                  xmlns="http://www.w3.org/2000/svg" 
                  width="24" 
                  height="24" 
                  viewBox="0 0 24 24" 
                  fill="none" 
                  stroke="currentColor" 
                  strokeWidth="2" 
                  strokeLinecap="round" 
                  strokeLinejoin="round"
                  className="mr-2"
                >
                  <path d="m12 19-7-7 7-7"/>
                  <path d="M19 12H5"/>
                </svg>
                Back
              </Button>
            </Link>
            <h1 className="text-3xl font-bold">Dataset Catalog</h1>
          </div>
          
          <Link href="/beta">
            <Button variant="outline">New Query</Button>
          </Link>
        </div>
        
        {/* Main content */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* Datasets List */}
          <div className="md:col-span-1">
            <Card>
              <CardHeader>
                <CardTitle>Available Datasets</CardTitle>
              </CardHeader>
              <CardContent>
                {isLoading ? (
                  <div className="space-y-2">
                    {[1, 2, 3, 4].map((i) => (
                      <div key={i} className="h-16 bg-gray-200 dark:bg-gray-800 animate-pulse rounded-md"></div>
                    ))}
                  </div>
                ) : (
                  <div className="space-y-2">
                    {datasets.map((dataset) => (
                      <div 
                        key={dataset.id}
                        onClick={() => handleDatasetSelect(dataset)}
                        className={`p-3 rounded-md cursor-pointer transition-colors ${
                          selectedDataset?.id === dataset.id 
                            ? 'bg-primary/10 border border-primary/30' 
                            : 'hover:bg-gray-100 dark:hover:bg-gray-800'
                        }`}
                      >
                        <h3 className="font-medium truncate">{dataset.title}</h3>
                        <p className="text-sm text-gray-500 dark:text-gray-400 truncate">
                          {dataset.organization}
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
          
          {/* Dataset Details */}
          <div className="md:col-span-2">
            <Card className="h-full">
              {!selectedDataset ? (
                <div className="h-full flex items-center justify-center p-8 text-center text-gray-500">
                  <div>
                    <h3 className="text-xl font-medium mb-2">Select a dataset</h3>
                    <p>Choose a dataset from the list to view details and analyze it</p>
                  </div>
                </div>
              ) : (
                <>
                  <CardHeader>
                    <CardTitle>{selectedDataset.title}</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <Tabs defaultValue="overview">
                      <TabsList>
                        <TabsTrigger value="overview">Overview</TabsTrigger>
                        <TabsTrigger value="resources">Resources</TabsTrigger>
                      </TabsList>
                      
                      <TabsContent value="overview" className="space-y-4">
                        <div>
                          <h3 className="text-lg font-medium mb-1">Description</h3>
                          <p className="text-gray-700 dark:text-gray-300">{selectedDataset.description}</p>
                        </div>
                        
                        <div>
                          <h3 className="text-lg font-medium mb-1">Organization</h3>
                          <p className="text-gray-700 dark:text-gray-300">{selectedDataset.organization}</p>
                        </div>
                        
                        {selectedDataset.lastUpdated && (
                          <div>
                            <h3 className="text-lg font-medium mb-1">Last Updated</h3>
                            <p className="text-gray-700 dark:text-gray-300">{selectedDataset.lastUpdated}</p>
                          </div>
                        )}
                        
                        {selectedDataset.tags && selectedDataset.tags.length > 0 && (
                          <div>
                            <h3 className="text-lg font-medium mb-1">Tags</h3>
                            <div className="flex flex-wrap gap-2">
                              {selectedDataset.tags.map((tag) => (
                                <span 
                                  key={tag} 
                                  className="inline-block bg-gray-100 dark:bg-gray-800 px-2.5 py-0.5 rounded-full text-sm"
                                >
                                  {tag}
                                </span>
                              ))}
                            </div>
                          </div>
                        )}
                        
                        <div className="pt-4">
                          <Button 
                            onClick={handleAnalyze}
                            className="w-full sm:w-auto"
                          >
                            Analyze This Dataset
                          </Button>
                        </div>
                      </TabsContent>
                      
                      <TabsContent value="resources" className="space-y-4">
                        <div>
                          <h3 className="text-lg font-medium mb-2">Available Resources</h3>
                          <div className="space-y-2">
                            {selectedDataset.resources && selectedDataset.resources.length > 0 ? (
                              selectedDataset.resources.map((resource, index) => (
                                <div key={index} className="border p-3 rounded-md">
                                  <h4 className="font-medium">{resource.name}</h4>
                                  <a 
                                    href={resource.url} 
                                    target="_blank" 
                                    rel="noopener noreferrer"
                                    className="text-blue-600 dark:text-blue-400 text-sm hover:underline"
                                  >
                                    Download
                                  </a>
                                </div>
                              ))
                            ) : (
                              <p className="text-gray-500">No resource files are currently available for direct download.</p>
                            )}
                          </div>
                        </div>
                      </TabsContent>
                    </Tabs>
                  </CardContent>
                </>
              )}
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}