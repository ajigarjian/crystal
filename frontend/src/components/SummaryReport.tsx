import React from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";

interface SummaryReportProps {
  query: string;
  summary: string;
  keyFindings: string[];
  sources: {
    citation_id: string;
    title: string;
    organization: string;
  }[];
}

export function SummaryReport({
  query,
  summary,
  keyFindings,
  sources,
}: SummaryReportProps) {
  const cleanSummary = summary?.replace(/^\(≈\d+ words\):\s*/g, '').trim() || '';

  // Helper function to format bold text
  const formatBoldText = (text: string) => {
    if (!text) return null;
    
    // Split by ** markers
    const parts = text.split(/(\*\*.*?\*\*)/g);
    
    return parts.map((part, i) => {
      // Check if this part is surrounded by **
      if (part.startsWith('**') && part.endsWith('**')) {
        // Remove the ** and make it bold
        const boldText = part.slice(2, -2);
        return <strong key={i}>{boldText}</strong>;
      }
      return part;
    });
  };

  return (
    <Card className="mt-4 w-full bg-card">
      <CardHeader className="pb-3">
        <CardTitle className="text-xl font-semibold capitalize">&quot;{query}&quot;</CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        <div>
          <h3 className="text-lg font-medium mb-2">Summary</h3>
          <p className="text-sm leading-6 text-muted-foreground">{cleanSummary}</p>
        </div>
        
        <Separator />
        
        <div>
          <h3 className="text-lg font-medium mb-2">Key Findings</h3>
          <ul className="text-sm leading-6 text-muted-foreground space-y-2">
            {keyFindings.map((finding, index) => (
              <li key={index}>{formatBoldText(finding)}</li>
            ))}
          </ul>
        </div>
        
        <Separator />
        
        <div>
          <h3 className="text-lg font-medium mb-2">Sources</h3>
          <ScrollArea className="h-auto max-h-[200px]">
            <ol className="text-sm leading-6 text-muted-foreground list-decimal pl-5 space-y-2">
              {sources.map((source) => (
                <li key={source.citation_id}>
                  <span className="font-medium">[{source.citation_id}]</span>{" "}
                  {source.title} ({source.organization})
                </li>
              ))}
            </ol>
          </ScrollArea>
        </div>
      </CardContent>
    </Card>
  );
} 