import { Star } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { PREFERRED_DATASET_ID_SET } from "@/lib/constants";

interface DatasetBadgeProps {
  datasetId: string;
}

export function PreferredDatasetBadge({ datasetId }: DatasetBadgeProps) {
  if (!PREFERRED_DATASET_ID_SET.has(datasetId)) {
    return null;
  }
  
  return (
    <Badge className="bg-amber-400 text-amber-900 hover:bg-amber-500 ml-2 flex items-center gap-1">
      <Star className="h-3 w-3" />
      <span>Preferred</span>
    </Badge>
  );
} 