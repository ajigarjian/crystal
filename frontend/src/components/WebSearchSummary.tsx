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
  sources: Record<string, WebSearchSource>;
  top_sources: WebSearchSource[];
  total_relevant_sources: number;
  source_citations: boolean;
}

interface WebSearchSummaryProps {
  data?: WebSearchSummaryData;
}

export function WebSearchSummary({ data }: WebSearchSummaryProps) {
  if (!data) {
    return null;
  }

  // Function to replace [1], [2] citations with source titles and format KEY POINTS
  const formatSummaryWithSourceTitles = (summary: string) => {
    if (!summary) return "";
    
    let formattedSummary = summary;
    
    // Replace both actual newlines and escaped newlines with HTML line breaks
    formattedSummary = formattedSummary.replace(/(\\n|\n)/g, '<br />');
    
    // Replace [1], [2], etc. with numbered badges
    Object.keys(data.sources || {}).forEach((key) => {
      const source = data.sources[key];
      
      // Use regex to replace [key] with numbered badge
      const regex = new RegExp(`\\[${key}\\]`, 'g');
      formattedSummary = formattedSummary.replace(
        regex, 
        `<a href="${source?.url || '#'}" target="_blank" rel="noopener noreferrer" class="inline-flex items-center">
          <span class="inline-flex items-center justify-center px-2 py-0.5 text-xs font-medium rounded-full bg-blue-100 text-blue-800 hover:bg-blue-200 transition-colors">
            ${key}
          </span>
        </a>`
      );
    });
    
    // Format the KEY POINTS section with proper styling
    if (formattedSummary.includes("KEY POINTS:")) {
      // Replace KEY POINTS: with a formatted header
      formattedSummary = formattedSummary.replace(
        "KEY POINTS:", 
        '<h3 class="font-bold text-lg mt-4 mb-2">Key Points:</h3>'
      );
      
      // Convert plain text bullet points to proper HTML list
      formattedSummary = formattedSummary.replace(
        /- (.*?)(?=\n- |\n\n|$)/g, 
        '<li>$1</li>'
      );
      
      // Wrap list items in a ul tag with proper styling
      formattedSummary = formattedSummary.replace(
        /<li>.*?<\/li>/g,
        match => `<ul class="list-disc pl-5 space-y-1">${match}</ul>`
      );
    }
    
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
            Based on {data.total_relevant_sources || 0} web sources related to your query
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div 
            className="prose prose-sm dark:prose-invert max-w-none"
            dangerouslySetInnerHTML={{ 
              __html: formatSummaryWithSourceTitles(data.summary || '') 
            }}
          />
        </CardContent>
      </Card>
      
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Sources</CardTitle>
          <CardDescription>
            Top {(data.top_sources || []).length} sources used for this summary
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {(data.top_sources || []).map((source, index) => (
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