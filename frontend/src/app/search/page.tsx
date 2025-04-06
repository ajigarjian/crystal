"use client";

import Link from 'next/link';
import { useState, useRef, useEffect } from 'react';
import { Input } from "@/components/ui/input";
import { Search, Loader2 } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { streamSearchDatasets } from "@/lib/firebase";

export default function SearchPage() {
  const [query, setQuery] = useState('');
  const [isSearching, setIsSearching] = useState(false);
  const [searchProgress, setSearchProgress] = useState(0);
  const [statusMessage, setStatusMessage] = useState('');
  const [datasets, setDatasets] = useState<any[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  // Focus the input field when the page loads
  useEffect(() => {
    if (inputRef.current) {
      inputRef.current.focus();
    }
  }, []);

  // Automatically increment progress for perceived performance
  useEffect(() => {
    if (isSearching && searchProgress < 90) {
      const timer = setTimeout(() => {
        // Accelerate at the beginning and slow down near 90%
        const increment = searchProgress < 30 ? 5 : searchProgress < 60 ? 2 : 0.5;
        setSearchProgress(prev => Math.min(prev + increment, 90));
      }, 500);
      return () => clearTimeout(timer);
    }
  }, [isSearching, searchProgress]);

  const handleSearch = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!query.trim() || isSearching) return;

    // Reset state for new search
    setIsSearching(true);
    setSearchProgress(0);
    setStatusMessage('Initiating search...');
    setDatasets([]);

    try {
      // Start the streaming search
      await streamSearchDatasets(
        {
          query: query.trim(),
          search_method: null, // hybrid search
          similarity_threshold: 0.3,
          max_results: 15
        },
        (chunk) => {
          // Process incoming chunks
          if (chunk.type === 'status') {
            setStatusMessage(chunk.message);
            // Bump progress a bit for each status message
            setSearchProgress(prev => Math.min(prev + 3, 90));
          } 
          else if (chunk.type === 'dataset') {
            setDatasets(prev => [...prev, chunk.data]);
            // Small progress boost for each dataset found
            setSearchProgress(prev => Math.min(prev + 1, 90));
          }
          else if (chunk.type === 'dataset_update') {
            // Update dataset with new information
            setDatasets(prev => prev.map(d => 
              d.id === chunk.data.id ? { ...d, ...chunk.data } : d
            ));
          }
          else if (chunk.type === 'complete') {
            // Search complete, set progress to 100%
            setSearchProgress(100);
            
            // Small delay before finishing to show the completion
            setTimeout(() => {
              setIsSearching(false);
            }, 1000);
          }
        }
      );
    } catch (error: any) {
      console.error("Search error:", error);
      setStatusMessage(`Error: ${error.message || 'An unknown error occurred'}`);
      setIsSearching(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && query.trim() && !isSearching) {
      handleSearch();
    }
  };

  return (
    <div className="flex flex-col min-h-screen bg-gray-50">
      {/* Header with logo */}
      <div className="flex h-16 shrink-0 items-center justify-between px-4 border-b">
        <div className="flex items-center">
          <Link href="/">
            <div className="flex items-center cursor-pointer hover:opacity-80 transition-opacity">
              <img 
                src="/images/crystal-icon.png" 
                alt="Crystal Logo" 
                className="h-6 w-6 mr-2 filter brightness-0" 
              />
              <h1 className="text-lg font-bold" style={{ fontFamily: 'Satoshi, sans-serif' }}>Crystal</h1>
            </div>
          </Link>
        </div>
      </div>
      
      {/* Search section */}
      <div className="max-w-3xl mx-auto w-full px-4 pt-12 pb-8">
        <div className="relative w-full transition-all overflow-hidden rounded-full">
          <Input
            ref={inputRef}
            placeholder="Search for datasets..."
            className="pl-12 pr-4 py-7 text-lg w-full rounded-full border-gray-300 transition-all shadow-sm hover:shadow focus:shadow-md relative z-10"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isSearching}
          />
          <div 
            className={`absolute left-4 top-1/2 -translate-y-1/2 transition-colors duration-200 ease-in-out z-20 ${!isSearching && query.trim() ? 'cursor-pointer' : ''}`}
            onClick={!isSearching && query.trim() ? handleSearch : undefined}
          >
            {isSearching ? (
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
          
          {!isSearching && query.trim() && (
            <div className="absolute right-4 top-1/2 -translate-y-1/2 text-sm text-gray-400 opacity-70 z-20">
              Press Enter to search
            </div>
          )}
          
          {/* Progress bar positioned inside the search input */}
          {isSearching && (
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
        
        {/* Status message below search bar */}
        <AnimatePresence>
          {isSearching && (
            <motion.div 
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.3 }}
              className="mt-4"
            >
              <span 
                className={`text-sm text-neutral-600 dark:text-neutral-400 ${isSearching ? 'animate-pulse' : ''} cursor-pointer`}
              >
                {statusMessage}
              </span>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
      
      {/* Removed dataset results section */}
    </div>
  );
}
