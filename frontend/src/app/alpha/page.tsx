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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Progress } from "@/components/ui/progress";
import { AlertCircle, CheckCircle2, FileText, Database, ArrowRight, Download, FileCheck, Loader2 } from "lucide-react";
import { Checkbox } from "@/components/ui/checkbox";
import { streamSearchDatasets, warmFunctions, streamAnalyzeDatasets } from "@/lib/firebase";

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
  status?: 'starting' | 'downloading' | 'downloaded' | 'analyzing_files' | 'loading' | 'assessing' | 'relevant' | 'not_relevant' | 'skipped' | 'error';
  processing_complete?: boolean;
  pre_assessment?: {
    is_relevant: boolean;
    relevance_score: number;
    reasoning: string;
  };
  relevance?: {
    is_relevant: boolean;
    relevance_score: number;
    reasoning: string;
  };
  error?: string;
  file_count?: number;
  files?: string[];
  primary_file?: string;
  preview?: DatasetPreview;
  isRemoving?: boolean;
}

interface DatasetPreview {
  type: 'pdf' | 'tabular';
  file_name: string;
  num_pages?: number;
  text_sample?: string;
  enhanced_summary?: string;
  key_points?: string[];
  row_count?: number;
  column_count?: number;
  columns?: string[];
  sample_data?: any[];
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
  const [showAllMessages, setShowAllMessages] = useState(false);
  const [queryVariations, setQueryVariations] = useState<string[]>([]);
  const [searchStages, setSearchStages] = useState<{
    stage: string;
    complete: boolean;
    startTime?: number;
    endTime?: number;
  }[]>([]);
  const [selectedPreview, setSelectedPreview] = useState<Dataset | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  
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

  // Auto-scroll to bottom of status messages when they update
  useEffect(() => {
    const statusMessageContainers = document.querySelectorAll('.status-message-container');
    statusMessageContainers.forEach(container => {
      container.scrollTop = container.scrollHeight;
    });
  }, [statusMessages]);

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
      
      // Call the Firebase callable function with the search parameters
      const searchParams = {
        query: queryText,
        search_method: searchMethod === "hybrid" ? null : searchMethod,
        similarity_threshold: similarityThreshold,
        max_results: 15,
        census_max_results: 5,
        relevance_threshold: 0.4
      };
      
      // Set up tracking variables
      let vectorSearchActive = false;
      let keywordSearchActive = false;
      
