import React from "react";
import { CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Button } from "@/components/ui/button";
import { X } from "lucide-react";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Drawer, DrawerContent } from "@/components/ui/drawer";

interface AnalysisResultsModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  isMobile: boolean;
  query: string;
  summary: string;
  keyFindings: string[];
  sources: {
    citation_id: string;
    title: string;
    organization: string;
  }[];
}

export function AnalysisResultsModal({
  open,
  onOpenChange,
  isMobile,
  query,
  summary,
  keyFindings,
  sources
}: AnalysisResultsModalProps) {
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
        return <strong key={i} className="font-semibold">{boldText}</strong>;
      }
      return part;
    });
  };
  
  // Make the report content itself the main content with white background
  const content = (
    <div className="bg-white rounded-lg text-gray-900 p-6 relative shadow-sm">
      {/* Close button in the top right corner */}
      <Button 
        variant="ghost" 
        size="icon" 
        onClick={() => onOpenChange(false)}
        className="h-8 w-8 rounded-full absolute top-4 right-4 text-gray-500 hover:text-gray-900 hover:bg-gray-100"
      >
        <X className="h-4 w-4" />
      </Button>
      
      <CardTitle className="text-xl mb-6 capitalize font-semibold text-gray-900">&quot;{query}&quot;</CardTitle>
      
      <div className="space-y-6">
        <div>
          <h3 className="text-lg font-medium mb-2 text-gray-900">Summary</h3>
          <p className="text-md leading-6 text-gray-700">
            {formatBoldText(cleanSummary)}
          </p>
        </div>
        
        <Separator className="bg-gray-200" />
        
        <div>
          <h3 className="text-lg font-medium mb-2 text-gray-900">Key Findings</h3>
          <ul className="text-md leading-6 text-gray-700 space-y-2">
            {keyFindings.map((finding, index) => (
              <li key={index}>{formatBoldText(finding)}</li>
            ))}
          </ul>
        </div>
        
        <Separator className="bg-gray-200" />
        
        <div>
          <h3 className="text-lg font-medium mb-2 text-gray-900">Sources</h3>
          <ScrollArea className="h-auto max-h-[200px]">
            <ol className="text-md leading-6 text-gray-700 list-decimal pl-5 space-y-2">
              {sources.map((source) => (
                <li key={source.citation_id}>
                  <span className="font-medium">[{source.citation_id}]</span>{" "}
                  {source.title} ({source.organization})
                </li>
              ))}
            </ol>
          </ScrollArea>
        </div>
      </div>
    </div>
  );

  return isMobile ? (
    <Drawer open={open} onOpenChange={onOpenChange}>
      <DrawerContent className="bg-white p-0">
        <ScrollArea className="max-h-[85vh]">
          {content}
        </ScrollArea>
      </DrawerContent>
    </Drawer>
  ) : (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[800px] max-h-[85vh] bg-white p-0 overflow-hidden border border-gray-200">
        <ScrollArea className="max-h-[85vh]">
          {content}
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}