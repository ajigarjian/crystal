import React from "react";
import { Card, CardHeader, CardContent, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ExternalLink } from "lucide-react";

// Types for web search summary
export interface WebSearchSource {
  title: string;
  url: string;
  relevance_level: number;
  source_type: string;
}

export interface WebSearchSummaryData {
  query: string;
  has_relevant_results: boolean;
  summary: string;
  sources: Record<string, any>;
  top_sources: WebSearchSource[];
  total_relevant_sources: number;
  source_citations: boolean;
}

interface WebSearchSummaryProps {
  data: WebSearchSummaryData;
}

export function WebSearchSummary({ data }: WebSearchSummaryProps) {
  // Function to replace [1], [2] citations with source titles
  const formatSummaryWithSourceTitles = (summary: string) => {
    if (!summary) return "";
    
    let formattedSummary = summary;
    
    // Replace [1], [2], etc. with actual source titles
    Object.keys(data.sources || {}).forEach((key) => {
      const source = data.sources[key];
      const title = source.title || "Source";
      
      // Use regex to replace [key] with source title
      const regex = new RegExp(`\\[${key}\\]`, 'g');
      formattedSummary = formattedSummary.replace(regex, `<a href="${source.url}" target="_blank" rel="noopener noreferrer" class="font-medium text-blue-600 hover:underline inline-flex items-center">${title} <span class="inline-block ml-0.5"><svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-external-link"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg></span></a>`);
    });
    
    return formattedSummary;
  };
  
  const getRelevanceLevelColor = (level: number) => {
    switch(level) {
      case 5: return "bg-green-100 text-green-800 border-green-200 dark:bg-green-900/30 dark:text-green-300";
      case 4: return "bg-blue-100 text-blue-800 border-blue-200 dark:bg-blue-900/30 dark:text-blue-300";
      case 3: return "bg-yellow-100 text-yellow-800 border-yellow-200 dark:bg-yellow-900/30 dark:text-yellow-300";
      case 2: return "bg-orange-100 text-orange-800 border-orange-200 dark:bg-orange-900/30 dark:text-orange-300";
      case 1: return "bg-red-100 text-red-800 border-red-200 dark:bg-red-900/30 dark:text-red-300";
      default: return "bg-gray-100 text-gray-800 border-gray-200 dark:bg-gray-800/30 dark:text-gray-300";
    }
  };
  
  const getRelevanceLevelText = (level: number) => {
    switch(level) {
      case 5: return "Highly Relevant";
      case 4: return "Very Relevant";
      case 3: return "Relevant";
      case 2: return "Somewhat Relevant";
      case 1: return "Slightly Relevant";
      default: return "Unknown Relevance";
    }
  };
  
  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-xl">Web Research Summary</CardTitle>
          <CardDescription>
            Based on {data.total_relevant_sources} web sources related to your query
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div 
            className="prose prose-sm dark:prose-invert max-w-none"
            dangerouslySetInnerHTML={{ 
              __html: formatSummaryWithSourceTitles(data.summary) 
            }}
          />
        </CardContent>
      </Card>
      
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Sources</CardTitle>
          <CardDescription>
            Top {data.top_sources.length} sources used for this summary
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {data.top_sources.map((source, index) => (
              <div key={index} className="border rounded-md p-3 flex items-start gap-2">
                <div className="flex-1">
                  <div className="flex items-center">
                    <h3 className="text-sm font-medium">
                      <a 
                        href={source.url} 
                        target="_blank" 
                        rel="noopener noreferrer"
                        className="hover:underline flex items-center"
                      >
                        {source.title}
                        <ExternalLink className="h-3 w-3 ml-1 inline-flex" />
                      </a>
                    </h3>
                  </div>
                  <p className="text-xs text-muted-foreground mt-1 truncate">
                    {source.url}
                  </p>
                </div>
                <Badge 
                  variant="outline" 
                  className={getRelevanceLevelColor(source.relevance_level)}
                >
                  {getRelevanceLevelText(source.relevance_level)}
                </Badge>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
} 