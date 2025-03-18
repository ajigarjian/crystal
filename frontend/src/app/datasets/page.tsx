"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardHeader, CardFooter } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";

interface Resource {
  id: string;
  name: string;
  url: string;
  description?: string;
  format?: string;
}

interface Tag {
  name: string;
  display_name?: string;
}

interface Dataset {
  id: string;
  title: string;
  description?: string;
  similarity?: number;
  relevance_score?: number;
  organization?: {
    id?: string;
    name?: string;
    title?: string;
    image_url?: string;
  };
  organization_name?: string;
  organization_title?: string;
  resources?: Resource[];
  tags?: (Tag | string)[];
  image_url?: string;
  search_source?: string;
}

export default function DatasetsPage() {
  const [query, setQuery] = useState("");
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchPerformed, setSearchPerformed] = useState(false);
  const [searchMethod, setSearchMethod] = useState<string>("hybrid");
  const [similarityThreshold, setSimilarityThreshold] = useState<number>(0.5);
  const [executionTime, setExecutionTime] = useState<number | null>(null);
  const router = useRouter();

  // Function to process a query and get relevant datasets
  const processQuery = async (queryText: string) => {
    if (!queryText.trim()) {
      setError("Please enter a query about government data.");
      return;
    }

    try {
      setLoading(true);
      setError(null);
      setDatasets([]);
      setSearchPerformed(true);
      
      console.log(`Searching for datasets: "${queryText}"`);
      
      // Use our new search endpoint instead of the query endpoint
      const response = await fetch("/api/search", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          query: queryText,
          search_method: searchMethod === "hybrid" ? null : searchMethod,
          similarity_threshold: similarityThreshold,
          timeout: 30
        }),
      });

      if (!response.ok) {
        throw new Error(`Error searching datasets: ${response.status} ${response.statusText}`);
      }

      const data = await response.json();
      console.log("Search response received");

      // Extract datasets from the response
      if (data.datasets && Array.isArray(data.datasets)) {
        console.log(`Received ${data.datasets.length} datasets in ${data.execution_time.toFixed(2)} seconds`);
        
        // Store execution time
        setExecutionTime(data.execution_time);
        
        // Sort datasets by similarity score
        const sortedDatasets = [...data.datasets].sort((a, b) => 
          (b.similarity || 0) - (a.similarity || 0)
        );
        
        setDatasets(sortedDatasets);
        
        // Display search method used
        console.log(`Search method used: ${data.search_method}`);
      } else {
        console.error("No datasets array in response:", data);
        setDatasets([]);
      }
    } catch (err) {
      console.error("Error searching datasets:", err);
      setError(`Failed to search datasets: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  // Handle form submission
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    processQuery(query);
  };

  // Handle dataset selection
  const handleDatasetSelect = (dataset: Dataset) => {
    router.push(`/chat?dataset=${dataset.id}&query=${encodeURIComponent(query)}`);
  };

  // Helper function to get image URL
  const getImageUrl = (dataset: Dataset) => {
    // First check if dataset has an image_url
    if (dataset.image_url) return dataset.image_url;
    
    // Then check if organization has an image_url
    if (dataset.organization && dataset.organization.image_url) 
      return dataset.organization.image_url;
    
    // Get organization name from either structure
    const orgName = dataset.organization?.title || 
                   dataset.organization?.name || 
                   dataset.organization_title || 
                   dataset.organization_name || 
                   "";
    
    const firstLetter = orgName ? orgName.charAt(0).toUpperCase() : "D";
    const colors = ["4F46E5", "10B981", "EF4444", "F59E0B", "6366F1"];
    const randomColor = colors[Math.floor(Math.random() * colors.length)];
    
    return `https://placehold.co/32x32/${randomColor}/ffffff?text=${firstLetter}`;
  };

  return (
    <div className="container mx-auto py-6 space-y-6">
      {/* Header */}
      <div className="flex flex-col space-y-2">
        <h1 className="text-2xl font-bold">Data Explorer</h1>
        <p className="text-neutral-600 dark:text-neutral-400">
          Ask a question about government data, and we'll find relevant datasets for you.
        </p>
      </div>

      {/* Search form */}
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="flex flex-col space-y-2">
          <label htmlFor="query" className="text-sm font-medium">
            What government data are you looking for?
          </label>
          <div className="flex space-x-2">
            <Input
              id="query"
              type="text"
              placeholder="e.g., What is the air quality in major US cities?"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="flex-1"
              disabled={loading}
            />
            <Button type="submit" disabled={loading}>
              {loading ? "Searching..." : "Search"}
            </Button>
          </div>
        </div>
        <div className="flex flex-col space-y-2 mt-4">
          <div className="flex flex-wrap gap-4">
            <div>
              <label htmlFor="search-method" className="text-sm font-medium block mb-1">
                Search Method
              </label>
              <select
                id="search-method"
                value={searchMethod}
                onChange={(e) => setSearchMethod(e.target.value)}
                className="h-9 rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm"
                disabled={loading}
              >
                <option value="hybrid">Hybrid (Default)</option>
                <option value="vector">Vector Search</option>
                <option value="keyword">Keyword Search</option>
              </select>
            </div>
            
            <div>
              <label htmlFor="similarity-threshold" className="text-sm font-medium block mb-1">
                Similarity Threshold: {similarityThreshold}
              </label>
              <input
                id="similarity-threshold"
                type="range"
                min="0.1"
                max="0.9"
                step="0.1"
                value={similarityThreshold}
                onChange={(e) => setSimilarityThreshold(parseFloat(e.target.value))}
                className="w-48"
                disabled={loading}
              />
            </div>
          </div>
        </div>
      </form>

      {/* Error message */}
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* Loading state */}
      {loading && (
        <div className="space-y-4">
          <p className="text-sm text-neutral-600 dark:text-neutral-400 animate-pulse">
            Searching for relevant datasets...
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
            {Array.from({ length: 6 }).map((_, index) => (
              <Card key={index} className="overflow-hidden border-neutral-200">
                <CardHeader className="p-3 pb-2">
                  <div className="flex items-start">
                    <Skeleton className="h-6 w-6 rounded mr-2 flex-shrink-0" />
                    <div className="flex-1">
                      <Skeleton className="h-3 w-3/4 mb-1" />
                      <Skeleton className="h-2 w-full" />
                    </div>
                  </div>
                </CardHeader>
                <CardFooter className="px-3 py-2 border-t border-neutral-100">
                  <div className="w-full flex gap-1.5">
                    <Skeleton className="h-5 w-16" />
                    <Skeleton className="h-5 w-16" />
                  </div>
                </CardFooter>
              </Card>
            ))}
          </div>
        </div>
      )}

      {/* Results */}
      {!loading && searchPerformed && (
        <div className="space-y-4">
          {datasets.length > 0 ? (
            <>
              <p className="text-sm text-neutral-600 dark:text-neutral-400">
                Found {datasets.length} relevant datasets for your query.
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
                {datasets.map((dataset) => (
                  <Card 
                    key={dataset.id}
                    className="overflow-hidden hover:shadow-md transition-shadow cursor-pointer hover:border-green-200 flex flex-col border-neutral-200"
                    onClick={() => handleDatasetSelect(dataset)}
                  >
                    <CardHeader className="p-3 pb-2">
                      <div className="flex items-start">
                        <div className="h-6 w-6 rounded overflow-hidden bg-neutral-200 mr-2 flex-shrink-0">
                          <img 
                            src={getImageUrl(dataset)} 
                            alt={`Dataset logo`}
                            className="w-full h-full object-cover"
                            onError={(e) => {
                              const target = e.target as HTMLImageElement;
                              target.src = `https://placehold.co/32x32/4F46E5/ffffff?text=D`;
                            }}
                          />
                        </div>
                        <div className="flex-1 min-w-0">
                          <h3 className="text-sm font-medium leading-tight line-clamp-2 mb-0.5">{dataset.title}</h3>
                          <p className="text-xs text-neutral-500 truncate">
                            {dataset.organization?.title || 
                             dataset.organization_title || 
                             dataset.organization?.name || 
                             dataset.organization_name || 
                             'Unknown source'}
                          </p>
                          <div className="mt-1 flex flex-wrap gap-1.5">
                            <Badge variant="outline" className="text-xs">
                              Relevance: {Math.round((dataset.relevance_score || dataset.similarity || 0) * 100)}%
                            </Badge>
                            {dataset.search_source && (
                              <Badge 
                                variant={dataset.search_source === 'both' ? 'default' : 
                                        dataset.search_source === 'vector' ? 'secondary' : 'outline'} 
                                className="text-xs"
                              >
                                {dataset.search_source}
                              </Badge>
                            )}
                          </div>
                        </div>
                      </div>
                    </CardHeader>
                    
                    {/* Add a description section */}
                    <div className="px-3 py-2">
                      <p className="text-xs text-neutral-600 line-clamp-3">
                        {dataset.description ? 
                          (typeof dataset.description === 'string' ? 
                            dataset.description.replace(/<[^>]*>/g, '') : 
                            'No description') : 
                          'No description'}
                      </p>
                    </div>
                    
                    {/* Add a resources section */}
                    {dataset.resources && dataset.resources.length > 0 && (
                      <div className="px-3 py-2">
                        <p className="text-xs font-medium">Available formats:</p>
                        <div className="flex flex-wrap gap-1 mt-1">
                          {Array.from(new Set(dataset.resources.map(r => r.format?.toUpperCase() || 'UNKNOWN'))).map((format, i) => (
                            <Badge key={i} variant="secondary" className="text-xs">
                              {format}
                            </Badge>
                          ))}
                        </div>
                      </div>
                    )}
                    
                    <CardFooter className="px-3 py-2 border-t border-neutral-100 mt-auto">
                      <div className="w-full flex flex-wrap gap-1.5">
                        {dataset.tags && dataset.tags.length > 0 ? (
                          <>
                            {dataset.tags.slice(0, 3).map((tag, index) => (
                              <Badge 
                                key={index} 
                                variant="secondary" 
                                className="text-xs px-2 py-0.5 h-5 whitespace-nowrap overflow-hidden text-ellipsis max-w-[120px]"
                              >
                                {typeof tag === 'object' && tag.name ? tag.name : String(tag)}
                              </Badge>
                            ))}
                            {dataset.tags.length > 3 && (
                              <Badge variant="outline" className="text-xs px-2 py-0.5 h-5">
                                +{dataset.tags.length - 3}
                              </Badge>
                            )}
                          </>
                        ) : (
                          <span className="text-xs text-neutral-400">No tags</span>
                        )}
                      </div>
                    </CardFooter>
                  </Card>
                ))}
              </div>
            </>
          ) : (
            <div className="text-center py-10">
              <p className="text-neutral-500">No relevant datasets found for your query. Try a different question.</p>
            </div>
          )}
        </div>
      )}

      {/* Execution time */}
      {executionTime !== null && (
        <div className="bg-neutral-50 dark:bg-neutral-900 p-3 rounded-md text-sm mt-2">
          <p className="text-neutral-600 dark:text-neutral-400">
            Search completed in {executionTime.toFixed(2)} seconds using {searchMethod} search method.
          </p>
        </div>
      )}

      {/* Initial state - no search performed yet */}
      {!loading && !searchPerformed && (
        <div className="text-center py-20">
          <p className="text-neutral-500">Enter a question above to find relevant government datasets.</p>
        </div>
      )}
    </div>
  );
}
