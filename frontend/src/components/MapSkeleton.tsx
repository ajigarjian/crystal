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
        "flex h-full w-full items-center justify-center rounded-xl border bg-muted/30 relative overflow-hidden",
        className
      )}
      {...props}
    >
      {/* Enhanced shimmer overlay */}
      <div className="absolute inset-0 -translate-x-full animate-shimmer bg-gradient-to-r from-transparent via-white/20 to-transparent"></div>
      
      {/* Loading content */}
      <div className="space-y-4 text-center z-10">
        {/* Map placeholder with shimmer */}
        <div className="relative">
          <div className="h-32 w-48 rounded-lg bg-muted animate-pulse"></div>
          <div className="absolute inset-0 -translate-x-full animate-shimmer-fast bg-gradient-to-r from-transparent via-white/30 to-transparent rounded-lg"></div>
        </div>
        
        {/* Loading text */}
        <div className="space-y-2">
          <div className="text-sm font-medium text-muted-foreground">Loading Map</div>
          
          {/* Animated loading dots */}
          <div className="flex items-center justify-center space-x-1">
            <div className="w-1 h-1 bg-muted-foreground rounded-full animate-bounce-dot"></div>
            <div className="w-1 h-1 bg-muted-foreground rounded-full animate-bounce-dot-delay-1"></div>
            <div className="w-1 h-1 bg-muted-foreground rounded-full animate-bounce-dot-delay-2"></div>
          </div>
        </div>
      </div>
    </div>
  );
} 