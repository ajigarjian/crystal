"use client";

import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { Star } from "lucide-react";
import { PREFERRED_DATASET_ID_SET } from "@/lib/constants";

export function PreferredDatasetBadge({ datasetId }: { datasetId: string }) {
  // Only show the badge if the dataset is in the preferred set
  if (!PREFERRED_DATASET_ID_SET.has(datasetId)) {
    return null;
  }

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <div className="cursor-help absolute -right-6">
            <Star className="h-4 w-4 text-amber-400 fill-amber-400" />
          </div>
        </TooltipTrigger>
        <TooltipContent>
          <p className="text-sm">Preferred for speed and relevance</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}