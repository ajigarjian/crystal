"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardHeader, CardFooter } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { 
  Popover, 
  PopoverTrigger, 
  PopoverContent 
} from "@/components/ui/popover";
import { Textarea } from "@/components/ui/textarea";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Label } from "@/components/ui/label";
import Link from "next/link";
import { ChevronDown, ChevronUp, MessageSquareIcon, ThumbsUpIcon, BugIcon, LightbulbIcon, XIcon } from "lucide-react";
import { SummaryReport } from '@/components/SummaryReport';
import { SummaryReportSkeleton } from '@/components/SummaryReportSkeleton';
import { PreferredDatasetBadge } from '@/components/ui/dataset-badge';
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
import { streamSearchDatasets, warmFunctions, streamAnalyzeDatasets, submitFeedback } from "@/lib/firebase";
import Script from "next/script";
import { WebSearchSummary, WebSearchSummaryData } from '@/components/WebSearchSummary';
import { WebSearchSummarySkeleton } from '@/components/WebSearchSummarySkeleton';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Globe } from 'lucide-react';
import { PREFERRED_DATASET_ID_SET } from "@/lib/constants";

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
  progress?: number; // For progress bars
  analysis_results?: any; // Store the analysis results
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

// Define more specific types for analysis results
interface AnalysisResult {
  summary?: string;
  key_points?: string[];
  charts?: any[]; // Would be better to have a more specific type
  tables?: any[]; // Would be better to have a more specific type
  extracted_data?: Record<string, any>;
  [key: string]: any; // Allow for flexibility in results
}