      // Call the Firebase function with a callback to process chunks in real-time
      await streamSearchDatasets(searchParams, (data) => {
        console.log('Received chunk:', data);
        
        try {
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
                
                // Add file count based on resources if available
                const datasetWithFileCount = {
                  ...data.data,
                  file_count: data.data.resources?.length || 0
                };
                
                // Sort datasets by similarity
                const newDatasets = [...prev, datasetWithFileCount].sort(
                  (a, b) => (b.similarity || 0) - (a.similarity || 0)
                );
                return newDatasets;
              });
              break;
              
            case 'dataset_update':
              setDatasets(prev => {
                const datasetIndex = prev.findIndex(d => d.id === data.data.id);
                
                // If dataset exists, update it
                if (datasetIndex !== -1) {
                  const updatedDatasets = [...prev];
                  updatedDatasets[datasetIndex] = {
                    ...updatedDatasets[datasetIndex],
                    ...data.data
                  };
                  
                  // If the dataset has been assessed as not relevant, mark it for removal
                  if (data.data.relevance && data.data.relevance.is_relevant === false) {
                    updatedDatasets[datasetIndex].isRemoving = true;
                    
                    // Remove the dataset after animation completes
                    setTimeout(() => {
                      setDatasets(current => current.filter(d => d.id !== data.data.id));
                    }, 500); // Match this with your CSS transition duration
                  }
                  
                  return updatedDatasets;
                }
                
                return prev;
              });
              break;
              
            case 'complete':
              // Search is complete
              setSearchComplete(true);
              setLoading(false);
              setExecutionTime(data.data.execution_time);
              
              // Sort datasets by relevance score when search is complete
              // AND filter out any datasets that were marked as not relevant
              setDatasets(prev => {
                return [...prev]
                  .filter(dataset => !dataset.relevance || dataset.relevance.is_relevant !== false)
                  .sort((a, b) => {
                    const scoreA = a.relevance?.relevance_score || a.similarity || 0;
                    const scoreB = b.relevance?.relevance_score || b.similarity || 0;
                    return scoreB - scoreA; // Sort in descending order
                  });
              });
              
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
              
            case 'phase_complete':
              // A major phase like search is complete
              if (data.phase === 'search') {
                // Mark all search-related stages as complete
                setSearchStages(prev => {
                  const updated = [...prev];
                  // Ensure all search stages are complete
                  for (let i = 0; i < updated.length; i++) {
                    if (!updated[i].complete) {
                      updated[i] = { ...updated[i], complete: true, endTime: Date.now() };
                    }
                  }
                  // Add processing stage
                  updated.push({ 
                    stage: "Processing datasets", 
                    complete: false, 
                    startTime: Date.now() 
                  });
                  return updated;
                });
                
                const searchCompleteMessage: StatusMessage = {
                  id: Math.random().toString(36).substring(2, 9),
                  message: data.message,
                  timestamp: data.data.execution_time,
                  type: 'status'
                };
                setStatusMessages(prev => [...prev, searchCompleteMessage]);
              }
              break;
            
            case 'processing_start':
              // Starting to process a specific dataset
              setDatasets(prev => {
                return prev.map(d => {
                  if (d.id === data.dataset_id) {
                    return {
                      ...d,
                      status: 'starting'
                    };
                  }
                  return d;
                });
              });
              
              const processingStartMessage: StatusMessage = {
                id: Math.random().toString(36).substring(2, 9),
                message: data.message,
                timestamp: data.timestamp,
                type: 'status'
              };
              setStatusMessages(prev => [...prev, processingStartMessage]);
              break;
            
            case 'pre_assessment':
              // Pre-download relevance assessment result
              setDatasets(prev => {
                return prev.map(d => {
                  if (d.id === data.dataset_id) {
                    return {
                      ...d,
                      pre_assessment: {
                        is_relevant: data.is_relevant,
                        relevance_score: data.relevance_score,
                        reasoning: data.reasoning
                      }
                    };
                  }
                  return d;
                });
              });
              break;
            
            case 'download_complete':
              // Dataset files have been downloaded
              const downloadMessage: StatusMessage = {
                id: Math.random().toString(36).substring(2, 9),
                message: `Downloaded ${data.file_count} files for dataset`,
                timestamp: data.timestamp,
                type: 'status'
              };
              setStatusMessages(prev => [...prev, downloadMessage]);
              break;
            
            case 'file_analysis':
              // Analysis of multiple files in a dataset
              console.log("File analysis:", data);
              break;
            
            case 'dataset_preview':
              // Dataset preview information
              setDatasets(prev => {
                return prev.map(d => {
                  if (d.id === data.dataset_id) {
                    return {
                      ...d,
                      preview: data.preview
                    };
                  }
                  return d;
                });
              });
              break;
            
            case 'relevance_assessment':
              // Final relevance assessment after analyzing the actual data
              setDatasets(prev => {
                const updatedDatasets = prev.map(d => {
                  if (d.id === data.dataset_id) {
                    return {
                      ...d,
                      relevance: {
                        is_relevant: data.is_relevant,
                        relevance_score: data.relevance_score,
                        reasoning: data.reasoning
                      }
                    };
                  }
                  return d;
                });
                
                // If the dataset is not relevant, mark it for removal with animation
                if (!data.is_relevant) {
                  const datasetIndex = updatedDatasets.findIndex(d => d.id === data.dataset_id);
                  if (datasetIndex !== -1) {
                    updatedDatasets[datasetIndex].isRemoving = true;
                    
                    // Remove the dataset after animation completes
                    setTimeout(() => {
                      setDatasets(current => current.filter(d => d.id !== data.dataset_id));
                    }, 500); // Match this with your CSS transition duration
                  }
                }
                
                return updatedDatasets;
              });
              
              const assessmentMessage: StatusMessage = {
                id: Math.random().toString(36).substring(2, 9),
                message: `Dataset assessed with relevance score: ${data.relevance_score.toFixed(2)}`,
                timestamp: data.timestamp,
                type: 'status'
              };
              setStatusMessages(prev => [...prev, assessmentMessage]);
              break;
            
            default:
              console.log(`Unknown message type: ${data.type}`, data);
          }
        } catch (err) {
          console.error("Error processing chunk:", err);
          console.error("Problematic chunk:", data);
        }
      });
      
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
    
    // If search is already complete, start analysis with selected datasets
    if (searchComplete && datasets.length > 0) {
      // If analysis functionality is ready, use the internal startAnalysis
      // startAnalysis();
      
      // Otherwise, navigate to chat page with multiple datasets
      handleMultiDatasetSelect();
    } else {
      // Otherwise do the search as before
      processStreamingQuery(query);
    }
  };

  // Handle single dataset selection
  const handleDatasetSelect = (dataset: Dataset) => {
    // Store the selected dataset ID in localStorage
    localStorage.setItem('selectedDataset', dataset.id);
    localStorage.setItem('lastQuery', query);
    
    // Navigate to the chat page with dataset ID and query
    router.push(`/chat?dataset=${dataset.id}&query=${encodeURIComponent(query)}`);
  };
  
  // Handle multi-dataset selection - for when user wants to analyze multiple datasets
  const handleMultiDatasetSelect = () => {
    // Get the selected datasets
    const datasetIds = Object.entries(selectedDatasets)
      .filter(([_, isSelected]) => isSelected)
      .map(([id]) => id);
      
    if (datasetIds.length === 0) {
      setError("Please select at least one dataset to analyze.");
      return;
    }
    
    // Store selected dataset IDs in localStorage
    localStorage.setItem('selectedDatasets', JSON.stringify(datasetIds));
    localStorage.setItem('lastQuery', query);
    
    // Navigate to analysis page with dataset IDs and query
    router.push(`/chat?datasets=${encodeURIComponent(JSON.stringify(datasetIds))}&query=${encodeURIComponent(query)}`);
  };

  // Helper function to get image URL
  const getImageUrl = (dataset: Dataset) => {
    // First check if dataset has an image_url
    if (dataset.image_url) return dataset.image_url;
    
    // Then check if organization has an image_url
    if (dataset.organization && typeof dataset.organization === 'object' && dataset.organization.image_url) 
      return dataset.organization.image_url;
    
    // Get organization name from either structure
    let orgName = "";
    if (dataset.organization) {
      if (typeof dataset.organization === 'object') {
        orgName = dataset.organization.title || dataset.organization.name || "";
      } else {
        orgName = dataset.organization; // Handle case where organization is a string
      }
    } else {
      orgName = dataset.organization_title || dataset.organization_name || "";
    }
    
    const firstLetter = orgName ? orgName.charAt(0).toUpperCase() : "D";
    const colors = ["4F46E5", "10B981", "EF4444", "F59E0B", "6366F1"];
    const randomColor = colors[Math.floor(Math.random() * colors.length)];
    
    return `https://placehold.co/32x32/${randomColor}/ffffff?text=${firstLetter}`;
  };

  // Helper function to get organization name
  const getOrganizationName = (dataset: Dataset) => {
    if (dataset.organization) {
      if (typeof dataset.organization === 'object') {
        return dataset.organization.title || dataset.organization.name || 'Unknown source';
      } else {
        return dataset.organization; // Handle case where organization is a string
      }
    }
    return dataset.organization_title || dataset.organization_name || 'Unknown source';
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

  // New function to check if we should show the "Show All" button
  const shouldShowAllButton = (messages: StatusMessage[]) => {
    return messages.length > 3;
  };

  // New function to handle dataset preview
  const handlePreviewClick = (e: React.MouseEvent, dataset: Dataset) => {
    e.stopPropagation(); // Prevent card click event from firing
    setSelectedPreview(dataset);
    setPreviewOpen(true);
  };

  // New function to render dataset status
  const getDatasetStatusInfo = (dataset: Dataset) => {
    // Status info with icon and text
    switch(dataset.status) {
      case 'starting':
        return { 
          icon: <Loader2 className="h-4 w-4 animate-spin text-yellow-500" />, 
          text: "Starting analysis...",
          color: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300"
        };
      case 'downloading':
        return { 
          icon: <Download className="h-4 w-4 animate-pulse text-blue-500" />, 
          text: "Downloading files...",
          color: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300"
        };
      case 'downloaded':
        return { 
          icon: <FileCheck className="h-4 w-4 text-blue-500" />, 
          text: `Downloaded ${dataset.file_count || 0} files`,
          color: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300"
        };
      case 'analyzing_files':
        return { 
          icon: <Loader2 className="h-4 w-4 animate-spin text-indigo-500" />, 
          text: "Analyzing files...",
          color: "bg-indigo-100 text-indigo-800 dark:bg-indigo-900/30 dark:text-indigo-300"
        };
      case 'loading':
        return { 
          icon: <Loader2 className="h-4 w-4 animate-spin text-indigo-500" />, 
          text: "Loading data...",
          color: "bg-indigo-100 text-indigo-800 dark:bg-indigo-900/30 dark:text-indigo-300"
        };
      case 'assessing':
        return { 
          icon: <Loader2 className="h-4 w-4 animate-spin text-purple-500" />, 
          text: "Assessing relevance...",
          color: "bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300" 
        };
      case 'relevant':
        return { 
          icon: <CheckCircle2 className="h-4 w-4 text-green-500" />, 
          text: `Relevant (${dataset.relevance?.relevance_score.toFixed(2)})`,
          color: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300"
        };
      case 'not_relevant':
        return { 
          icon: <AlertCircle className="h-4 w-4 text-orange-500" />, 
          text: `Not relevant (${dataset.relevance?.relevance_score.toFixed(2)})`,
          color: "bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-300"
        };
      case 'skipped':
        return { 
          icon: <ArrowRight className="h-4 w-4 text-gray-500" />, 
          text: "Skipped",
          color: "bg-gray-100 text-gray-800 dark:bg-gray-800/30 dark:text-gray-300"
        };
      case 'error':
        return { 
          icon: <AlertCircle className="h-4 w-4 text-red-500" />, 
          text: "Error",
          color: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300"
        };
      default:
        return null;
    }
  };

  // Add this CSS to your component (you can also put it in a separate CSS file)

  const cardStyles = {
    '.dataset-card': {
      transition: 'all 0.5s ease-out',
      opacity: 1,
      transform: 'scale(1)',
      maxHeight: '500px', // Adjust to your card's actual max height
      marginBottom: '16px',
      overflow: 'hidden',
    },
    '.dataset-card.removing': {
      opacity: 0,
      transform: 'scale(0.8)',
      maxHeight: 0,
      marginBottom: 0,
      padding: 0,
    }
  };

  // Add this effect to warm functions when the page loads
  useEffect(() => {
    warmFunctions();
  }, []);

  // Add this effect to automatically search when URL has a query
  useEffect(() => {
    // Get query from URL
    const params = new URLSearchParams(window.location.search);
    const initialQuery = params.get('query');
    
    if (initialQuery) {
      // Set the query in state
      setQuery(initialQuery);
      // Start the search automatically
      processStreamingQuery(initialQuery);
      // Mark search as performed
      setSearchPerformed(true);
    }
  }, []);

  // Add state to track selected datasets
  const [selectedDatasets, setSelectedDatasets] = useState<Record<string, boolean>>({});
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [processingDatasets, setProcessingDatasets] = useState<Dataset[]>([]);
  const [analysisComplete, setAnalysisComplete] = useState(false);
  const [analysisResults, setAnalysisResults] = useState<any>(null);

  // Initialize datasets as selected by default
  useEffect(() => {
    if (datasets.length > 0) {
      // Create an object with all datasets selected by default
      const initialSelection = datasets.reduce((acc, dataset) => {
        acc[dataset.id] = true;
        return acc;
      }, {} as Record<string, boolean>);
      
      setSelectedDatasets(initialSelection);
    }
  }, [datasets]);

  // Add the new analysis function
  const startAnalysis = async () => {
    // Get the selected datasets
    const datasetIds = Object.entries(selectedDatasets)
      .filter(([_, isSelected]) => isSelected)
      .map(([id]) => id);
      
    if (datasetIds.length === 0) {
      setError("Please select at least one dataset to analyze.");
      return;
    }
    
    try {
      // Update UI state
      setIsAnalyzing(true);
      setError(null);
      setAnalysisComplete(false);
      setAnalysisResults(null);
      
      // Initialize processing datasets
      const datasetsToAnalyze = datasets.filter(d => datasetIds.includes(d.id));
      
      // Mark selected datasets as queued
      const initialProcessing = datasetsToAnalyze.map(dataset => ({
        ...dataset,
        status: 'queued'
      }));
      
      setProcessingDatasets(initialProcessing);
      
      // Call the Firebase function with streaming
      await streamAnalyzeDatasets(
        {
          query: query,
          datasets: datasetsToAnalyze,
        },
        (data) => {
          console.log('Received analysis chunk:', data);
          
          // Process different message types
          switch (data.type) {
            case 'status':
              // Add global status message (if needed)
              break;
              
            case 'dataset_status':
              // Update the status of a specific dataset
              if (data.dataset_id && data.status) {
                setProcessingDatasets(prev => 
                  prev.map(d => 
                    d.id === data.dataset_id 
                      ? { ...d, status: data.status, progress: data.progress }
                      : d
                  )
                );
              }
              break;
              
            case 'dataset_result':
              // Store analysis results for a specific dataset
              if (data.dataset_id && data.result) {
                setProcessingDatasets(prev => 
                  prev.map(d => 
                    d.id === data.dataset_id 
                      ? { ...d, analysis_result: data.result, status: 'analyzed' }
                      : d
                  )
                );
              }
              break;
              
            case 'result':
              // Store overall analysis results
              setAnalysisResults(prev => ({
                ...prev,
                ...data.data
              }));
              break;
              
            case 'complete':
              // Analysis is complete
              setAnalysisComplete(true);
              setIsAnalyzing(false);
              break;
              
            case 'error':
              // Handle error - either global or for a specific dataset
              if (data.dataset_id) {
                // Dataset-specific error
                setProcessingDatasets(prev => 
                  prev.map(d => 
                    d.id === data.dataset_id 
                      ? { ...d, status: 'error', error: data.message }
                      : d
                  )
                );
              } else {
                // Global error
                setError(data.message);
                setIsAnalyzing(false);
              }
              break;
              
            default:
              console.log(`Unknown analysis message type: ${data.type}`, data);
          }
        }
      );
    } catch (err: any) {
      console.error("Error in dataset analysis:", err);
      setError(`Failed to analyze datasets: ${err.message || String(err)}`);
      setIsAnalyzing(false);
    }
  };

  // Add these helper functions for status display
  const getStatusColor = (status: string) => {
    switch (status) {
      case 'downloading':
      case 'downloaded':
        return 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300';
      case 'loading':
      case 'loaded':
        return 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900/30 dark:text-indigo-300';
      case 'assessing':
      case 'assessed':
        return 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300';
      case 'extracting':
      case 'extracted':
        return 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300';
      case 'analyzing':
      case 'analyzed':
        return 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300';
      case 'error':
        return 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300';
      case 'queued':
      default:
        return 'bg-gray-100 text-gray-800 dark:bg-gray-800/30 dark:text-gray-300';
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'downloading':
        return <Download className="h-3 w-3 animate-pulse" />;
      case 'downloaded':
        return <Download className="h-3 w-3" />;
      case 'loading':
      case 'assessing':
      case 'extracting':
      case 'analyzing':
        return <Loader2 className="h-3 w-3 animate-spin" />;
      case 'loaded':
      case 'assessed':
      case 'extracted':
      case 'analyzed':
        return <CheckCircle2 className="h-3 w-3" />;
      case 'error':
        return <AlertCircle className="h-3 w-3" />;
      case 'queued':
      default:
        return <FileText className="h-3 w-3" />;
    }
  };

  const getStatusLabel = (status: string) => {
    // Convert status to a more readable format
    switch (status) {
      case 'downloading':
        return 'Downloading';
      case 'downloaded':
        return 'Downloaded';
      case 'loading':
        return 'Loading';
      case 'loaded':
        return 'Loaded';
      case 'assessing':
        return 'Assessing';
      case 'assessed':
        return 'Assessed';
      case 'extracting':
        return 'Extracting';
      case 'extracted':
        return 'Extracted';
      case 'analyzing':
        return 'Analyzing';
      case 'analyzed':
        return 'Analyzed';
      case 'error':
        return 'Error';
      case 'queued':
        return 'Queued';
      default:
        return status.charAt(0).toUpperCase() + status.slice(1);
    }
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
              <Button 
                type="submit" 
                disabled={loading || isAnalyzing} 
                className={`${
                  !loading && searchComplete && datasets.length > 0
                    ? isAnalyzing
                      ? "bg-black/80 text-white" 
                      : "bg-black hover:bg-black/90 text-white animate-pulse"
                    : "bg-green-600 hover:bg-green-700 text-white"
                }`}
              >
                {loading 
                  ? "Searching..." 
                  : isAnalyzing
                    ? "Analyzing..."
                    : (searchComplete && datasets.length > 0) 
                      ? "Analyze" 
                      : "Search"
                }
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
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center">
                    <div className="w-3 h-3 bg-green-500 rounded-full animate-pulse mr-2"></div>
                    <h3 className="font-medium">Search Progress</h3>
                  </div>
                  {shouldShowAllButton(statusMessages) && (
                    <Button 
                      variant="ghost" 
                      size="sm" 
                      className="h-6 text-xs"
                      onClick={() => setShowAllMessages(prev => !prev)}
                    >
                      {showAllMessages ? "Show Less" : "Show All"}
                    </Button>
                  )}
                </div>
                
                <div className="space-y-1 max-h-[200px] overflow-y-auto pr-1 status-message-container">
                  {(showAllMessages ? statusMessages : statusMessages.slice(-3)).map((msg) => (
                    <div 
                      key={msg.id}
                      className={`text-sm ${msg.type === 'error' ? 'text-red-500' : 'text-neutral-600 dark:text-neutral-400'} mb-2`}
                    >
                      {msg.message && typeof msg.message === 'string' && msg.message.includes("Assessing dataset") ? (
                        // Format assessment messages in a more conversational style
                        <div dangerouslySetInnerHTML={{ 
                          __html: msg.message.replace(/Assessing dataset \d+\/\d+: (.+)/, (match, datasetName) => {
                            // Extract organization name from the message if available
                            const orgMatch = msg.message.match(/organization_name":\s*"([^"]+)"/);
                            const orgName = orgMatch ? orgMatch[1] : "";
                            
                            if (orgName) {
                              return `I'm assessing the dataset <strong>${datasetName}</strong> from <strong>${orgName}</strong>`;
                            } else {
                              return `I'm assessing the dataset <strong>${datasetName}</strong>`;
                            }
                          })
                        }} />
                      ) : msg.message && typeof msg.message === 'string' && msg.message.includes("Pre-assessment:") ? (
                        // Format pre-assessment messages
                        <div dangerouslySetInnerHTML={{ 
                          __html: msg.message.replace(
                            /Pre-assessment: Dataset is (relevant|not relevant) \(Score: (.+)\)(\s*)Reasoning: (.+)/,
                            function(match, relevance, score, space, reasoning) {
                              // Convert first letter of reasoning to lowercase
                              const lowerCaseReasoning = reasoning.charAt(0).toLowerCase() + reasoning.slice(1);
                              return `It appears to be <strong>${relevance}</strong> because ${lowerCaseReasoning} I'll download the files for additional insight.`;
                            }
                          )
                        }} />
                      ) : msg.message && typeof msg.message === 'string' && msg.message.includes("Final assessment:") ? (
                        // Format final assessment messages
                        <div dangerouslySetInnerHTML={{ 
                          __html: msg.message.replace(
                            /Final assessment: Dataset is (relevant|not relevant) \(Score: (.+)\)(\s*)Reasoning: (.+)/,
                            function(match, relevance, score, space, reasoning) {
                              // Convert first letter of reasoning to lowercase
                              const lowerCaseReasoning = reasoning.charAt(0).toLowerCase() + reasoning.slice(1);
                              return `Based on the actual files, this dataset is <strong>${relevance}</strong> because ${lowerCaseReasoning}`;
                            }
                          )
                        }} />
                      ) : (
                        // Keep other messages as is or handle undefined
                        msg.message || ""
                      )}
                    </div>
                  ))}
                </div>
              </div>
              
              <p className="text-sm text-neutral-600 dark:text-neutral-400 animate-pulse">
                {datasets.length > 0 
                  ? `Found ${datasets.length} datasets so far...`
                  : "Finding relevant datasets..."}
              </p>
              
              {/* Show found datasets while still loading */}
              {datasets.length > 0 && (
                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
                  {datasets.map((dataset, index) => {
                    const statusInfo = getDatasetStatusInfo(dataset);
                    const style = { '--animation-delay': `${index * 50}ms` } as React.CSSProperties;
                    
                    return (
                      <Card 
                        key={dataset.id}
                        className={`overflow-hidden hover:shadow-md transition-shadow cursor-pointer 
                                   hover:border-green-200 flex flex-col border-neutral-200 
                                   ${dataset.isRemoving ? 'removing' : 'animate-fadeIn'}`}
                        onClick={() => handleDatasetSelect(dataset)}
                        style={style}
                      >
                        {/* Status indicator - if processing */}
                        {statusInfo && (
                          <div className={`absolute top-2 right-2 z-10 rounded-full px-2 py-0.5 flex items-center text-xs ${statusInfo.color}`}>
                            {statusInfo.icon}
                            <span className="ml-1">{statusInfo.text}</span>
                          </div>
                        )}
                        
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
                              <p className="text-xs text-neutral-500 truncate" title={getOrganizationName(dataset)}>
                                {getOrganizationName(dataset)}
                              </p>
                              <div className="mt-1 flex flex-wrap gap-1.5">
                                <Badge variant="outline" className="text-xs">
                                  Relevance: {Math.round((dataset.relevance?.relevance_score || dataset.similarity || 0) * 100)}%
                                </Badge>
                                
                                {/* Add file count badge if available */}
                                {dataset.file_count && dataset.file_count > 0 && (
                                  <Badge variant="secondary" className="text-xs">
                                    {dataset.file_count} {dataset.file_count === 1 ? 'file' : 'files'}
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
                        
                        {/* Preview button - if dataset has been downloaded/processed */}
                        {dataset.preview && (
                          <div className="px-3 py-2">
                            <Button 
                              variant="outline" 
                              size="sm" 
                              className="w-full text-xs"
                              onClick={(e) => handlePreviewClick(e, dataset)}
                            >
                              <FileText className="h-3 w-3 mr-1" />
                              Preview Data
                            </Button>
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
                    );
                  })}
                  
                  {/* Show skeletons for more datasets coming */}
                  {loading && datasets.length > 0 && !datasets.some(d => d.status) && (
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
                        Found {datasets.length} relevant datasets for your query
                        {executionTime !== null && ` in ${executionTime.toFixed(2)} seconds`}.
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
                          
                
                        </div>
                        
                        {/* Status messages */}
                        <div className="p-3 bg-white dark:bg-neutral-800">
                          <div className="flex items-center justify-between mb-2">
                            <h3 className="font-medium text-sm">Search Progress</h3>
                            {shouldShowAllButton(statusMessages) && (
                              <Button 
                                variant="ghost" 
                                size="sm" 
                                className="h-6 text-xs"
                                onClick={() => setShowAllMessages(prev => !prev)}
                              >
                                {showAllMessages ? "Show Less" : "Show All"}
                              </Button>
                            )}
                          </div>
                          <div className="space-y-1 max-h-[300px] overflow-y-auto pr-1 status-message-container">
                            {(showAllMessages ? statusMessages : statusMessages.slice(-3)).map((msg) => (
                              <div 
                                key={msg.id}
                                className={`text-sm ${msg.type === 'error' ? 'text-red-500' : 'text-neutral-600 dark:text-neutral-400'} mb-2`}
                              >
                                {msg.message && typeof msg.message === 'string' && msg.message.includes("Assessing dataset") ? (
                                  // Format assessment messages in a more conversational style
                                  <div dangerouslySetInnerHTML={{ 
                                    __html: msg.message.replace(/Assessing dataset \d+\/\d+: (.+)/, (match, datasetName) => {
                                      // Extract organization name from the message if available
                                      const orgMatch = msg.message.match(/organization_name":\s*"([^"]+)"/);
                                      const orgName = orgMatch ? orgMatch[1] : "";
                                      
                                      if (orgName) {
                                        return `I'm assessing the dataset <strong>${datasetName}</strong> from <strong>${orgName}</strong>`;
                                      } else {
                                        return `I'm assessing the dataset <strong>${datasetName}</strong>`;
                                      }
                                    })
                                  }} />
                                ) : msg.message && typeof msg.message === 'string' && msg.message.includes("Pre-assessment:") ? (
                                  // Format pre-assessment messages
                                  <div dangerouslySetInnerHTML={{ 
                                    __html: msg.message.replace(
                                      /Pre-assessment: Dataset is (relevant|not relevant) \(Score: (.+)\)(\s*)Reasoning: (.+)/,
                                      function(match, relevance, score, space, reasoning) {
                                        // Convert first letter of reasoning to lowercase
                                        const lowerCaseReasoning = reasoning.charAt(0).toLowerCase() + reasoning.slice(1);
                                        return `It appears to be <strong>${relevance}</strong> because ${lowerCaseReasoning} I'll download the files for additional insight.`;
                                      }
                                    )
                                  }} />
                                ) : msg.message && typeof msg.message === 'string' && msg.message.includes("Final assessment:") ? (
                                  // Format final assessment messages
                                  <div dangerouslySetInnerHTML={{ 
                                    __html: msg.message.replace(
                                      /Final assessment: Dataset is (relevant|not relevant) \(Score: (.+)\)(\s*)Reasoning: (.+)/,
                                      function(match, relevance, score, space, reasoning) {
                                        // Convert first letter of reasoning to lowercase
                                        const lowerCaseReasoning = reasoning.charAt(0).toLowerCase() + reasoning.slice(1);
                                        return `Based on the actual files, this dataset is <strong>${relevance}</strong> because ${lowerCaseReasoning}`;
                                      }
                                    )
                                  }} />
                                ) : (
                                  // Keep other messages as is or handle undefined
                                  msg.message || ""
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                  
                  {/* New Table View for Datasets */}
                  <div className="rounded-md border shadow-sm overflow-hidden">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead className="w-[40px]"></TableHead>
                          <TableHead className="max-w-[250px] w-[250px]">Dataset</TableHead>
                          <TableHead className="w-[80px] text-center">Files</TableHead>
                          <TableHead className="w-[100px] text-center">Relevance</TableHead>
                          <TableHead className="w-[120px] text-center">Status</TableHead>
                          <TableHead className="w-[100px] text-center">Include in Analysis</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {datasets.map((dataset) => {
                          const relevanceScore = dataset.relevance?.relevance_score || dataset.similarity || 0;
                          
                          // Find the processing status for this dataset
                          const processingDataset = processingDatasets.find(d => d.id === dataset.id);
                          const processingStatus = processingDataset?.status;
                          
                          return (
                            <TableRow 
                              key={dataset.id}
                              className="cursor-pointer hover:bg-neutral-50 dark:hover:bg-neutral-800/50"
                            >
                              <TableCell className="p-2">
                                <div className="h-8 w-8 rounded overflow-hidden bg-neutral-200 flex-shrink-0">
                                  <img 
                                    src={getImageUrl(dataset)} 
                                    alt={`${getOrganizationName(dataset)} logo`}
                                    className="w-full h-full object-cover"
                                    onError={(e) => {
                                      const target = e.target as HTMLImageElement;
                                      target.src = `https://placehold.co/32x32/4F46E5/ffffff?text=D`;
                                    }}
                                  />
                                </div>
                              </TableCell>
                              <TableCell className="py-2 max-w-[250px] w-[250px]" onClick={() => handleDatasetSelect(dataset)}>
                                <div className="overflow-hidden">
                                  <p className="font-medium text-sm truncate" title={dataset.title}>{dataset.title}</p>
                                  <p className="text-xs text-neutral-500 truncate" title={getOrganizationName(dataset)}>
                                    {getOrganizationName(dataset)}
                                  </p>
                                </div>
                              </TableCell>
                              <TableCell className="text-center">
                                {dataset.file_count ? (
                                  <span className="text-xs">{dataset.file_count}</span>
                                ) : (
                                  <span className="text-xs text-neutral-400">—</span>
                                )}
                              </TableCell>
                              <TableCell className="text-center">
                                <div className="flex items-center justify-center">
                                  {relevanceScore > 0.7 ? (
                                    <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300">
                                      <CheckCircle2 className="h-3 w-3 mr-1" />
                                      {Math.round(relevanceScore * 100)}%
                                    </span>
                                  ) : (
                                    <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300">
                                      {Math.round(relevanceScore * 100)}%
                                    </span>
                                  )}
                                </div>
                              </TableCell>
                              <TableCell className="text-center">
                                {processingStatus ? (
                                  <div className="flex flex-col items-center justify-center">
                                    <Badge className={`${getStatusColor(processingStatus)}`}>
                                      {getStatusIcon(processingStatus)}
                                      <span className="ml-1">{getStatusLabel(processingStatus)}</span>
                                    </Badge>
                                    {/* Add progress bar for downloading status */}
                                    {processingStatus === 'downloading' && processingDataset.progress && (
                                      <Progress 
                                        value={processingDataset.progress} 
                                        className="h-1 w-16 mt-1" 
                                      />
                                    )}
                                  </div>
                                ) : (
                                  <span className="text-xs text-neutral-500">
                                    {isAnalyzing ? 
                                      (selectedDatasets[dataset.id] === true ? 'Queued' : 'Skipped') : 
                                      'Ready'}
                                  </span>
                                )}
                              </TableCell>
                              <TableCell className="text-center">
                                <Checkbox
                                  checked={selectedDatasets[dataset.id] === true}
                                  disabled={isAnalyzing}
                                  onCheckedChange={(checked) => {
                                    setSelectedDatasets(prev => ({
                                      ...prev,
                                      [dataset.id]: checked === true
                                    }));
                                  }}
                                  aria-label="Include in analysis"
                                  className="mx-auto"
                                />
                              </TableCell>
                            </TableRow>
                          );
                        })}
                      </TableBody>
                    </Table>
                  </div>
                </>
              ) : (
                <div className="text-center py-10">
                  <p className="text-neutral-500">No relevant datasets found for your query. Try a different question.</p>
                </div>
              )}
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
          opacity: 0;
          animation: fadeIn 0.5s ease-out forwards;
          animation-delay: var(--animation-delay, 0ms);
        }
        
        /* Smooth transition for dataset cards */
        .dataset-card {
          transition: opacity 0.5s ease, transform 0.5s ease, max-height 0.5s ease, margin 0.5s ease, padding 0.5s ease;
          opacity: 1;
          transform: scale(1);
          max-height: 500px;
          overflow: hidden;
        }
        
        .dataset-card.removing {
          opacity: 0;
          transform: scale(0.95);
          max-height: 0;
        }
      `}</style>

      {/* Dataset Preview Dialog */}
      <Dialog open={previewOpen} onOpenChange={setPreviewOpen}>
        <DialogContent className="max-w-4xl max-h-[90vh] overflow-hidden flex flex-col">
          <DialogHeader>
            <DialogTitle>{selectedPreview?.title}</DialogTitle>
            <DialogDescription>
              {selectedPreview?.preview?.file_name || "Dataset Preview"}
            </DialogDescription>
          </DialogHeader>
          
          <ScrollArea className="flex-1 overflow-auto p-4">
            {selectedPreview?.preview?.type === 'pdf' ? (
              <div className="space-y-4">
                <div className="flex items-center space-x-2 text-sm text-muted-foreground">
                  <FileText className="h-4 w-4" />
                  <span>PDF Document • {selectedPreview?.preview?.num_pages} pages</span>
                </div>
                
                {selectedPreview?.preview?.enhanced_summary && (
                  <div className="space-y-2">
                    <h3 className="text-sm font-medium">Document Summary</h3>
                    <p className="text-sm">{selectedPreview?.preview?.enhanced_summary}</p>
                  </div>
                )}
                
                {selectedPreview?.preview?.key_points && selectedPreview?.preview?.key_points.length > 0 && (
                  <div className="space-y-2">
                    <h3 className="text-sm font-medium">Key Points</h3>
                    <ul className="list-disc pl-5 space-y-1">
                      {selectedPreview?.preview?.key_points.map((point, i) => (
                        <li key={i} className="text-sm">{point}</li>
                      ))}
                    </ul>
                  </div>
                )}
                
                <div className="space-y-2">
                  <h3 className="text-sm font-medium">Text Sample</h3>
                  <div className="bg-muted p-3 rounded-md text-sm font-mono whitespace-pre-wrap">
                    {selectedPreview?.preview?.text_sample || "No text sample available"}
                  </div>
                </div>
              </div>
            ) : selectedPreview?.preview?.type === 'tabular' ? (
              <div className="space-y-4">
                <div className="flex items-center space-x-2 text-sm text-muted-foreground">
                  <Database className="h-4 w-4" />
                  <span>
                    Tabular Data • {selectedPreview?.preview?.row_count} rows • {selectedPreview?.preview?.column_count} columns
                  </span>
                </div>
                
                <div className="space-y-2">
                  <h3 className="text-sm font-medium">Data Sample</h3>
                  {selectedPreview?.preview?.sample_data ? (
                    <Table>
                      <TableHeader>
                        <TableRow>
                          {selectedPreview?.preview?.columns?.map((col, i) => (
                            <TableHead key={i} className="text-xs">{col}</TableHead>
                          ))}
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {selectedPreview?.preview?.sample_data.map((row, i) => (
                          <TableRow key={i}>
                            {selectedPreview?.preview?.columns?.map((col, j) => (
                              <TableCell key={j} className="text-xs p-2">{row[col]?.toString() || ""}</TableCell>
                            ))}
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  ) : (
                    <p className="text-sm text-muted-foreground">No sample data available</p>
                  )}
                </div>
              </div>
            ) : (
              <div className="text-center p-8 text-muted-foreground">
                <p>No preview available for this dataset</p>
              </div>
            )}
            
            {/* Assessment information */}
            {selectedPreview?.relevance && (
              <div className="mt-6 border-t pt-4 space-y-2">
                <h3 className="text-sm font-medium">Relevance Assessment</h3>
                <div className={`p-3 rounded-md ${
                  selectedPreview.relevance.is_relevant 
                    ? "bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-900/50" 
                    : "bg-orange-50 dark:bg-orange-900/20 border border-orange-200 dark:border-orange-900/50"
                }`}>
                  <div className="flex items-center mb-2">
                    {selectedPreview.relevance.is_relevant ? (
                      <CheckCircle2 className="h-4 w-4 text-green-500 mr-2" />
                    ) : (
                      <AlertCircle className="h-4 w-4 text-orange-500 mr-2" />
                    )}
                    <p className="text-sm font-medium">
                      {selectedPreview.relevance.is_relevant ? "Relevant" : "Not Relevant"} 
                      <span className="ml-1 font-normal">
                        (Score: {selectedPreview.relevance.relevance_score.toFixed(2)})
                      </span>
                    </p>
                  </div>
                  <p className="text-sm">{selectedPreview.relevance.reasoning}</p>
                </div>
              </div>
            )}
          </ScrollArea>
          
          <DialogFooter>
            <Button 
              variant="secondary" 
              onClick={() => setPreviewOpen(false)}
            >
              Close
            </Button>
            <Button
              onClick={() => handleDatasetSelect(selectedPreview!)}
            >
              Use Dataset
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
