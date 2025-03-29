"use client";

import { Button } from "@/components/ui/button";
import { useEffect, useRef, useState } from "react";
import { ArrowRight, Send } from "lucide-react";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardFooter, CardHeader } from "@/components/ui/card";
import { processQuery } from '@/lib/api';
import Link from "next/link";

export default function BetaPage() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [mousePosition, setMousePosition] = useState({ x: 0, y: 0 });
  const trailPositions = useRef<Array<{x: number, y: number}>>([]);
  const requestRef = useRef<number>();
  const previousTimeRef = useRef<number>();
  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [chatMode, setChatMode] = useState(false);
  
  // Chat state variables
  const [messages, setMessages] = useState<Array<{
    role: 'user' | 'assistant';
    content: string;
    loading?: boolean;
    response?: any; // To store the full API response
  }>>([]);
  
  const contentRef = useRef(null);
  const [thumbHeight, setThumbHeight] = useState(0);
  const [thumbTop, setThumbTop] = useState(0);
  const [isDragging, setIsDragging] = useState(false);
  const [startY, setStartY] = useState(0);
  const [startScrollTop, setStartScrollTop] = useState(0);
  
  // Process URL parameters on page load
  useEffect(() => {
    const processUrlParams = async () => {
      try {
        // Get URL parameters
        const urlParams = new URLSearchParams(window.location.search);
        const datasetsParam = urlParams.get('datasets');
        const queryParam = urlParams.get('query');
        
        // If both parameters are present, trigger analysis
        if (datasetsParam && queryParam) {
          // Parse dataset IDs (removing brackets and quotes if needed)
          let datasetIds;
          try {
            datasetIds = JSON.parse(datasetsParam);
          } catch (e) {
            // If parsing fails, try to split by comma
            datasetIds = datasetsParam.split(',');
          }
          
          if (datasetIds && datasetIds.length > 0) {
            // Add user message to the chat
            setMessages(prev => [...prev, { role: 'user', content: queryParam }]);
            
            // Add a loading message from the assistant
            setMessages(prev => [...prev, { role: 'assistant', content: '', loading: true }]);
            
            // Switch to chat mode
            setChatMode(true);
            setIsLoading(true);
            
            // Make API call to analyze datasets
            const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5000/crystal-2f87e/us-central1';
            const response = await fetch(`${apiUrl}/stream_analyze`, {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
              },
              body: JSON.stringify({ 
                dataset_ids: datasetIds,
                query: queryParam 
              }),
            });
            
            if (!response.ok) {
              throw new Error(`API error: ${response.status}`);
            }
            
            // Handle the streaming response
            const reader = response.body?.getReader();
            let partialData = '';
            
            if (reader) {
              while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                
                const text = new TextDecoder().decode(value);
                partialData += text;
                
                // Split by SSE format "data:" lines
                const lines = partialData.split(/data:/);
                
                for (const line of lines) {
                  if (!line.trim()) continue;
                  
                  try {
                    const data = JSON.parse(line.trim());
                    
                    // Handle different message types
                    if (data.type === 'update' || data.type === 'complete') {
                      // Update the assistant message with latest content
                      setMessages(prev => {
                        const newMessages = [...prev];
                        const loadingIndex = newMessages.findIndex(m => m.loading);
                        if (loadingIndex !== -1) {
                          newMessages[loadingIndex] = {
                            role: 'assistant',
                            content: data.data?.summary || data.message || "Processing...",
                            loading: data.type !== 'complete',
                            response: data.data || data
                          };
                        }
                        return newMessages;
                      });
                      
                      if (data.type === 'complete') {
                        setIsLoading(false);
                      }
                    }
                  } catch (e) {
                    // Skip parsing errors for partial chunks
                  }
                }
              }
            }
          }
        }
      } catch (error) {
        console.error('Error processing URL parameters:', error);
        
        // Update with error message
        setMessages(prev => {
          const newMessages = [...prev];
          const loadingIndex = newMessages.findIndex(m => m.loading);
          if (loadingIndex !== -1) {
            newMessages[loadingIndex] = {
              role: 'assistant',
              content: "Sorry, I encountered an error processing your request. Please try again."
            };
          }
          return newMessages;
        });
        
        setIsLoading(false);
      }
    };
    
    processUrlParams();
  }, []);
  
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
  const displayedExamples = isMobile ? exampleQueries.slice(0, 3) : exampleQueries;
  
  // Function to handle clicking an example query - immediately start chat
  const handleExampleClick = async (query: string) => {
    // Add user message to the chat
    setMessages(prev => [...prev, { role: 'user', content: query }]);
    
    // Add a loading message from the assistant
    setMessages(prev => [...prev, { role: 'assistant', content: '', loading: true }]);
    
    // Switch to chat mode
    setChatMode(true);
    
    setIsLoading(true);
    
    try {
      // Check URL for dataset IDs
      const urlParams = new URLSearchParams(window.location.search);
      const datasetsParam = urlParams.get('datasets');
      let datasetIds;
      
      // Parse dataset IDs if available
      if (datasetsParam) {
        try {
          datasetIds = JSON.parse(datasetsParam);
        } catch (e) {
          datasetIds = datasetsParam.split(',');
        }
      }
      
      // Process the query with dataset IDs if available
      const response = await processQuery(query, datasetIds);
      
      // Update the loading message with the actual response
      setMessages(prev => {
        const newMessages = [...prev];
        const loadingIndex = newMessages.findIndex(m => m.loading);
        if (loadingIndex !== -1) {
          newMessages[loadingIndex] = {
            role: 'assistant',
            content: response.summary || "No summary available",
            response: response
          };
        }
        return newMessages;
      });
      
    } catch (error) {
      console.error("Error processing query:", error);
      
      // Update the loading message with an error
      setMessages(prev => {
        const newMessages = [...prev];
        const loadingIndex = newMessages.findIndex(m => m.loading);
        if (loadingIndex !== -1) {
          newMessages[loadingIndex] = {
            role: 'assistant',
            content: "Sorry, I encountered an error processing your query. Please try again."
          };
        }
        return newMessages;
      });
    } finally {
      setIsLoading(false);
    }
  };
  
  // Initialize trail positions
  useEffect(() => {
    // Initialize with 5 points at the center
    const centerX = window.innerWidth / 2;
    const centerY = window.innerHeight / 2;
    trailPositions.current = Array(5).fill({ x: centerX, y: centerY });
  }, []);
  
  // Animation loop for the trail effect
  const animate = (time: number) => {
    if (previousTimeRef.current !== undefined) {
      // Update trail positions with physics
      const mousePos = { x: mousePosition.x, y: mousePosition.y };
      
      // Update the first point to follow the mouse with some easing
      if (trailPositions.current.length > 0) {
        const firstPoint = trailPositions.current[0];
        const dx = mousePos.x - firstPoint.x;
        const dy = mousePos.y - firstPoint.y;
        
        // Apply easing (0.2 = more lag, 0.8 = less lag)
        trailPositions.current[0] = {
          x: firstPoint.x + dx * 0.3,
          y: firstPoint.y + dy * 0.3
        };
        
        // Update the rest of the trail to follow the point ahead of it
        for (let i = 1; i < trailPositions.current.length; i++) {
          const point = trailPositions.current[i];
          const prevPoint = trailPositions.current[i - 1];
          const dx = prevPoint.x - point.x;
          const dy = prevPoint.y - point.y;
          
          trailPositions.current[i] = {
            x: point.x + dx * 0.3,
            y: point.y + dy * 0.3
          };
        }
      }
      
      // Update CSS variables for all trail points
      if (containerRef.current) {
        // Main spotlight follows the mouse directly
        containerRef.current.style.setProperty('--mouse-x', `${mousePos.x}px`);
        containerRef.current.style.setProperty('--mouse-y', `${mousePos.y}px`);
        
        // Trail points
        trailPositions.current.forEach((pos, i) => {
          containerRef.current?.style.setProperty(`--trail-x-${i}`, `${pos.x}px`);
          containerRef.current?.style.setProperty(`--trail-y-${i}`, `${pos.y}px`);
        });
      }
    }
    
    previousTimeRef.current = time;
    requestRef.current = requestAnimationFrame(animate);
  };
  
  useEffect(() => {
    if (chatMode) {
      // If in chat mode, cancel any existing animation frame
      if (requestRef.current) {
        cancelAnimationFrame(requestRef.current);
        requestRef.current = undefined;
      }
      return;
    }
    
    // Only run animation when not in chat mode
    requestRef.current = requestAnimationFrame(animate);
    return () => {
      if (requestRef.current) {
        cancelAnimationFrame(requestRef.current as number);
      }
    };
  }, [mousePosition, chatMode]);
  
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!containerRef.current || chatMode) return; // Skip if in chat mode
      
      const rect = containerRef.current.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      
      setMousePosition({ x, y });
    };
    
    const container = containerRef.current;
    if (container) {
      container.addEventListener('mousemove', handleMouseMove);
    }
    
    return () => {
      if (container) {
        container.removeEventListener('mousemove', handleMouseMove);
      }
    };
  }, [chatMode]);

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInputValue(e.target.value);
  };

  const handleSubmit = async () => {
    if (!inputValue.trim()) return;
    
    // Add user message to the chat
    const userMessage = inputValue;
    setMessages(prev => [...prev, { role: 'user', content: userMessage }]);
    
    // Add a loading message from the assistant
    setMessages(prev => [...prev, { role: 'assistant', content: '', loading: true }]);
    
    // Switch to chat mode if not already
    if (!chatMode) {
      setChatMode(true);
    }
    
    setIsLoading(true);
    setInputValue("");
    
    try {
      // Check URL for dataset IDs
      const urlParams = new URLSearchParams(window.location.search);
      const datasetsParam = urlParams.get('datasets');
      let datasetIds;
      
      // Parse dataset IDs if available
      if (datasetsParam) {
        try {
          datasetIds = JSON.parse(datasetsParam);
        } catch (e) {
          datasetIds = datasetsParam.split(',');
        }
      }
      
      // Process the query with dataset IDs if available
      const response = await processQuery(userMessage, datasetIds);
      
      // Update the loading message with the actual response
      setMessages(prev => {
        const newMessages = [...prev];
        const loadingIndex = newMessages.findIndex(m => m.loading);
        if (loadingIndex !== -1) {
          newMessages[loadingIndex] = {
            role: 'assistant',
            content: response.summary || "No summary available",
            response: response
          };
        }
        return newMessages;
      });
      
    } catch (error) {
      console.error("Error processing query:", error);
      
      // Update the loading message with an error
      setMessages(prev => {
        const newMessages = [...prev];
        const loadingIndex = newMessages.findIndex(m => m.loading);
        if (loadingIndex !== -1) {
          newMessages[loadingIndex] = {
            role: 'assistant',
            content: "Sorry, I encountered an error processing your query. Please try again."
          };
        }
        return newMessages;
      });
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  useEffect(() => {
    const content = contentRef.current;
    if (!content) return;
    
    const updateThumb = () => {
      const { scrollHeight, clientHeight, scrollTop } = content;
      const scrollRatio = clientHeight / scrollHeight;
      const newThumbHeight = Math.max(scrollRatio * clientHeight, 30); // Minimum thumb height
      const newThumbTop = (scrollTop / scrollHeight) * clientHeight;
      
      setThumbHeight(newThumbHeight);
      setThumbTop(newThumbTop);
    };
    
    content.addEventListener('scroll', updateThumb);
    window.addEventListener('resize', updateThumb);
    updateThumb();
    
    return () => {
      content.removeEventListener('scroll', updateThumb);
      window.addEventListener('resize', updateThumb);
    };
  }, []);

  const handleThumbMouseDown = (e) => {
    setIsDragging(true);
    setStartY(e.clientY);
    setStartScrollTop(contentRef.current.scrollTop);
  };

  useEffect(() => {
    const handleMouseMove = (e) => {
      if (!isDragging) return;
      
      const content = contentRef.current;
      const { scrollHeight, clientHeight } = content;
      const deltaY = e.clientY - startY;
      const deltaRatio = deltaY / clientHeight;
      const newScrollTop = startScrollTop + deltaRatio * scrollHeight;
      
      content.scrollTop = newScrollTop;
    };
    
    const handleMouseUp = () => {
      setIsDragging(false);
    };
    
    if (isDragging) {
      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('mouseup', handleMouseUp);
    }
    
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isDragging, startY, startScrollTop]);

  return (
    <div className="flex items-center justify-center min-h-screen bg-neutral-50 dark:bg-neutral-50 p-4">
      <div
        ref={containerRef}
        className={`w-full h-[calc(100vh-2rem)] rounded-lg bg-cover bg-center flex flex-col ${
          chatMode ? 'justify-between' : 'justify-center'
        } relative overflow-hidden`}
        style={{
          backgroundImage: "url('/images/crystalbackground.png')",
        }}
      >
        {/* Background Image Layer with dark overlay - no spotlight */}
        <div 
          className="absolute inset-0 z-10 bg-cover bg-center after:absolute after:inset-0 after:bg-black/70 after:backdrop-blur-sm" 
          style={{ backgroundImage: "url('/images/crystalbackground.png')" }}
        ></div>
        
        {/* Back to home link - always visible */}
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
        
        {/* Navigation links */}
        <div className="absolute top-6 right-6 z-30 flex gap-4">
          <Link href="/alpha">
            <Button 
              variant="link" 
              className="text-white flex items-center gap-1 hover:text-white/80 transition-colors"
              style={{ fontFamily: 'var(--font-geist-sans)' }}
            >
              Alpha
            </Button>
          </Link>
        </div>
        
        {/* Content - Show differently based on chat mode */}
        {!chatMode ? (
          // Landing page content
          <>
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
                <span className="absolute text-sm font-normal opacity-70 top-1 -right-12">
                  beta
                </span>
              </div>
            </div>
            <div className="relative p-2 mt-2 z-20 text-center w-full">
              <h2 className="relative text-xl sm:text-2xl text-white" style={{ fontFamily: 'var(--font-geist-sans)' }}>
                Querying for Deep<span className="text-green-500 animate-pulse drop-shadow-[0_0_8px_rgba(34,197,94,0.8)]" style={{ textShadow: '0 0 10px rgba(34, 197, 94, 0.8)' }}>er</span> Research into Public Records
              </h2>
            </div>
            
            {/* Example queries - without the heading text */}
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
            
            {/* Chat input for landing page */}
            <div className="z-20 relative w-full max-w-md mx-auto px-4 mt-8">
              <div className="flex w-full items-end gap-2">
                <Textarea
                  value={inputValue}
                  onChange={handleInputChange}
                  onKeyDown={handleKeyDown}
                  placeholder="Ask about public data..."
                  className="min-h-10 resize-none bg-white/20 border-white/30 text-white placeholder:text-white/70 focus:border-green-400/70"
                  disabled={isLoading}
                />
                <Button 
                  size="icon" 
                  onClick={handleSubmit}
                  disabled={isLoading || !inputValue.trim()}
                  className="bg-green-500/80 hover:bg-green-500/90 text-white h-10 w-10"
                >
                  <Send className="h-4 w-4" />
                </Button>
              </div>
            </div>
          </>
        ) : (
          // Chat mode - full screen version without header logo/name
          <>
            {/* Chat messages - now starts from the top */}
            <div 
              ref={contentRef}
              className="flex-1 overflow-y-auto p-4 pt-16 z-20 relative" // Added pt-16 to give space below the back button
            >
              {messages.length === 0 ? (
                <div className="flex items-center justify-center h-full">
                  <div className="text-center text-white/70">
                    <p>Ask me about public data and records.</p>
                    <p className="text-sm mt-2">For example: "What's the air quality trend in NYC over the past 5 years?"</p>
                  </div>
                </div>
              ) : (
                <div className="space-y-4">
                  {messages.map((message, index) => (
                    <div 
                      key={index} 
                      className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
                    >
                      <div 
                        className={`max-w-[80%] rounded-lg p-3 ${
                          message.role === 'user' 
                            ? 'bg-green-500/80 text-white' 
                            : 'bg-white/20 text-white'
                        }`}
                      >
                        {message.loading ? (
                          <div className="flex items-center space-x-2">
                            <div className="w-2 h-2 bg-white/70 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
                            <div className="w-2 h-2 bg-white/70 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
                            <div className="w-2 h-2 bg-white/70 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
                          </div>
                        ) : (
                          <div>{message.content}</div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
              
              {/* Custom scrollbar */}
              <div 
                className="absolute right-1 top-0 w-2 h-full opacity-0 hover:opacity-100 transition-opacity"
                style={{ height: '100%' }}
              >
                <div 
                  className="absolute right-0 bg-white/30 rounded-full w-2"
                  style={{ 
                    height: `${thumbHeight}px`, 
                    top: `${thumbTop}px`,
                    cursor: 'pointer'
                  }}
                  onMouseDown={handleThumbMouseDown}
                ></div>
              </div>
            </div>
            
            {/* Chat input */}
            <div className="p-4 border-t border-white/10 z-20 relative">
              <div className="flex w-full items-end gap-2 max-w-4xl mx-auto">
                <Textarea
                  value={inputValue}
                  onChange={handleInputChange}
                  onKeyDown={handleKeyDown}
                  placeholder="Ask about public data..."
                  className="min-h-10 resize-none bg-white/20 border-white/30 text-white placeholder:text-white/70 focus:border-green-400/70"
                  disabled={isLoading}
                />
                <Button 
                  size="icon" 
                  onClick={handleSubmit}
                  disabled={isLoading || !inputValue.trim()}
                  className="bg-green-500/80 hover:bg-green-500/90 text-white h-10 w-10"
                >
                  <Send className="h-4 w-4" />
                </Button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