// Feedback Widget Component using shadcn components
const FeedbackWidget = () => {
  const [open, setOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [feedbackType, setFeedbackType] = useState<string>("suggestion");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    
    console.log("Starting feedback submission");
    
    try {
      // Simplify the data structure to match waitlist as closely as possible
      // Keep only what's essential
      const result = await submitFeedback({
        feedback_type: feedbackType,
        title,
        description,
        email: email || undefined,
        page_url: window.location.href,
        tags: [],  // Simplify: remove the generateTags function for now
        metadata: {}  // Simplify: empty metadata for now
      });
      
      console.log("Submission successful:", result);
      
      // Show success message
      setSubmitted(true);
      
      // Reset form after 3 seconds
      setTimeout(() => {
        setOpen(false);
        setTimeout(() => {
          setSubmitted(false);
          setTitle("");
          setDescription("");
          setEmail("");
          setFeedbackType("suggestion");
        }, 300);
      }, 3000);
    } catch (error: any) {
      console.error("Error submitting feedback:", error);
      setError(error.message || "Failed to submit feedback. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button
          variant="default"
          size="sm"
          className="fixed bottom-6 right-6 z-50 rounded-full shadow-lg flex items-center gap-2 bg-green-600 hover:bg-green-700 text-white transition-all duration-200 hover:scale-105"
        >
          <MessageSquareIcon className="h-4 w-4" />
          <span>Feedback</span>
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>Send Feedback</DialogTitle>
          <DialogDescription>
            Help us improve Crystal with your suggestions and feedback.
          </DialogDescription>
        </DialogHeader>
        
        {submitted ? (
          <div className="py-6 space-y-4 text-center">
            <div className="mx-auto bg-green-100 text-green-800 rounded-full p-3 w-fit">
              <ThumbsUpIcon className="h-6 w-6" />
            </div>
            <h3 className="font-semibold text-lg">Thank you for your feedback!</h3>
            <p className="text-sm text-gray-500">
              We appreciate your input and will take it into consideration.
            </p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4 py-4">
            {error && (
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertTitle>Error</AlertTitle>
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
            
            <div className="space-y-2">
              <Label htmlFor="feedback-type" className="text-sm font-medium">
                Feedback Type
              </Label>
              <RadioGroup 
                value={feedbackType} 
                onValueChange={setFeedbackType}
                className="grid grid-cols-2 gap-2"
              >
                <div className="flex items-center space-x-2">
                  <RadioGroupItem value="suggestion" id="suggestion" />
                  <Label htmlFor="suggestion" className="flex items-center text-sm cursor-pointer">
                    <LightbulbIcon className="mr-1 h-3 w-3" />
                    Suggestion
                  </Label>
                </div>
                <div className="flex items-center space-x-2">
                  <RadioGroupItem value="bug" id="bug" />
                  <Label htmlFor="bug" className="flex items-center text-sm cursor-pointer">
                    <BugIcon className="mr-1 h-3 w-3" />
                    Bug report
                  </Label>
                </div>
                <div className="flex items-center space-x-2">
                  <RadioGroupItem value="feature_request" id="feature_request" />
                  <Label htmlFor="feature_request" className="flex items-center text-sm cursor-pointer">
                    <ThumbsUpIcon className="mr-1 h-3 w-3" />
                    Feature request
                  </Label>
                </div>
                <div className="flex items-center space-x-2">
                  <RadioGroupItem value="praise" id="praise" />
                  <Label htmlFor="praise" className="flex items-center text-sm cursor-pointer">
                    <ThumbsUpIcon className="mr-1 h-3 w-3" />
                    Praise
                  </Label>
                </div>
              </RadioGroup>
            </div>
            
            <div className="space-y-2">
              <Label htmlFor="feedback-title" className="text-sm font-medium">
                Title
              </Label>
              <Input
                id="feedback-title"
                placeholder="Brief summary of your feedback"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="w-full"
                required
              />
            </div>
            
            <div className="space-y-2">
              <Label htmlFor="feedback-description" className="text-sm font-medium">
                Description
              </Label>
              <Textarea
                id="feedback-description"
                placeholder="Please provide more details about your feedback..."
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="min-h-[100px]"
                required
              />
            </div>
            
            <div className="space-y-2">
              <Label htmlFor="feedback-email" className="text-sm font-medium">
                Email (optional)
              </Label>
              <Input
                id="feedback-email"
                type="email"
                placeholder="your@email.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
              <p className="text-xs text-gray-500">
                We'll only use this to follow up on your feedback if needed.
              </p>
            </div>
            
            <DialogFooter className="pt-2">
              <Button 
                variant="outline" 
                type="button" 
                onClick={() => setOpen(false)}
                disabled={submitting}
              >
                Cancel
              </Button>
              <Button 
                type="submit" 
                disabled={submitting}
                className="bg-green-600 hover:bg-green-700"
              >
                {submitting ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Submitting...
                  </>
                ) : "Submit Feedback"}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
};

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
  const [webSearchData, setWebSearchData] = useState<WebSearchSummaryData | null>(null);
  const [isWebSearchLoading, setIsWebSearchLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<string>("datasets");
  
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
                  file_count: data.data.resources?.length || 0,
                  status: 'starting' // Initialize with a status to show we're starting to process it
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
                  
                  // If the dataset has been assessed as not relevant, update status and then mark for removal
                  if (data.data.relevance && data.data.relevance.is_relevant === false) {
                    // Update the status to 'not_relevant' in a separate state update
                    // This ensures a complete render cycle before starting the removal process
                    setDatasets(currentDatasets => {
                      return currentDatasets.map(d => {
                          if (d.id === data.data.id) {
                            return {
                              ...d,
                            status: 'not_relevant'  // Set the status
                            };
                          }
                          return d;
                        });
                      });
                      
                    // Then after a delay, start the removal process in a separate update
                      setTimeout(() => {
                      setDatasets(current => {
                        return current.map(d => {
                          if (d.id === data.data.id) {
                    return {
                      ...d,
                              isRemoving: true  // Start the removal animation
                    };
                  }
                  return d;
                });
              });
              
                      // After animation completes, remove the dataset
                    setTimeout(() => {
                        setDatasets(current => current.filter(d => d.id !== data.data.id));
                      }, 1000); // Animation duration
                    }, 1500); // Show "Not relevant" status for 1.5 seconds
                  } 
                  // If the dataset is being assessed, show the assessing state
                  else if (data.data.status === 'assessing') {
                    updatedDatasets[datasetIndex].status = 'assessing';
                  }
                  // If the dataset is relevant, update its status
                  else if (data.data.relevance && data.data.relevance.is_relevant === true) {
                    updatedDatasets[datasetIndex].status = 'relevant';
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
              
              // UPDATE THE DATASET COUNT to match what the backend says is relevant
              setDatasetCount(data.data.relevant_count);
              
              // After the search is complete, sort datasets with preferred datasets first, then by relevance
              // This appears in the 'complete' case of processing streaming query results
              setDatasets(prev => {
                // Filter out any datasets that were marked as not relevant
                const filteredDatasets = [...prev]
                  .filter(dataset => !dataset.relevance || dataset.relevance.is_relevant !== false);
                
                // Sort with a compound sorting rule:
                // 1. Preferred datasets first (using PREFERRED_DATASET_ID_SET)
                // 2. Then by relevance score (descending)
                return filteredDatasets.sort((a, b) => {
                  // First check if either dataset is preferred
                  const aIsPreferred = PREFERRED_DATASET_ID_SET.has(a.id);
                  const bIsPreferred = PREFERRED_DATASET_ID_SET.has(b.id);
                  
                  // If their preferred status differs, preferred ones come first
                  if (aIsPreferred !== bIsPreferred) {
                    return aIsPreferred ? -1 : 1;
                  }
                  
                  // If both have same preferred status, sort by relevance score
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
                      status: data.status || 'assessing', // Make sure we show the assessing status during relevance check
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
            
            case 'assessing':
              // Dataset is being assessed for relevance
              setDatasets(prev => {
                return prev.map(d => {
                  if (d.id === data.dataset_id) {
                    return {
                      ...d,
                      status: 'assessing'
                    };
                  }
                  return d;
                });
              });
              
              const assessingMessage: StatusMessage = {
                id: Math.random().toString(36).substring(2, 9),
                message: data.message || `Assessing relevance of dataset`,
                timestamp: data.timestamp,
                type: 'status'
              };
              setStatusMessages(prev => [...prev, assessingMessage]);
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
                      status: data.is_relevant ? 'relevant' : 'not_relevant', // Update status based on relevance
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
            
            case 'findings':
              // Store summary findings data
              if (data.data) {
                // Use the key_data_points array directly
                setSummaryData({
                  summary: data.data.summary || '',
                  key_data_points: data.data.key_data_points || [],
                  sources: data.data.sources || []
                });
                
                // Add a status message that summary is generated
                const summaryMessage: StatusMessage = {
                  id: Math.random().toString(36).substring(2, 9),
                  message: `Generated summary with ${data.data.sources?.length || 0} sources`,
                  timestamp: data.timestamp || Date.now(),
                  type: 'status'
                };
                setStatusMessages(prev => [...prev, summaryMessage]);
                
                console.log("Received structured summary data:", data.data);
              }
              break;
            
            // We can ignore the formatted_findings message
            case 'formatted_findings':
              // Skip this - we're already using the structured data
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
    
    // If analysis is complete, go back to home page
    if (analysisComplete) {
      router.push('/');
      return;
    }
    
    // If search is already complete, start analysis instead of searching again
    if (searchComplete && datasets.length > 0) {
      startAnalysis();
    } else {
      // Otherwise do the search as before
      processStreamingQuery(query);
    }
  };

  // Handle dataset selection
  const handleDatasetSelect = (dataset: Dataset) => {
    // Call stream_analyze instead of redirecting to beta page
    const datasetIds = [dataset.id];
    startAnalysisWithDatasets(datasetIds);
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
    
    startAnalysisWithDatasets(datasetIds);
  };

  // Function to start analysis with selected datasets
  const startAnalysisWithDatasets = async (datasetIds: string[]) => {
    try {
      // Update UI state
      setIsAnalyzing(true);
      setError(null);
      setAnalysisComplete(false);
      setAnalysisResults(null);
      setSummaryData(null);
      setWebSearchData(null);  // Reset web search data
      setIsWebSearchLoading(true); // Show web search skeleton
      
      // Initialize processing datasets
      const datasetsToAnalyze = datasets.filter(d => datasetIds.includes(d.id));
      
      // Mark selected datasets as queued
      const initialProcessing = datasetsToAnalyze.map(dataset => ({
        ...dataset,
        status: 'queued' as const // Use const assertion to fix type issue
      }));
      
      setProcessingDatasets(initialProcessing);
      
      // Add a status message that analysis is starting
      const startMessage: StatusMessage = {
        id: Math.random().toString(36).substring(2, 9),
        message: `Starting analysis of ${datasetIds.length} datasets...`,
        timestamp: Date.now(),
        type: 'status'
      };
      setStatusMessages(prev => [...prev, startMessage]);
      
      // Call the Firebase function with streaming
      const analysisChunks = await streamAnalyzeDatasets(
        {
          query: query,
          dataset_ids: datasetIds
        },
        (chunk) => {
          console.log('Analysis chunk received:', chunk);
          
          // Handle different chunk types
          switch (chunk.type) {
            case 'status':
              // Global status update
              const statusMessage: StatusMessage = {
                id: Math.random().toString(36).substring(2, 9),
                message: chunk.message,
                timestamp: chunk.timestamp || Date.now(),
                type: 'status'
              };
              setStatusMessages(prev => [...prev, statusMessage]);
              break;
              
            case 'dataset_status':
              // Update status for a specific dataset
              setProcessingDatasets(prev => {
                return prev.map(d => {
                  if (d.id === chunk.dataset_id) {
                    return {
                      ...d,
                      status: chunk.status,
                      progress: chunk.progress // For progress bars
                    };
                  }
                  return d;
                });
              });
              
              // Also add a status message
              if (chunk.message) {
                const datasetStatusMessage: StatusMessage = {
                  id: Math.random().toString(36).substring(2, 9),
                  message: chunk.message,
                  timestamp: chunk.timestamp || Date.now(),
                  type: 'status'
                };
                setStatusMessages(prev => [...prev, datasetStatusMessage]);
              }
              break;
              
            case 'download_start':
              // Update dataset to downloading state
              setProcessingDatasets(prev => {
                return prev.map(d => {
                  if (d.id === chunk.dataset_id) {
                    return {
                      ...d,
                      status: 'downloading',
                      progress: 0 // Initialize progress
                    };
                  }
                  return d;
                });
              });
              break;
              
            case 'download_progress':
              // Update download progress
              setProcessingDatasets(prev => {
                return prev.map(d => {
                  if (d.id === chunk.dataset_id) {
                    return {
                      ...d,
                      progress: chunk.progress
                    };
                  }
                  return d;
                });
              });
              break;
              
            case 'download_complete':
              // Mark download as complete
              setProcessingDatasets(prev => {
                return prev.map(d => {
                  if (d.id === chunk.dataset_id) {
                    return {
                      ...d,
                      status: 'downloaded',
                      file_count: chunk.file_count || d.file_count,
                      progress: 100
                    };
                  }
                  return d;
                });
              });
              
              // Add status message
              const downloadMessage: StatusMessage = {
                id: Math.random().toString(36).substring(2, 9),
                message: `Downloaded ${chunk.file_count || 'all'} files for dataset "${chunk.dataset_title || 'selected dataset'}"`,
                timestamp: chunk.timestamp || Date.now(),
                type: 'status'
              };
              setStatusMessages(prev => [...prev, downloadMessage]);
              break;
              
            case 'analysis_start':
              // Update dataset to analyzing state
              setProcessingDatasets(prev => {
                return prev.map(d => {
                  if (d.id === chunk.dataset_id) {
                    return {
                      ...d,
                      status: 'analyzing'
                    };
                  }
                  return d;
                });
              });
              
              // Add status message
              const analysisStartMessage: StatusMessage = {
                id: Math.random().toString(36).substring(2, 9),
                message: `Analyzing dataset "${chunk.dataset_title || 'selected dataset'}"...`,
                timestamp: chunk.timestamp || Date.now(),
                type: 'status'
              };
              setStatusMessages(prev => [...prev, analysisStartMessage]);
              break;
              
            case 'analysis_result':
              // Store analysis results
              if (chunk.dataset_id) {
                setProcessingDatasets(prev => {
                  return prev.map(d => {
                    if (d.id === chunk.dataset_id) {
                      return {
                        ...d,
                        status: 'analyzed',
                        analysis_results: chunk.results
                      };
                    }
                    return d;
                  });
                });
              }
              
              // Update global analysis results
              setAnalysisResults(prev => {
                const newResults = prev ? {...prev} : {};
                if (chunk.dataset_id) {
                  newResults[chunk.dataset_id] = chunk.results;
                }
                return newResults;
              });
              break;
              
            case 'complete':
              // Analysis is complete
              setAnalysisComplete(true);
              setIsAnalyzing(false);
              
              // Add completion message
              const completeMessage: StatusMessage = {
                id: Math.random().toString(36).substring(2, 9),
                message: chunk.message || "Analysis complete!",
                timestamp: chunk.timestamp || Date.now(),
                type: 'status'
              };
              setStatusMessages(prev => [...prev, completeMessage]);
              
              // Update all datasets to completed status if they're not already
              setProcessingDatasets(prev => {
                return prev.map(d => {
                  if (d.status !== 'analyzed' && d.status !== 'error') {
                    return {
                      ...d,
                      status: 'analyzed'
                    };
                  }
                  return d;
                });
              });
              break;
              
            case 'error':
              // Handle errors
              if (chunk.dataset_id) {
                // Dataset-specific error
                setProcessingDatasets(prev => {
                  return prev.map(d => {
                    if (d.id === chunk.dataset_id) {
                      return {
                        ...d,
                        status: 'error',
                        error: chunk.message
                      };
                    }
                    return d;
                  });
                });
              }
              
              // Add error message to status
              const errorMessage: StatusMessage = {
                id: Math.random().toString(36).substring(2, 9),
                message: `Error: ${chunk.message}`,
                timestamp: chunk.timestamp || Date.now(),
                type: 'error'
              };
              setStatusMessages(prev => [...prev, errorMessage]);
              break;
              
            case 'web_search_summary':
              if (chunk.data) {
                setWebSearchData(chunk.data);
                setIsWebSearchLoading(false);
                
                // Add a status message for web search completion
                const webSearchMessage: StatusMessage = {
                  id: Math.random().toString(36).substring(2, 9),
                  message: `Web search completed with ${chunk.data.total_relevant_sources || 0} relevant sources`,
                  timestamp: chunk.timestamp || Date.now(),
                  type: 'status'
                };
                setStatusMessages(prev => [...prev, webSearchMessage]);
              }
              break;
              
            default:
              console.log('Unknown analysis chunk type:', chunk.type, chunk);
          }
        }
      );
      
      // If we reached here with no completion message, manually set as complete
      if (!analysisComplete) {
        setAnalysisComplete(true);
        setIsAnalyzing(false);
        
        const finalMessage: StatusMessage = {
          id: Math.random().toString(36).substring(2, 9),
          message: "Analysis complete!",
          timestamp: Date.now(),
          type: 'status'
        };
        setStatusMessages(prev => [...prev, finalMessage]);
      }
      
      return analysisChunks;
    } catch (err) {
      console.error("Error in dataset analysis:", err);
      setError(`Failed to analyze datasets: ${err instanceof Error ? err.message : String(err)}`);
      setIsAnalyzing(false);
      setIsWebSearchLoading(false);
      
      // Add error to status messages
      const errorMessage: StatusMessage = {
        id: Math.random().toString(36).substring(2, 9),
        message: `Error: Failed to analyze datasets: ${err instanceof Error ? err.message : String(err)}`,
        timestamp: Date.now(),
        type: 'error'
      };
      setStatusMessages(prev => [...prev, errorMessage]);
    }
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
    
    // Use the dataset ID to deterministically select a color
    // This ensures the same color is always used for the same dataset
    const colorIndex = dataset.id ? 
      Math.abs(dataset.id.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0)) % colors.length : 
      0;
    
    const color = colors[colorIndex];
    
    return `https://placehold.co/32x32/${color}/ffffff?text=${firstLetter}`;
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

  // Format milliseconds to readable duration
  const formatDuration = (startTime?: number, endTime?: number) => {
    if (!startTime || !endTime) return "—";
    const duration = endTime - startTime;
    return `${(duration / 1000).toFixed(2)}s`;
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
          text: "Checking validity...",
          color: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300"
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
          text: `Relevant`,
          color: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300"
        };
      case 'not_relevant':
        return { 
          icon: <AlertCircle className="h-4 w-4 text-orange-500" />, 
          text: `Not relevant`,
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
  const [analysisResults, setAnalysisResults] = useState<Record<string, AnalysisResult> | null>(null);
  const [summaryData, setSummaryData] = useState<any>(null);
  const [isSummaryLoading, setIsSummaryLoading] = useState(false);

  // Initialize datasets as selected by default
  useEffect(() => {
    if (datasets.length > 0) {
      const initialSelection = datasets.reduce((acc, dataset) => {
        // Check if this dataset is in the preferred set
        const isPreferred = PREFERRED_DATASET_ID_SET.has(dataset.id);
        acc[dataset.id] = isPreferred;
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
      setSummaryData(null);
      setWebSearchData(null);  // Reset web search data
      setIsWebSearchLoading(true); // Show web search skeleton
      
      // Initialize processing datasets
      const datasetsToAnalyze = datasets.filter(d => datasetIds.includes(d.id));
      
      // Mark selected datasets as queued
      const initialProcessing = datasetsToAnalyze.map(dataset => ({
        ...dataset,
        status: 'queued'
      }));
      
      setProcessingDatasets(initialProcessing);
      
      // Call the Firebase function with streaming
      const analysisChunks = await streamAnalyzeDatasets(
        {
          query: query,
          dataset_ids: datasetsToAnalyze.map(d => d.id),
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
              
            case 'findings':
              // Store structured summary findings data
              if (data.data) {
                setSummaryData({
                  summary: data.data.summary || '',
                  key_data_points: data.data.key_data_points || [],
                  sources: data.data.sources || []
                });
                
                console.log("Received structured summary data:", data.data);
              }
              break;
              
            case 'formatted_findings':
              // Store summary findings data
              if (data.data) {
                setSummaryData(data.data);
              }
              break;
              
            case 'web_search_results':
              // Store web search results
              if (data.data) {
                setWebSearchData(data.data);
                setIsWebSearchLoading(false);
              }
              break;
              
            case 'web_search_summary':
              // Store web search summary
              if (data.data) {
                setWebSearchData(data.data);
                setIsWebSearchLoading(false);
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
              setIsSummaryLoading(false);
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
      setIsWebSearchLoading(false);
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
      case 'relevant':
        return 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300';
      case 'not_relevant':
        return 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-300';
      case 'complete':  // Add this to handle 'complete' status
        return 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300';
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
      case 'relevant':
        return <CheckCircle2 className="h-3 w-3" />;
      case 'not_relevant':
        return <AlertCircle className="h-3 w-3" />;
      case 'complete':  // Add this to handle 'complete' status
        return <CheckCircle2 className="h-3 w-3" />;
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
      case 'relevant':
        return 'Relevant';
      case 'not_relevant':
        return 'Not Relevant';
      case 'complete':  // Add this to handle 'complete' status
        return 'Completed';
    }
  };

  // Add this state variable with your other state declarations
  const [showAllStatusHistory, setShowAllStatusHistory] = useState(false);

  // Add this before rendering status messages to check for duplicates
  useEffect(() => {
    const messageIds = statusMessages.map(m => m.id);
    const uniqueIds = new Set(messageIds);
    if (messageIds.length !== uniqueIds.size) {
      console.error("Duplicate status messages detected:", 
        messageIds.length - uniqueIds.size, 
        "duplicates");
      
      // Find which messages are duplicated
      const counts = {};
      messageIds.forEach(id => {
        counts[id] = (counts[id] || 0) + 1;
      });
      
      Object.entries(counts)
        .filter(([id, count]) => count > 1)
        .forEach(([id, count]) => {
          const duplicates = statusMessages.filter(m => m.id === id);
          console.error(`Message duplicated ${count} times:`, duplicates);
        });
    }
  }, [statusMessages]);

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
            
            {/* Add FeedbackWidget */}
            <FeedbackWidget />
            
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
          {/* Back button and logo section */}
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center">
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
            
            {/* Add FeedbackWidget */}
            <FeedbackWidget />
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
                  analysisComplete
                    ? "bg-green-600 hover:bg-green-700 text-white"
                    : !loading && searchComplete && datasets.length > 0
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
                    : analysisComplete
                      ? "New Query" 
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

          {/* Status message history - moved outside of loading condition to be visible at all times */}
          {statusMessages.length > 0 && (
            <div className="relative mb-4">
              <div 
                onClick={() => setShowAllStatusHistory(prev => !prev)} 
                className={`text-sm text-neutral-600 dark:text-neutral-400 ${loading ? 'animate-pulse' : ''} cursor-pointer flex items-center`}
              >
                {statusMessages[statusMessages.length - 1].message}
                {statusMessages.length > 1 && (
                  <ChevronDown className={`h-4 w-4 ml-1 transition-transform ${showAllStatusHistory ? 'rotate-180' : ''}`} />
                )}
              </div>
              
              {/* Expanded history view */}
              {showAllStatusHistory && statusMessages.length > 1 && (
                <div className="mt-2 pl-4 border-l-2 border-gray-300 dark:border-gray-700 space-y-2 max-h-60 overflow-y-auto status-message-container">
                  {statusMessages.slice(0, -1).map((msg, index) => (
                    <div 
                      key={msg.id}
                      className={`text-sm ${msg.type === 'error' ? 'text-red-500' : 'text-neutral-500 dark:text-neutral-400'}`}
                    >
                      {msg.message}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Loading state with live discovery feed */}
          {loading && (
            <div className="space-y-4">
              {/* Status messages section completely removed from here - do not render anything related to status messages in this block */}
              
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
                                   hover:border-green-200 flex flex-col border-neutral-200 relative
                                   ${dataset.isRemoving ? 'removing' : 'animate-fadeIn'}`}
                        onClick={() => handleDatasetSelect(dataset)}
                        style={style}
                      >
                        {/* Status indicator - if processing */}
                        {statusInfo && (
                          <div className={`absolute top-2 right-2 z-10 rounded-full px-2 py-0.5 flex items-center text-xs 
                                           ${statusInfo.color} transition-opacity duration-500
                                           ${dataset.isRemoving ? 'opacity-0' : 'opacity-100'}`}>
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
                              <h3 className="text-sm font-medium leading-tight line-clamp-2 mb-0.5">
                                {dataset.title}
                              </h3>
                              <p className="text-xs text-neutral-500 truncate" title={getOrganizationName(dataset)}>
                                {getOrganizationName(dataset)}
                              </p>
                              {/* Remove badge from here */}
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
                  
                  {/* New Table View for Datasets */}
                  <div className="rounded-md border shadow-sm overflow-hidden">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead className="w-[40px]"></TableHead>
                          {/* Increase the width of the Dataset column */}
                          <TableHead className="max-w-[430px] w-[430px]">Dataset</TableHead>
                          {/* Relevance column removed */}
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
                              className={`
                                ${isAnalyzing ? 'opacity-70 pointer-events-none select-none' : 'cursor-pointer hover:bg-neutral-50 dark:hover:bg-neutral-800/50'}
                              `}
                              onClick={(e) => {
                                // Only allow clicking if not analyzing
                                if (isAnalyzing) return;
                                
                                // Prevent toggling if clicking on a button, checkbox, or interactive element
                                if (e.target instanceof HTMLElement && 
                                    (e.target.closest('button') || 
                                     e.target.tagName === 'INPUT' ||
                                     e.target.closest('input') ||
                                     e.target.closest('label') ||
                                     e.target.closest('.checkbox-container'))) {
                                  return;
                                }
                                
                                // Toggle the checkbox for this dataset
                                setSelectedDatasets(prev => ({
                                  ...prev,
                                  [dataset.id]: !(prev[dataset.id] === true)
                                }));
                              }}
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
                              
                              <TableCell className="py-2 max-w-[430px] w-[430px]">
                                <div className="overflow-hidden">
                                  <div className="flex items-center space-x-2">
                                    <p className="font-medium text-sm truncate" title={dataset.title}>{dataset.title}</p>
                                    {/* Add relevance chip next to title */}
                                    {relevanceScore > 0.65 ? (
                                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300 whitespace-nowrap">
                                        <CheckCircle2 className="h-3 w-3 mr-1" />
                                        {Math.round(relevanceScore * 100)}%
                                      </span>
                                    ) : (
                                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300 whitespace-nowrap">
                                        {Math.round(relevanceScore * 100)}%
                                      </span>
                                    )}
                                  </div>
                                  <div className="flex justify-between items-center">
                                    <p className="text-xs text-neutral-500 truncate" title={getOrganizationName(dataset)}>
                                      {getOrganizationName(dataset)}
                                    </p>
                                  </div>
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
                                <div className="flex items-center justify-center">
                                  <div className="relative flex items-center">
                                    <div className="w-4 h-4 flex items-center justify-center">
                                      <Checkbox
                                        checked={selectedDatasets[dataset.id] === true}
                                        disabled={isAnalyzing}
                                        onCheckedChange={(checked) => {
                                          if (isAnalyzing) return; // Extra protection
                                          setSelectedDatasets(prev => ({
                                            ...prev,
                                            [dataset.id]: checked === true
                                          }));
                                        }}
                                        aria-label="Include in analysis"
                                      />
                                    </div>
                                    <PreferredDatasetBadge datasetId={dataset.id} />
                                  </div>
                                </div>
                              </TableCell>
                            </TableRow>
                          );
                        })}
                      </TableBody>
                    </Table>
                  </div>

                  {/* Analysis Results Section */}
                  {(isAnalyzing || analysisComplete) && (
                    <div className="mt-6 space-y-4">
                      
                      <Tabs 
                        defaultValue="datasets" 
                        value={activeTab} 
                        onValueChange={setActiveTab}
                        className="w-full"
                      >
                        <TabsList className="grid w-full grid-cols-2 mb-4">
                          <TabsTrigger value="datasets" className="flex items-center gap-2">
                            <Database className="h-4 w-4" />
                            <span>Dataset Summary</span>
                          </TabsTrigger>
                          <TabsTrigger value="webSearch" className="flex items-center gap-2">
                            <Globe className="h-4 w-4" />
                            <span>Web Research</span>
                          </TabsTrigger>
                        </TabsList>
                        
                        <TabsContent value="datasets" className="space-y-4">
                          {isAnalyzing && !summaryData ? (
                            <SummaryReportSkeleton query={query} />
                          ) : summaryData ? (
                            <SummaryReport 
                              query={query}
                              summary={summaryData.summary || ''}
                              keyFindings={summaryData.key_data_points || []}
                              sources={summaryData.sources || []}
                            />
                          ) : (
                            <div className="text-center p-8 text-muted-foreground">
                              <p>No dataset analysis available</p>
                            </div>
                          )}
                          
                          {processingDatasets
                            .filter(d => d.analysis_results)
                            .map(dataset => (
                              <Card key={dataset.id} className="overflow-hidden mt-4">
                                <CardHeader className="p-4 bg-muted/50">
                                  <h3 className="text-lg font-semibold">{dataset.title}</h3>
                                </CardHeader>
                                <div className="p-4">
                                  {dataset.analysis_results ? (
                                    <div>
                                      <div className="text-sm text-muted-foreground">
                                        {dataset.analysis_results.summary}
                                      </div>
                                      {dataset.analysis_results.key_points && (
                                        <div className="mt-4">
                                          <h4 className="text-sm font-semibold mb-2">Key Points</h4>
                                          <ul className="list-disc pl-5 text-sm text-muted-foreground">
                                            {dataset.analysis_results.key_points.map((point: string, idx: number) => (
                                              <li key={idx}>{point}</li>
                                            ))}
                                          </ul>
                                        </div>
                                      )}
                                    </div>
                                  ) : (
                                    <div className="text-sm text-muted-foreground italic">
                                      No detailed analysis available for this dataset.
                                    </div>
                                  )}
                                </div>
                              </Card>
                            ))}
                        </TabsContent>
                        
                        <TabsContent value="webSearch" className="space-y-4">
                          {isWebSearchLoading ? (
                            <WebSearchSummarySkeleton />
                          ) : webSearchData ? (
                            <WebSearchSummary data={webSearchData} />
                          ) : (
                            <div className="text-center p-8 text-muted-foreground">
                              <p>No web search results available yet</p>
                            </div>
                          )}
                        </TabsContent>
                      </Tabs>
                    </div>
                  )}
                </>
              ) : (
                <div className="text-center py-10">
                  <p className="text-neutral-500">Sorry, we don't seem to have any datasets for this query yet. </p>
                  <p className="text-neutral-500">We're working hard to add more sources, please click "Feedback" to tell us!</p>
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
