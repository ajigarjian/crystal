"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardHeader, CardFooter } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import Link from "next/link";
import { ChevronDown, ChevronUp } from "lucide-react";

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

// Define interface for status messages
interface StatusMessage {
  id: string;
  message: string;
  timestamp: number;
  type: 'status' | 'error' | 'discovery';
  count?: number;
}

export default function DatasetsPage() {
  const [query, setQuery] = useState("");
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchPerformed, setSearchPerformed] = useState(false);
  const [searchMethod, setSearchMethod] = useState<string>("hybrid");
  const [similarityThreshold, setSimilarityThreshold] = useState<number>(0.3);
  const [executionTime, setExecutionTime] = useState<number | null>(null);
  const [statusMessages, setStatusMessages] = useState<StatusMessage[]>([]);
  const [discoveryMessages, setDiscoveryMessages] = useState<StatusMessage[]>([]);
  const [datasetCount, setDatasetCount] = useState<number>(0);
  const [searchComplete, setSearchComplete] = useState(false);
  const [showProcessDetails, setShowProcessDetails] = useState(false);
  const [queryVariations, setQueryVariations] = useState<string[]>([]);
  const [searchStages, setSearchStages] = useState<{
    stage: string;
    complete: boolean;
    startTime?: number;
    endTime?: number;
  }[]>([]);
  
  // Scroll to the latest discovered dataset
  const discoveryEndRef = useRef<HTMLDivElement>(null);
  
  const router = useRouter();
  
  // Add example queries
  const exampleQueries = [
    "What's the air quality trend in NYC over the past 5 years?",
    "How has median housing price changed in San Francisco since 2010?",
    "What are the vaccination rates for children in Chicago by neighborhood?",
    "Compare public transit ridership in Boston before and after COVID-19",
    "What's the correlation between green space and asthma rates in Los Angeles?",
    "Show me demographic changes in Atlanta's neighborhoods since 2015"
  ];
  
  // Determine if we're on mobile (for responsive design)
  const [isMobile, setIsMobile] = useState(false);
  
  // Check screen size on mount and when window resizes
  useEffect(() => {
    const checkMobile = () => {
      setIsMobile(window.innerWidth < 640); // 640px is the 'sm' breakpoint in Tailwind
    };
    
    // Check initially
    checkMobile();
    
    // Add resize listener
    window.addEventListener('resize', checkMobile);
    
    // Clean up
    return () => window.removeEventListener('resize', checkMobile);
  }, []);
  
  // Get the appropriate number of examples based on screen size
  const displayedExamples = isMobile ? exampleQueries.slice(0, 3) : exampleQueries.slice(0, 3);
  
  // Function to handle clicking an example query
  const handleExampleClick = (query: string) => {
    setQuery(query);
    processStreamingQuery(query);
  };
  
  // Scroll to bottom of discovery feed when new datasets are found
  // Commented out to prevent automatic scrolling so users can see the search strategy
  /*
  useEffect(() => {
    if (discoveryEndRef.current && discoveryMessages.length > 0) {
      discoveryEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [discoveryMessages]);
  */

  // Function to process a query with streaming
  const processStreamingQuery = async (queryText: string) => {
    if (!queryText.trim()) {
      setError("Please enter a query about government data.");
      return;
    }

    try {
      // Reset state for a new search
      setLoading(true);
      setError(null);
      setDatasets([]);
      setStatusMessages([]);
      setDiscoveryMessages([]);
      setDatasetCount(0);
      setSearchComplete(false);
      setSearchPerformed(true);
      setExecutionTime(null);
      setQueryVariations([]);
      setSearchStages([
        { stage: "Analyzing query", complete: false, startTime: Date.now() },
        { stage: "Generating query variations", complete: false },
        { stage: "Vector search", complete: false },
        { stage: "Keyword search", complete: false },
        { stage: "Combining results", complete: false }
      ]);
      
      console.log(`Streaming search for datasets: "${queryText}"`);
      
      // Simulate AI thinking about the query
      setTimeout(() => {
        // Mark the first stage as complete
        setSearchStages(prev => {
          const updated = [...prev];
          updated[0] = { ...updated[0], complete: true, endTime: Date.now() };
          updated[1] = { ...updated[1], startTime: Date.now() };
          return updated;
        });
        
        // Generate some plausible query variations
        const variations = [
          queryText,
          queryText.includes("data") ? queryText : `${queryText} data`,
          queryText.includes("statistics") ? queryText : `${queryText} statistics`
        ];
        
        // If the query contains specific keywords, add more targeted variations
        if (queryText.toLowerCase().includes("air quality")) {
          variations.push("air pollution measurements");
          variations.push("PM2.5 and PM10 levels");
        } else if (queryText.toLowerCase().includes("housing")) {
          variations.push("real estate market trends");
          variations.push("property value statistics");
        } else if (queryText.toLowerCase().includes("vaccination")) {
          variations.push("immunization rates");
          variations.push("vaccine coverage data");
        }
        
        // Add the variations to state
        setQueryVariations(variations);
        
        // Mark generation as complete, start vector search
        setTimeout(() => {
          setSearchStages(prev => {
            const updated = [...prev];
            updated[1] = { ...updated[1], complete: true, endTime: Date.now() };
            updated[2] = { ...updated[2], startTime: Date.now() };
            return updated;
          });
        }, 700);
      }, 800);
      
      // Create fetch request to our streaming endpoint
      const response = await fetch("/api/stream-search", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          query: queryText,
          search_method: searchMethod === "hybrid" ? null : searchMethod,
          similarity_threshold: similarityThreshold,
        }),
      });
      
      if (!response.ok || !response.body) {
        throw new Error(`Error starting search: ${response.status} ${response.statusText}`);
      }
      
      // Create a reader for the streaming response
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      
      // Process the stream chunks
      let buffer = ''; // For handling partial JSON chunks
      let vectorSearchActive = false;
      let keywordSearchActive = false;
      
      while (true) {
        const { done, value } = await reader.read();
        
        if (done) {
          console.log("Stream complete");
          break;
        }
        
        // Decode the chunk and add to buffer
        const chunk = decoder.decode(value, { stream: true });
        buffer += chunk;
        
        // Process complete JSON objects in the buffer
        const lines = buffer.split('\n');
        buffer = lines.pop() || ''; // Keep the last potentially incomplete line in the buffer
        
        for (const line of lines) {
          if (!line.trim()) continue; // Skip empty lines
          
          try {
            const data = JSON.parse(line);
            
            // Handle status messages to track search stages
            if (data.type === 'status') {
              const message = data.message.toLowerCase();
              
              if (message.includes('government database') && !vectorSearchActive) {
                vectorSearchActive = true;
                // Update vector search stage
                setSearchStages(prev => {
                  const updated = [...prev];
                  updated[2] = { ...updated[2], startTime: Date.now() };
                  return updated;
                });
              } else if (message.includes('additional government data') && !keywordSearchActive) {
                keywordSearchActive = true;
                // Mark vector search as complete
                setSearchStages(prev => {
                  const updated = [...prev];
                  updated[2] = { ...updated[2], complete: true, endTime: Date.now() };
                  updated[3] = { ...updated[3], startTime: Date.now() };
                  return updated;
                });
              } else if (message.includes('search complete')) {
                // Mark remaining stages as complete
                setSearchStages(prev => {
                  const updated = [...prev];
                  if (!updated[2].complete) {
                    updated[2] = { ...updated[2], complete: true, endTime: Date.now() };
                  }
                  if (!updated[3].complete) {
                    updated[3] = { ...updated[3], complete: true, endTime: Date.now() };
                  }
                  updated[4] = { ...updated[4], complete: true, startTime: Date.now() - 300, endTime: Date.now() };
                  return updated;
                });
              }
            }
            
            // Process different message types
            switch (data.type) {
              case 'status':
                // Add new status message
                const statusMessage: StatusMessage = {
                  id: Math.random().toString(36).substring(2, 9),
                  message: data.message,
                  timestamp: data.timestamp,
                  type: 'status'
                };
                setStatusMessages(prev => [...prev, statusMessage]);
                break;
                
              case 'discovery':
                // Add new discovery message
                const discoveryMessage: StatusMessage = {
                  id: Math.random().toString(36).substring(2, 9),
                  message: data.message,
                  timestamp: data.timestamp,
                  type: 'discovery',
                  count: data.count
                };
                setDiscoveryMessages(prev => [...prev, discoveryMessage]);
                setDatasetCount(data.count || discoveryMessages.length + 1);
                break;
                
              case 'dataset':
                // Add new dataset
                setDatasets(prev => {
                  // Check if dataset already exists
                  const exists = prev.some(d => d.id === data.data.id);
                  if (exists) return prev;
                  
                  // Sort datasets by similarity
                  const newDatasets = [...prev, data.data].sort(
                    (a, b) => (b.similarity || 0) - (a.similarity || 0)
                  );
                  return newDatasets;
                });
                break;
                
              case 'dataset_update':
                // Update an existing dataset (used for search_source updates)
                setDatasets(prev => 
                  prev.map(d => d.id === data.data.id ? data.data : d)
                );
                break;
                
              case 'complete':
                // Search is complete
                setSearchComplete(true);
                setLoading(false);
                setExecutionTime(data.data.execution_time);
                
                // Add the completion message to status messages
                if (data.message) {
                  const completeMessage: StatusMessage = {
                    id: Math.random().toString(36).substring(2, 9),
                    message: data.message,
                    timestamp: data.data.execution_time,
                    type: 'status'
                  };
                  setStatusMessages(prev => [...prev, completeMessage]);
                }
                break;
                
              case 'error':
                // Show error message
                setError(data.message);
                setLoading(false);
                
                // Add to status messages too
                const errorMessage: StatusMessage = {
                  id: Math.random().toString(36).substring(2, 9),
                  message: `Error: ${data.message}`,
                  timestamp: data.timestamp,
                  type: 'error'
                };
                setStatusMessages(prev => [...prev, errorMessage]);
                break;
                
              default:
                console.log(`Unknown message type: ${data.type}`, data);
            }
          } catch (err) {
            console.error("Error parsing JSON from stream:", err, line);
          }
        }
      }
      
      // If we got here without errors, but search isn't marked complete
      if (!searchComplete) {
        setSearchComplete(true);
        setLoading(false);
        
        // Ensure all search stages are marked complete
        setSearchStages(prev => {
          return prev.map(stage => {
            if (!stage.complete) {
              return { ...stage, complete: true, endTime: Date.now() };
            }
            return stage;
          });
        });
      }
      
    } catch (err: any) {
      console.error("Error in streaming search:", err);
      setError(`Failed to search datasets: ${err.message || String(err)}`);
      setLoading(false);
    }
  };

  // Handle form submission
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    // Use the streaming function
    processStreamingQuery(query);
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

  // Handle keydown in the input field
  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      processStreamingQuery(query);
    }
  };

  // Toggle process details visibility
  const toggleProcessDetails = () => {
    setShowProcessDetails(!showProcessDetails);
  };

  // Format milliseconds to readable duration
  const formatDuration = (startTime?: number, endTime?: number) => {
    if (!startTime || !endTime) return "—";
    const duration = endTime - startTime;
    return `${(duration / 1000).toFixed(2)}s`;
  };

  return (
    <>
      {/* Initial hero state - when no search has been performed */}
      {!searchPerformed ? (
        <div className="flex items-center justify-center min-h-screen bg-neutral-50 dark:bg-neutral-50 p-4">
          <div
            className="w-full h-[calc(100vh-2rem)] rounded-lg bg-cover bg-center flex flex-col justify-center relative overflow-hidden"
            style={{
              backgroundImage: "url('/images/crystal-bg0.png')",
            }}
          >
            {/* Background Image Layer with dark overlay */}
            <div 
              className="absolute inset-0 z-10 bg-cover bg-center after:absolute after:inset-0 after:bg-black/70 after:backdrop-blur-sm" 
              style={{ backgroundImage: "url('/images/crystal-bg0.png')" }}
            ></div>
            
            {/* Back to home link */}
            <div className="absolute top-6 left-6 z-30">
              <Link href="/">
                <Button 
                  variant="link" 
                  className="text-white hover:text-green-400 transition-colors p-2 rounded-full hover:bg-white/10 group"
                  style={{ fontFamily: 'var(--font-geist-sans)' }}
                  aria-label="Back to home"
                >
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
                    className="transition-transform duration-200 group-hover:translate-x-[-2px]"
                  >
                    <path d="m12 19-7-7 7-7"/>
                    <path d="M19 12H5"/>
                  </svg>
                </Button>
              </Link>
            </div>
            
            {/* Content */}
            <div className="flex items-center justify-center z-20 relative w-full">
              <img 
                src="/images/gem.svg" 
                alt="Crystal Gem Logo" 
                className="h-12 w-12 mr-3" 
                style={{ filter: "brightness(0) invert(1)" }}
              />
              <div className="relative">
                <h1 className="text-6xl font-bold text-white" style={{ fontFamily: 'var(--font-geist-sans)' }}>
                  Crystal
                </h1>
              </div>
            </div>
            <div className="relative p-2 mt-2 z-20 text-center w-full">
              <h2 className="relative text-xl sm:text-2xl text-white" style={{ fontFamily: 'var(--font-geist-sans)' }}>
                Querying for deep<span className="text-green-500 animate-pulse drop-shadow-[0_0_8px_rgba(34,197,94,0.8)]" style={{ textShadow: '0 0 10px rgba(34, 197, 94, 0.8)' }}>er</span> Research into Public Records
              </h2>
            </div>
            
            {/* Example queries */}
            <div className="z-20 relative w-full max-w-3xl mx-auto px-4 mt-8">
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                {displayedExamples.map((query, index) => (
                  <button
                    key={index}
                    onClick={() => handleExampleClick(query)}
                    className="bg-white/10 hover:bg-white/20 text-white text-sm p-3 rounded-lg border border-white/20 transition-colors text-left hover:border-green-400/50"
                  >
                    {query}
                  </button>
                ))}
              </div>
            </div>
            
            {/* Search input for landing page */}
            <div className="z-20 relative w-full max-w-md mx-auto px-4 mt-8">
              <div className="flex w-full items-end gap-2">
                <Input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Ask about public data..."
                  className="min-h-10 bg-white/20 border-white/30 text-white placeholder:text-white/70 focus:border-green-400/70"
                  disabled={loading}
                />
                <Button 
                  onClick={() => processStreamingQuery(query)}
                  disabled={loading || !query.trim()}
                  className="bg-green-500/80 hover:bg-green-500/90 text-white h-10"
                >
                  {loading ? "Searching..." : "Search"}
                </Button>
              </div>
            </div>
          </div>
        </div>
      ) : (
        /* Regular datasets page layout when search has been performed */
        <div className="container mx-auto py-6 space-y-6">
          {/* Back button */}
          <div className="flex items-center mb-4">
            <Link href="/">
              <Button 
                variant="ghost" 
                className="p-2 mr-2 group"
                aria-label="Back to home"
              >
                <svg 
                  xmlns="http://www.w3.org/2000/svg" 
                  width="20" 
                  height="20" 
                  viewBox="0 0 24 24" 
                  fill="none" 
                  stroke="currentColor" 
                  strokeWidth="2" 
                  strokeLinecap="round" 
                  strokeLinejoin="round"
                  className="transition-transform duration-200 group-hover:translate-x-[-2px]"
                >
                  <path d="m12 19-7-7 7-7"/>
                  <path d="M19 12H5"/>
                </svg>
              </Button>
            </Link>
            <div className="flex items-center">
              <img 
                src="/images/gem.svg" 
                alt="Crystal Logo" 
                className="h-6 w-6 mr-2" 
              />
              <h1 className="text-2xl font-bold">Crystal</h1>
            </div>
          </div>
          
          {/* Search form - simplified */}
          <form onSubmit={handleSubmit} className="mb-6">
            <div className="flex space-x-2">
              <Input
                id="query"
                type="text"
                placeholder="Refine your search..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                className="flex-1"
                disabled={loading}
              />
              <Button type="submit" disabled={loading} className="bg-green-600 hover:bg-green-700 text-white">
                {loading ? "Searching..." : "Search"}
              </Button>
            </div>
          </form>

          {/* Error message */}
          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {/* Loading state with live discovery feed */}
          {loading && (
            <div className="space-y-4">
              {/* Status messages */}
              <div className="p-3 bg-neutral-50 dark:bg-neutral-900 rounded-md border border-neutral-200 dark:border-neutral-800">
                <div className="flex items-center mb-2">
                  <div className="w-3 h-3 bg-green-500 rounded-full animate-pulse mr-2"></div>
                  <h3 className="font-medium">Search Progress</h3>
                </div>
                
                <div className="space-y-1">
                  {statusMessages.slice(-3).map((msg) => (
                    <div 
                      key={msg.id}
                      className={`text-sm ${msg.type === 'error' ? 'text-red-500' : 'text-neutral-600 dark:text-neutral-400'}`}
                    >
                      {msg.message}
                    </div>
                  ))}
                </div>
              </div>
              
              {/* Dataset discovery feed */}
              {discoveryMessages.length > 0 && (
                <div className="border rounded-md p-3 max-h-60 overflow-y-auto border-green-100 dark:border-green-900/50">
                  <h3 className="font-medium mb-2">Discovering Datasets ({datasetCount})</h3>
                  <div className="space-y-2">
                    {discoveryMessages.map((msg) => (
                      <div 
                        key={msg.id}
                        className="text-sm bg-neutral-50 dark:bg-neutral-900 p-2 rounded animate-fadeIn"
                      >
                        {msg.message}
                        <span className="text-xs text-green-600 ml-2">#{msg.count}</span>
                      </div>
                    ))}
                    <div ref={discoveryEndRef} /> {/* Scroll anchor */}
                  </div>
                </div>
              )}
              
              <p className="text-sm text-neutral-600 dark:text-neutral-400 animate-pulse">
                {datasets.length > 0 
                  ? `Found ${datasets.length} datasets so far...`
                  : "Finding relevant datasets..."}
              </p>
              
              {/* Show found datasets while still loading */}
              {datasets.length > 0 && (
                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
                  {datasets.map((dataset) => (
                    <Card 
                      key={dataset.id}
                      className="overflow-hidden hover:shadow-md transition-shadow cursor-pointer hover:border-green-200 flex flex-col border-neutral-200 animate-fadeIn"
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
                  
                  {/* Show skeletons for more datasets coming */}
                  {loading && datasets.length > 0 && (
                    <Card className="overflow-hidden border-neutral-200 animate-pulse">
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
                  )}
                </div>
              )}
              
              {/* Show skeletons if no datasets found yet */}
              {datasets.length === 0 && discoveryMessages.length === 0 && (
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
              )}
            </div>
          )}

          {/* Search complete results */}
          {!loading && searchPerformed && (
            <div className="space-y-4">
              {datasets.length > 0 ? (
                <>
                  <div className="flex flex-col">
                    <div className="flex items-center justify-between">
                      <p className="text-sm text-neutral-600 dark:text-neutral-400">
                        Found {datasets.length} relevant datasets for your query.
                      </p>
                      <Button 
                        variant="ghost" 
                        size="sm" 
                        className="flex items-center gap-1 text-xs text-neutral-500 hover:text-green-700"
                        onClick={toggleProcessDetails}
                      >
                        {showProcessDetails ? (
                          <>
                            <span>Hide Search Process</span>
                            <ChevronUp className="h-4 w-4" />
                          </>
                        ) : (
                          <>
                            <span>View Search Process</span>
                            <ChevronDown className="h-4 w-4" />
                          </>
                        )}
                      </Button>
                    </div>
                    
                    {/* Collapsible process details */}
                    {showProcessDetails && (
                      <div className="mt-2 border rounded-md overflow-hidden border-green-100 dark:border-green-900">
                        {/* AI thinking process */}
                        <div className="border-b p-3 bg-green-50 dark:bg-green-900/30">
                          <h3 className="font-medium text-sm mb-2 text-green-900 dark:text-green-400">Search Strategy</h3>
                          
                          {/* Search stages with timing */}
                          <div className="space-y-2 mb-3">
                            {searchStages.map((stage, index) => (
                              <div key={index} className="flex items-center justify-between text-sm">
                                <div className="flex items-center gap-2">
                                  {stage.complete ? (
                                    <svg className="h-4 w-4 text-green-600" viewBox="0 0 20 20" fill="currentColor">
                                      <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                                    </svg>
                                  ) : (
                                    <div className="h-4 w-4 rounded-full border-2 border-green-300 animate-pulse"></div>
                                  )}
                                  <span className={stage.complete ? "text-green-900 dark:text-green-300" : "text-neutral-500 dark:text-neutral-400"}>
                                    {stage.stage}
                                  </span>
                                </div>
                                <span className="text-xs text-green-700 dark:text-green-400">
                                  {formatDuration(stage.startTime, stage.endTime)}
                                </span>
                              </div>
                            ))}
                          </div>
                          
                          {/* Query variations */}
                          {queryVariations.length > 0 && (
                            <div className="mt-3">
                              <h4 className="text-xs font-medium mb-1 text-green-900 dark:text-green-400">Query Variations</h4>
                              <div className="flex flex-wrap gap-1">
                                {queryVariations.map((variation, index) => (
                                  <Badge 
                                    key={index} 
                                    variant={index === 0 ? "default" : "outline"} 
                                    className={`text-xs ${index === 0 ? 'bg-green-600' : 'text-green-700 border-green-300 dark:border-green-700'}`}
                                  >
                                    {variation}
                                  </Badge>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                        
                        {/* Status messages */}
                        <div className="p-3 bg-white dark:bg-neutral-800">
                          <h3 className="font-medium text-sm mb-2">Search Progress</h3>
                          <div className="space-y-1">
                            {statusMessages.map((msg) => (
                              <div 
                                key={msg.id}
                                className={`text-sm ${msg.type === 'error' ? 'text-red-500' : 'text-neutral-600 dark:text-neutral-400'}`}
                              >
                                {msg.message}
                              </div>
                            ))}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                  
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
            <div className="bg-green-50 dark:bg-green-900/20 border border-green-100 dark:border-green-900 p-3 rounded-md text-sm mt-2">
              <p className="text-green-700 dark:text-green-400">
                Search completed in {executionTime.toFixed(2)} seconds.
              </p>
            </div>
          )}
        </div>
      )}
      
      {/* Add fadeIn animation to the global styles */}
      <style jsx global>{`
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(10px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .animate-fadeIn {
          animation: fadeIn 0.3s ease-in-out forwards;
        }
      `}</style>
    </>
  );
}
