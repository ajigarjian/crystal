"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

interface MapSkeletonProps extends React.HTMLAttributes<HTMLDivElement> {
  className?: string;
}

export function MapSkeleton({ className, ...props }: MapSkeletonProps) {
  return (
    <div
      className={cn(
        "flex h-full w-full items-center justify-center rounded-xl border border-dashed bg-muted/50 p-4",
        className
      )}
      {...props}
    >
      <div className="animate-pulse space-y-2 text-center">
        <div className="h-6 w-32 rounded bg-muted"></div>
        <div className="h-4 w-40 rounded bg-muted"></div>
      </div>
    </div>
  );
} 