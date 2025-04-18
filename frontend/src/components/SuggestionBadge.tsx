// src/components/SuggestionBadge.tsx
import React from 'react';
import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/TooltipNoArrow";

interface SuggestionBadgeProps {
  suggestion: string;
  label: string;
  onClick: (suggestion: string) => void;
}

export const SuggestionBadge: React.FC<SuggestionBadgeProps> = ({ 
  suggestion, 
  label, 
  onClick 
}) => {
  const handleClick = () => {
    onClick(suggestion);
  };
  
  return (
    <TooltipProvider>
      <Tooltip delayDuration={300}>
        <TooltipTrigger asChild>
          <Badge 
            variant="outline" 
            className="cursor-pointer py-1 border-0 bg-green-100 text-green-800 hover:bg-green-200 transition-colors rounded-sm"
            onClick={handleClick}
          >
            {label}
          </Badge>
        </TooltipTrigger>
        <TooltipContent className="bg-white p-2 shadow-md border border-gray-200 z-50">
          <p className="text-sm text-gray-900">{suggestion}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
};