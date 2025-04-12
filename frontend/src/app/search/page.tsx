"use client";

import Link from 'next/link';
import React, { useState, useRef, useEffect } from 'react';
import { Input } from "@/components/ui/input";
import { Search, Loader2, ChevronDown, ChevronUp, FileText, ExternalLink, Info, ChevronRight, Download, X, Lock, AlertCircle, Lightbulb, MessageSquare, ThumbsUp, Bug, ArrowRight } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { streamSearchDatasets } from "@/lib/firebase";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  TableCaption,
  TableFooter,
} from "@/components/ui/table";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
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
  Drawer,
  DrawerContent,
  DrawerDescription,
  DrawerHeader,
  DrawerTitle,
  DrawerTrigger,
  DrawerFooter,
  DrawerClose,
} from "@/components/ui/drawer";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Textarea } from "@/components/ui/textarea";
import { submitFeedback } from "@/lib/firebase";
import { MessageSquareIcon, ThumbsUpIcon, BugIcon } from "lucide-react";

// Add the FeedbackWidget component
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
            Help us improve Crystal with your suggestions.
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
                    <Lightbulb className="mr-1 h-3 w-3" />
                    Suggestion
                  </Label>
                </div>
                <div className="flex items-center space-x-2">
                  <RadioGroupItem value="bug" id="bug" />
                  <Label htmlFor="bug" className="flex items-center text-sm cursor-pointer">
                    <Bug className="mr-1 h-3 w-3" />
                    Bug report
                  </Label>
                </div>
                <div className="flex items-center space-x-2">
                  <RadioGroupItem value="feature_request" id="feature_request" />
                  <Label htmlFor="feature_request" className="flex items-center text-sm cursor-pointer">
                    <ThumbsUp className="mr-1 h-3 w-3" />
                    Feature request
                  </Label>
                </div>
                <div className="flex items-center space-x-2">
                  <RadioGroupItem value="praise" id="praise" />
                  <Label htmlFor="praise" className="flex items-center text-sm cursor-pointer">
                    <ThumbsUp className="mr-1 h-3 w-3" />
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

// Add the new enum and state
enum SearchStatus {
  IDLE = "idle",          
  SEARCHING = "searching",
  COMPLETE = "complete"   
}

