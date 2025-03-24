import React from "react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";

interface SummaryReportSkeletonProps {
  query?: string;
}

export function SummaryReportSkeleton({ query }: SummaryReportSkeletonProps) {
  return (
    <Card className="mt-4 w-full bg-card animate-pulse">
      <CardHeader className="pb-3">
        <CardTitle className="text-xl font-semibold capitalize">
          {query ? `"${query}"` : <Skeleton className="h-7 w-3/4" />}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        <div>
          <h3 className="text-lg font-medium mb-2">Summary</h3>
          <div className="space-y-2">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-5/6" />
            <Skeleton className="h-4 w-4/5" />
          </div>
        </div>
        
        <Separator />
        
        <div>
          <h3 className="text-lg font-medium mb-2">Key Findings</h3>
          <ul className="space-y-3">
            <li><Skeleton className="h-4 w-full" /></li>
            <li><Skeleton className="h-4 w-full" /></li>
            <li><Skeleton className="h-4 w-11/12" /></li>
            <li><Skeleton className="h-4 w-4/5" /></li>
          </ul>
        </div>
        
        <Separator />
        
        <div>
          <h3 className="text-lg font-medium mb-2">Sources</h3>
          <ol className="space-y-3 pl-5">
            <li><Skeleton className="h-4 w-full" /></li>
            <li><Skeleton className="h-4 w-11/12" /></li>
            <li><Skeleton className="h-4 w-10/12" /></li>
          </ol>
        </div>
      </CardContent>
    </Card>
  );
}