import { Skeleton } from "@/components/ui/skeleton";

export function SectionCardSkeleton() {
  return (
    <div className="p-3 rounded-lg border bg-card text-card-foreground shadow-sm">
      <div className="text-sm font-medium text-muted-foreground mb-1">
        <Skeleton className="h-5 w-2/3" />
      </div>
      <div className="text-lg font-bold">
        <Skeleton className="h-7 w-1/2" />
      </div>
    </div>
  );
} 