export default function SearchPage() {
  const [query, setQuery] = useState('');
  const [searchStatus, setSearchStatus] = useState<SearchStatus>(SearchStatus.IDLE);
  const [searchProgress, setSearchProgress] = useState(0);
  const [statusMessage, setStatusMessage] = useState('');
  const [datasets, setDatasets] = useState<any[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  const allDatasetsRef = useRef<any[]>([]);  // Store all datasets, relevant or not
  const [expandedDataset, setExpandedDataset] = useState<string | null>(null);
  const [executionTime, setExecutionTime] = useState<number>(0);
  const [ellipsis, setEllipsis] = useState('');
  const [activeTab, setActiveTab] = useState<string>("data.gov");

  // Focus the input field when the page loads
  useEffect(() => {
    if (inputRef.current) {
      inputRef.current.focus();
    }
  }, []);

  // Update the progress increment effect
  useEffect(() => {
    if (searchStatus === SearchStatus.SEARCHING && searchProgress < 90) {
      const timer = setTimeout(() => {
        // Accelerate at the beginning and slow down near 90%
        const increment = searchProgress < 30 ? 5 : searchProgress < 60 ? 2 : 0.5;
        setSearchProgress(prev => Math.min(prev + increment, 90));
      }, 500);
      return () => clearTimeout(timer);
    }
  }, [searchStatus, searchProgress]);

  // Update the dataset filter effect
  useEffect(() => {
    if (searchStatus === SearchStatus.COMPLETE && executionTime > 0) {
      // Only run this effect when a search is actually complete, not on initial load
      const allDatasets = allDatasetsRef.current;
      
      // Only show relevant datasets
      const relevantDatasets = allDatasets
        .filter(dataset => dataset.relevance && dataset.relevance.is_relevant === true)
        .sort((a, b) => 
          ((b.relevance?.relevance_score || b.similarity || 0) - 
           (a.relevance?.relevance_score || a.similarity || 0))
        );
      
      setDatasets(relevantDatasets);
    }
  }, [searchStatus, executionTime]);

  // Update the ellipsis animation effect
  useEffect(() => {
    if (searchStatus === SearchStatus.SEARCHING) {
      const ellipsisAnimation = setInterval(() => {
        setEllipsis(prev => {
          if (prev === '') return '.';
          if (prev === '.') return '..';
          if (prev === '..') return '...';
          return '';
        });
      }, 1000);
      
      return () => clearInterval(ellipsisAnimation);
    } else {
      setEllipsis('');
    }
  }, [searchStatus]);

  // Update the search handler
  const handleSearch = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!query.trim() || searchStatus === SearchStatus.SEARCHING) return;

    // Reset state for new search - more thorough cleanup
    setSearchStatus(SearchStatus.SEARCHING);
    setSearchProgress(0);
    setStatusMessage('Initiating search...');
    setDatasets([]);
    allDatasetsRef.current = []; // Reset the raw datasets ref
    setExpandedDataset(null);
    setExecutionTime(0); // Reset execution time as well
    setEllipsis(''); // Ensure ellipsis is reset

    try {
      // Start the streaming search
      await streamSearchDatasets(
        {
          query: query.trim(),
          search_method: null, // hybrid search
          similarity_threshold: 0.35,
          max_results: 20
        },
        (chunk) => {
          // Process incoming chunks
          if (chunk.type === 'status') {
            setStatusMessage(chunk.message);
            // Bump progress a bit for each status message
            setSearchProgress(prev => Math.min(prev + 3, 90));
          } 
          else if (chunk.type === 'dataset') {
            // Store dataset in our ref but don't display yet
            const allDatasets = allDatasetsRef.current;
            // Check if we already have this dataset ID
            if (!allDatasets.some(d => d.id === chunk.data.id)) {
              // Use immutable update but more efficiently
              allDatasetsRef.current.push(chunk.data);
              
              // Show datasets immediately as they come in - more efficiently
              setDatasets(prev => {
                const newDatasets = [...prev];
                newDatasets.push(chunk.data);
                return newDatasets;
              });
            }
            
            // Small progress boost for each dataset found
            setSearchProgress(prev => Math.min(prev + 1, 90));
          }
          else if (chunk.type === 'dataset_update') {
            // Update dataset in our ref - more efficiently
            const allDatasets = allDatasetsRef.current;
            for (let i = 0; i < allDatasets.length; i++) {
              if (allDatasets[i].id === chunk.data.id) {
                allDatasetsRef.current[i] = { ...allDatasets[i], ...chunk.data };
                break;
              }
            }
            
            // Update the displayed datasets, maintaining order but updating relevance
            setDatasets(prev => {
              const updatedDatasets = [...prev];
              
              for (let i = 0; i < updatedDatasets.length; i++) {
                if (updatedDatasets[i].id === chunk.data.id) {
                  updatedDatasets[i] = { ...updatedDatasets[i], ...chunk.data };
                  break;
                }
              }
              
              // Filter out irrelevant datasets
              return updatedDatasets.filter(dataset => 
                !dataset.relevance || dataset.relevance.is_relevant !== false
              );
            });
          }
          else if (chunk.type === 'complete') {
            // Search complete
            setSearchProgress(100); // Set to 100% before transitioning to complete
            
            // Add a small delay before fully completing, to show the 100% state briefly
            setTimeout(() => {
              setSearchStatus(SearchStatus.COMPLETE);
              setSearchProgress(0);
              
              // Store the execution time
              if (chunk.data && chunk.data.execution_time) {
                setExecutionTime(chunk.data.execution_time);
              }
              
              // Calculate our own relevant count based on actual processed datasets
              const allDatasets = allDatasetsRef.current;
              const relevantDatasets = allDatasets.filter(
                dataset => dataset.relevance && dataset.relevance.is_relevant === true
              );
              
              // Set status message with our calculated counts
              setStatusMessage(
                `Found ${relevantDatasets.length} relevant datasets.`
              );
            }, 300); // Brief delay to show 100% state
          }
        }
      );
    } catch (error: any) {
      console.error("Search error:", error);
      setStatusMessage(`Error: ${error.message || 'An unknown error occurred'}`);
      setSearchStatus(SearchStatus.COMPLETE);
      setSearchProgress(0);
    }
  };

  // Update key down handler
  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && query.trim() && searchStatus !== SearchStatus.SEARCHING) {
      handleSearch();
    }
  };

  // Toggle expansion function
  const toggleExpand = (datasetId: string) => {
    setExpandedDataset(expandedDataset === datasetId ? null : datasetId);
  };
  
  // Get organization image
  const getOrganizationImage = (dataset: any) => {
    // Check all possible places where image URLs might exist
    
    // 1. Direct image_url on dataset
    if (dataset.image_url && typeof dataset.image_url === 'string') {
      return dataset.image_url;
    }
    
    // 2. Inside organization object
    if (dataset.organization) {
      if (typeof dataset.organization === 'object') {
        // Check various possible field names
        if (dataset.organization.image_url) {
          return dataset.organization.image_url;
        }
        if (dataset.organization.logo) {
          return dataset.organization.logo;
        }
        if (dataset.organization.icon) {
          return dataset.organization.icon;
        }
      }
    }
    
    // 3. Check for separate organization_image_url field
    if (dataset.organization_image_url) {
      return dataset.organization_image_url;
    }
    
    // Get organization name for the fallback initial
    let orgName = '';
    if (dataset.organization) {
      if (typeof dataset.organization === 'object') {
        orgName = dataset.organization.name || dataset.organization.title || '';
      } else {
        orgName = dataset.organization; // Handle case where organization is a string
      }
    } else {
      orgName = dataset.organization_title || dataset.organization_name || '';
    }
    
    // Return the first letter of organization name
    return orgName ? orgName.charAt(0).toUpperCase() : 'U';
  };

  // Get organization name
  const getOrganizationName = (dataset: any) => {
    if (dataset.organization) {
      if (typeof dataset.organization === 'object') {
        return dataset.organization.title || dataset.organization.name || 'Unknown source';
      } else {
        return dataset.organization; // Handle case where organization is a string
      }
    }
    return dataset.organization_title || dataset.organization_name || 'Unknown source';
  };
  
  // Format file type
  const getFileType = (resource: any) => {
    if (resource.format) return resource.format.toUpperCase();
    
    // Try to extract from URL
    const url = resource.url || '';
    const extension = url.split('.').pop()?.toLowerCase();
    
    if (['csv', 'json', 'xml', 'pdf', 'xls', 'xlsx', 'txt', 'zip'].includes(extension || '')) {
      return extension?.toUpperCase();
    }
    
    return 'FILE';
  };

  // Get formatted tag list
  const getTagsList = (dataset: any, maxTags = 3) => {
    if (!dataset.tags || !dataset.tags.length) return null;
    
    const tags = dataset.tags.slice(0, maxTags).map((tag: any, i: number) => {
      const tagText = typeof tag === 'string' ? tag : (tag.display_name || tag.name || '');
      return (
        <Badge 
          key={i} 
          variant="secondary"
          className="text-xs bg-gray-100 text-gray-800 mr-1"
        >
          {tagText}
        </Badge>
      );
    });
    
    if (dataset.tags.length > maxTags) {
      tags.push(
        <Badge key="more" variant="outline" className="text-xs text-gray-500">
          +{dataset.tags.length - maxTags}
        </Badge>
      );
    }
    
    return tags;
  };

  return (
    <div className="flex flex-col min-h-screen bg-gray-50 text-gray-900">
      {/* Header with logo */}
      <div className="flex h-16 shrink-0 items-center justify-between px-4">
        <div className="flex items-center">
          <Link href="/">
            <div className="flex items-center cursor-pointer hover:opacity-80 transition-opacity">
              <img 
                src="/images/crystal-icon.png" 
                alt="Crystal Logo" 
                className="h-6 w-6 mr-2 filter brightness-0" 
              />
              <h1 className="text-lg font-bold text-gray-900" style={{ fontFamily: 'Satoshi, sans-serif' }}>Crystal</h1>
            </div>
          </Link>
        </div>
        
        {/* Add navigation links including waitlist in the same style as landing page */}
        <div className="flex gap-4 items-center">
          <Link href="/waitlist" target="_blank">
            <Button 
              variant="link" 
              className="text-gray-900 flex items-center gap-2 hover:text-gray-700 transition-colors"
              style={{ fontFamily: 'var(--font-geist-sans)' }}
            >
              Join <Badge className="bg-purple-500 hover:bg-purple-500 text-xs py-0 px-1.5 text-white font-normal rounded-sm">BETA</Badge> Waitlist <ArrowRight className="h-4 w-4" />
            </Button>
          </Link>
          
          {/* Feedback widget */}
          <FeedbackWidget />
        </div>
      </div>
      
      {/* Search section */}
      <div className="max-w-3xl mx-auto w-full px-4 pt-12 pb-8">
        <div className="relative w-full transition-all overflow-hidden rounded-xl">
          <Input
            ref={inputRef}
            placeholder="Search for datasets..."
            className="pl-12 pr-4 py-7 text-lg w-full rounded-xl border-gray-300 transition-all shadow-sm hover:shadow focus:shadow-md relative z-10 bg-white text-gray-900 selection:bg-green-100 selection:text-green-900"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={searchStatus === SearchStatus.SEARCHING}
          />
          <div 
            className={`absolute left-4 top-1/2 -translate-y-1/2 transition-colors duration-200 ease-in-out z-20 ${
              searchStatus !== SearchStatus.SEARCHING && query.trim() ? 'cursor-pointer' : ''
            }`}
            onClick={searchStatus !== SearchStatus.SEARCHING && query.trim() ? handleSearch : undefined}
          >
            {searchStatus === SearchStatus.SEARCHING ? (
              <motion.div
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{ opacity: 1, scale: 1 }}
                className="relative"
              >
                <Loader2 className="h-5 w-5 text-green-500 animate-spin" />
              </motion.div>
            ) : (
              <Search 
                className={`h-5 w-5 transition-all ${
                  query.trim() 
                    ? 'text-green-500 scale-110 drop-shadow-[0_0_12px_rgba(34,197,94,0.8)] filter brightness-110' 
                    : 'text-gray-400'
                }`} 
              />
            )}
          </div>
          
          {searchStatus !== SearchStatus.SEARCHING && query.trim() && (
            <div className="absolute right-4 top-1/2 -translate-y-1/2 text-sm text-gray-400 opacity-70 z-20">
              Press Enter to search
            </div>
          )}
          
          {searchStatus === SearchStatus.SEARCHING && searchProgress > 0 && (
            <div className="absolute bottom-0 left-0 w-full h-0.5 z-0">
              <motion.div
                initial={{ width: 0 }}
                animate={{ width: `${searchProgress}%` }}
                transition={{ ease: "easeOut" }}
                className="h-full bg-green-500"
              />
            </div>
          )}
        </div>
      </div>
      
      {/* Dataset results section - TABLE VIEW */}
      <div className="flex-1 max-w-7xl mx-auto w-full px-4 pb-12">
        <AnimatePresence>
          {(searchStatus === SearchStatus.SEARCHING || 
            (searchStatus === SearchStatus.COMPLETE && datasets.length > 0)) && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.5 }}
              className="mt-6"
            >
              <motion.div 
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.5 }}
                className="flex items-center justify-between mb-2"
              >
                <h2 className="text-sm text-gray-900">
                  {searchStatus === SearchStatus.SEARCHING ? (
                    <span className="flex items-center">
                      <span className="text-gray-700">
                        {/* Remove any trailing ellipsis from the status message */}
                        {statusMessage.replace(/\.{3,}$/, '')}
                        <span className="inline-block w-8">{ellipsis}</span>
                      </span>
                    </span>
                  ) : (
                    searchStatus === SearchStatus.COMPLETE && datasets.length > 0 ? 
                    `${statusMessage || `Found ${datasets.length} relevant datasets in ${executionTime.toFixed(1)} seconds.`}` :
                    ''
                  )}
                </h2>
              </motion.div>
              
              <Tabs 
                defaultValue="data.gov" 
                value={activeTab}
                onValueChange={setActiveTab}
                className="mb-0"
              >
                <TabsList className="bg-white border border-gray-200 rounded-md border-b-0 rounded-b-none">
                  <TabsTrigger value="data.gov" className="data-[state=active]:bg-green-50 data-[state=active]:text-green-700">
                    data.gov
                  </TabsTrigger>
                  
                  {/* Replace each locked tab with a tooltip wrapper */}
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <div className="cursor-not-allowed">
                          <TabsTrigger 
                            value="census" 
                            disabled 
                            className="opacity-60 text-gray-400 hover:!bg-transparent hover:!text-gray-400 data-[state=active]:bg-transparent" 
                          >
                            <div className="flex items-center gap-1.5">
                              U.S. Census Bureau
                              <Lock className="h-3.5 w-3.5 text-gray-400" />
                            </div>
                          </TabsTrigger>
                        </div>
                      </TooltipTrigger>
                      <TooltipContent side="bottom" className="bg-white p-3 shadow-lg border border-gray-200">
                        <div className="text-sm">
                          <Link 
                            href="/waitlist" 
                            target="_blank"
                            className="text-gray-900 hover:text-green-700 font-medium inline-flex items-center gap-1.5 transition-colors"
                          >
                            Join beta waitlist for early access <ExternalLink className="h-3 w-3" />
                          </Link>
                        </div>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>

                  {/* Repeat for other locked tabs */}
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <div className="cursor-not-allowed">
                          <TabsTrigger 
                            value="bls" 
                            disabled 
                            className="opacity-60 text-gray-400 hover:!bg-transparent hover:!text-gray-400 data-[state=active]:bg-transparent" 
                          >
                            <div className="flex items-center gap-1.5">
                              U.S. BLS
                              <Lock className="h-3.5 w-3.5 text-gray-400" />
                            </div>
                          </TabsTrigger>
                        </div>
                      </TooltipTrigger>
                      <TooltipContent side="bottom" className="bg-white p-3 shadow-lg border border-gray-200">
                        <div className="text-sm">
                          <Link 
                            href="/waitlist" 
                            target="_blank"
                            className="text-gray-900 hover:text-green-700 font-medium inline-flex items-center gap-1.5 transition-colors"
                          >
                            Join beta waitlist for early access <ExternalLink className="h-3 w-3" />
                          </Link>
                        </div>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>

                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <div className="cursor-not-allowed">
                          <TabsTrigger 
                            value="eia" 
                            disabled 
                            className="opacity-60 text-gray-400 hover:!bg-transparent hover:!text-gray-400 data-[state=active]:bg-transparent" 
                          >
                            <div className="flex items-center gap-1.5">
                              U.S. EIA
                              <Lock className="h-3.5 w-3.5 text-gray-400" />
                            </div>
                          </TabsTrigger>
                        </div>
                      </TooltipTrigger>
                      <TooltipContent side="bottom" className="bg-white p-3 shadow-lg border border-gray-200">
                        <div className="text-sm">
                          <Link 
                            href="/waitlist" 
                            target="_blank"
                            className="text-gray-900 hover:text-green-700 font-medium inline-flex items-center gap-1.5 transition-colors"
                          >
                            Join beta waitlist for early access <ExternalLink className="h-3 w-3" />
                          </Link>
                        </div>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>

                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <div className="cursor-not-allowed">
                          <TabsTrigger 
                            value="noaa" 
                            disabled 
                            className="opacity-60 text-gray-400 hover:!bg-transparent hover:!text-gray-400 data-[state=active]:bg-transparent" 
                          >
                            <div className="flex items-center gap-1.5">
                              NOAA
                              <Lock className="h-3.5 w-3.5 text-gray-400" />
                            </div>
                          </TabsTrigger>
                        </div>
                      </TooltipTrigger>
                      <TooltipContent side="bottom" className="bg-white p-3 shadow-lg border border-gray-200">
                        <div className="text-sm">
                          <Link 
                            href="/waitlist" 
                            target="_blank"
                            className="text-gray-900 hover:text-green-700 font-medium inline-flex items-center gap-1.5 transition-colors"
                          >
                            Join beta waitlist for early access <ExternalLink className="h-3 w-3" />
                          </Link>
                        </div>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>

                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <div className="cursor-not-allowed">
                          <TabsTrigger 
                            value="cdc" 
                            disabled 
                            className="opacity-60 text-gray-400 hover:!bg-transparent hover:!text-gray-400 data-[state=active]:bg-transparent" 
                          >
                            <div className="flex items-center gap-1.5">
                              CDC
                              <Lock className="h-3.5 w-3.5 text-gray-400" />
                            </div>
                          </TabsTrigger>
                        </div>
                      </TooltipTrigger>
                      <TooltipContent side="bottom" className="bg-white p-3 shadow-lg border border-gray-200">
                        <div className="text-sm">
                          <Link 
                            href="/waitlist" 
                            target="_blank"
                            className="text-gray-900 hover:text-green-700 font-medium inline-flex items-center gap-1.5 transition-colors"
                          >
                            Join beta waitlist for early access <ExternalLink className="h-3 w-3" />
                          </Link>
                        </div>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>

                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <div className="cursor-not-allowed">
                          <TabsTrigger 
                            value="usgs" 
                            disabled 
                            className="opacity-60 text-gray-400 hover:!bg-transparent hover:!text-gray-400 data-[state=active]:bg-transparent" 
                          >
                            <div className="flex items-center gap-1.5">
                              USGS
                              <Lock className="h-3.5 w-3.5 text-gray-400" />
                            </div>
                          </TabsTrigger>
                        </div>
                      </TooltipTrigger>
                      <TooltipContent side="bottom" className="bg-white p-3 shadow-lg border border-gray-200">
                        <div className="text-sm">
                          <Link 
                            href="/waitlist" 
                            target="_blank"
                            className="text-gray-900 hover:text-green-700 font-medium inline-flex items-center gap-1.5 transition-colors"
                          >
                            Join beta waitlist for early access <ExternalLink className="h-3 w-3" />
                          </Link>
                        </div>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>

                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <div className="cursor-not-allowed">
                          <TabsTrigger 
                            value="fred" 
                            disabled 
                            className="opacity-60 text-gray-400 hover:!bg-transparent hover:!text-gray-400 data-[state=active]:bg-transparent" 
                          >
                            <div className="flex items-center gap-1.5">
                              FRED
                              <Lock className="h-3.5 w-3.5 text-gray-400" />
                            </div>
                          </TabsTrigger>
                        </div>
                      </TooltipTrigger>
                      <TooltipContent side="bottom" className="bg-white p-3 shadow-lg border border-gray-200">
                        <div className="text-sm">
                          <Link 
                            href="/waitlist" 
                            target="_blank"
                            className="text-gray-900 hover:text-green-700 font-medium inline-flex items-center gap-1.5 transition-colors"
                          >
                            Join beta waitlist for early access <ExternalLink className="h-3 w-3" />
                          </Link>
                        </div>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                </TabsList>
              </Tabs>
              
              <div className="rounded-md rounded-tl-none border border-gray-200 bg-white">
                <Table className="table-fixed">
                  <TableHeader>
                    <TableRow className="hover:!bg-transparent border-b border-gray-200">
                      <TableHead className="w-[5%] h-10 text-gray-700"></TableHead>
                      <TableHead className="w-[25%] font-medium text-gray-700">Source</TableHead>
                      <TableHead className="w-[50%] font-medium text-gray-700">Dataset</TableHead>
                      <TableHead className="w-[10%] text-center font-medium text-gray-700">Relevance</TableHead>
                      <TableHead className="w-[10%] text-center font-medium text-gray-700">Resources</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {/* Always show real dataset rows if we have any */}
                    {datasets.map((dataset, index) => (
                        <React.Fragment key={dataset.id}>
                          <TableRow 
                            className={`border-b border-gray-200 hover:bg-gray-50 transition-colors cursor-pointer ${
                              expandedDataset === dataset.id ? 'bg-gray-50' : ''
                            }`}
                            onClick={() => toggleExpand(dataset.id)}
                          >
                            <TableCell className="py-4 px-4">
                              <motion.div
                                initial={{ rotate: 0 }}
                                animate={{ rotate: expandedDataset === dataset.id ? 90 : 0 }}
                                transition={{ duration: 0.2 }}
                                className="flex items-center justify-center w-5 h-5"
                              >
                                <ChevronRight className="h-4 w-4 text-gray-500" />
                              </motion.div>
                            </TableCell>
                          <TableCell className="py-4 max-w-[200px]">
                              <div className="flex items-center gap-2">
                                <Avatar className="h-6 w-6 rounded shrink-0">
                                  {typeof getOrganizationImage(dataset) === 'string' && 
                                   getOrganizationImage(dataset).length > 1 ? (
                                    <AvatarImage src={getOrganizationImage(dataset) as string} />
                                  ) : (
                                    <AvatarFallback className="rounded bg-green-100 text-green-600 text-xs">
                                      {getOrganizationImage(dataset)}
                                    </AvatarFallback>
                                  )}
                                </Avatar>
                              <div className="min-w-0 flex-1">
                                <span 
                                  className="text-sm block text-gray-800 leading-tight truncate"
                                  title={getOrganizationName(dataset)}
                                >
                                  {getOrganizationName(dataset)}
                                </span>
                              </div>
                              </div>
                            </TableCell>
                          <TableCell className="py-4">
                            <div>
                              <h3 
                                className="font-medium text-gray-900 truncate" 
                                title={dataset.title}
                              >
                                  {dataset.title}
                                </h3>
                              </div>
                            </TableCell>
                            <TableCell className="py-4 text-center">
                              <Badge 
                                variant="outline" 
                                className={`font-medium text-xs ${
                                  dataset.relevance?.relevance_score >= 0.7 
                                    ? 'bg-green-50 text-green-700 border-green-200' 
                                    : dataset.relevance?.relevance_score >= 0.5
                                      ? 'bg-blue-50 text-blue-700 border-blue-200'
                                      : 'bg-gray-50 text-gray-700 border-gray-200'
                                }`}
                              >
                                {dataset.relevance?.relevance_score 
                                  ? (dataset.relevance.relevance_score * 100).toFixed(0) + '%' 
                                  : dataset.similarity
                                    ? (dataset.similarity * 100).toFixed(0) + '%'
                                    : 'N/A'}
                              </Badge>
                            </TableCell>
                            <TableCell className="py-4 text-center">
                              <Drawer>
                                <DrawerTrigger asChild>
                                  <Badge 
                                    variant="outline" 
                                    className="font-medium text-gray-700 border border-gray-200 bg-transparent hover:bg-gray-100 cursor-pointer inline-flex items-center gap-1.5 transition-colors px-3 py-1"
                                  >
                                    <Download className="h-3 w-3" />
                                    {(dataset.resources || []).length}
                                  </Badge>
                                </DrawerTrigger>
                                <DrawerContent className="bg-white text-gray-900">
                                  <DrawerHeader className="border-b border-gray-100">
                                    <DrawerTitle className="text-xl font-semibold text-gray-900">Resources</DrawerTitle>
                                    <DrawerDescription className="text-gray-600">
                                      Available resources for "{dataset.title}"
                                    </DrawerDescription>
                                  </DrawerHeader>
                                  <div className="p-4">
                                    {dataset.resources && dataset.resources.length > 0 ? (
                                      <Table>
                                        <TableHeader>
                                          <TableRow className="border-b border-gray-200 hover:!bg-gray-50">
                                            <TableHead className="w-[100px] text-gray-700">Type</TableHead>
                                            <TableHead className="text-gray-700">Name</TableHead>
                                            <TableHead className="text-right text-gray-700">Access</TableHead>
                                          </TableRow>
                                        </TableHeader>
                                        <TableBody>
                                          {dataset.resources.map((resource: any, resourceIndex: number) => (
                                            <TableRow 
                                              key={resource.id || resourceIndex}
                                              className="border-b border-gray-100 hover:!bg-gray-50 hover:!text-gray-900"
                                            >
                                              <TableCell className="font-medium text-gray-900">
                                                {getFileType(resource)}
                                              </TableCell>
                                              <TableCell className="text-gray-800">
                                                {resource.name || 'Unnamed resource'}
                                              </TableCell>
                                              <TableCell className="text-right">
                                                <Button 
                                                  size="sm" 
                                                  variant="ghost"
                                                  className="h-8 w-8 p-0 text-gray-700 hover:!bg-gray-100 hover:!text-gray-900"
                                                  asChild
                                                >
                                                  <a href={resource.url} target="_blank" rel="noopener noreferrer">
                                                    <ExternalLink className="h-4 w-4" />
                                                  </a>
                                                </Button>
                                              </TableCell>
                                            </TableRow>
                                          ))}
                                        </TableBody>
                                      </Table>
                                    ) : (
                                      <p className="text-sm text-gray-500 italic">No resources available</p>
                                    )}
                                  </div>
                                  <DrawerFooter className="border-t border-gray-100 bg-white">
                                    <div className="flex justify-end w-full">
                                      <Button 
                                        variant="default" 
                                        className="gap-1 bg-green-500 text-white hover:!bg-green-600"
                                        onClick={() => {
                                          // Logic to download all resources
                                          if (dataset.resources && dataset.resources.length > 0) {
                                            window.open(dataset.resources[0].url, '_blank');
                                          }
                                        }}
                                      >
                                        <Download className="h-4 w-4" />
                                        Download All
                                      </Button>
                                    </div>
                                  </DrawerFooter>
                                </DrawerContent>
                              </Drawer>
                            </TableCell>
                          </TableRow>
                          
                          {/* Expandable row for resources */}
                          <AnimatePresence>
                            {expandedDataset === dataset.id && (
                              <motion.tr
                                initial={{ opacity: 0, height: 0 }}
                                animate={{ opacity: 1, height: 'auto' }}
                                exit={{ opacity: 0, height: 0 }}
                                transition={{ duration: 0.2 }}
                                className="bg-gray-50"
                              >
                              <td colSpan={5} className="p-0 border-b border-gray-200">
                                  <motion.div
                                    initial={{ opacity: 0 }}
                                    animate={{ opacity: 1 }}
                                    exit={{ opacity: 0 }}
                                    transition={{ duration: 0.2, delay: 0.1 }}
                                    className="px-4 py-4"
                                  >
                                    {/* Full description */}
                                    <div className="mb-4">
                                    <h4 className="text-sm font-medium mb-1 text-gray-800">Description</h4>
                                      <p className="text-sm text-gray-600">
                                        {dataset.description || 'No description available'}
                                      </p>
                                    </div>
                                    
                                    {/* Relevance reasoning */}
                                    {dataset.relevance && dataset.relevance.reasoning && (
                                    <div className="mb-4">
                                        <h4 className="text-sm font-medium mb-1 text-gray-800">Relevance Assessment</h4>
                                        <p className="text-sm text-gray-600">
                                          {dataset.relevance.reasoning}
                                        </p>
                                      </div>
                                    )}
                                    
                                    {/* Tags section */}
                                    {dataset.tags && dataset.tags.length > 0 && (
                                      <div>
                                        <h4 className="text-sm font-medium mb-2 text-gray-800">Tags</h4>
                                        <div className="flex flex-wrap gap-1.5">
                                          {dataset.tags.map((tag: any, tagIndex: number) => {
                                            const tagText = typeof tag === 'string' 
                                              ? tag 
                                              : (tag.display_name || tag.name || '');
                                              
                                            return (
                                              <Badge 
                                                key={tagIndex} 
                                                variant="secondary"
                                                className="text-xs text-gray-700 bg-gray-100 hover:bg-gray-200"
                                              >
                                                {tagText}
                                              </Badge>
                                            );
                                          })}
                                        </div>
                                      </div>
                                    )}
                                  </motion.div>
                                </td>
                              </motion.tr>
                            )}
                          </AnimatePresence>
                        </React.Fragment>
                    ))}
                    
                    {/* Show skeleton rows only when searching */}
                    {searchStatus === SearchStatus.SEARCHING && (
                      // Skeleton rows when searching
                      Array(6).fill(0).map((_, index) => (
                        <TableRow 
                          key={`skeleton-${index}`}
                          className="border-b border-gray-200 hover:!bg-transparent"
                        >
                          <TableCell className="py-4 px-4">
                            <div className="flex items-center justify-center w-5 h-5">
                              <Skeleton className="h-4 w-4 bg-gray-200 rounded-sm" />
                            </div>
                          </TableCell>
                          <TableCell className="py-4">
                            <div className="flex items-center gap-2">
                              <Skeleton className="h-6 w-6 rounded-full bg-gray-200 shrink-0" />
                              <div className="flex-1">
                                <Skeleton className="h-4 w-full bg-gray-200" />
                              </div>
                            </div>
                          </TableCell>
                          <TableCell className="py-4">
                            <Skeleton className="h-5 w-[90%] bg-gray-200" />
                          </TableCell>
                          <TableCell className="py-4 text-center">
                            <div className="flex justify-center">
                              {/* Match the badge shape/size in the Relevance column */}
                              <Skeleton className="h-6 w-16 bg-gray-200 rounded-full" />
                            </div>
                          </TableCell>
                          <TableCell className="py-4 text-center">
                            <div className="flex justify-center">
                              {/* Match the badge shape/size in the Resources column */}
                              <Skeleton className="h-7 w-20 bg-gray-200 rounded-full" />
                            </div>
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
