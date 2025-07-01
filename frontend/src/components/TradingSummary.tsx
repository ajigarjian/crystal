"use client";

import React, { useState, useEffect } from 'react';
import { Skeleton } from "@/components/ui/skeleton";

interface TradingSummaryProps {
  className?: string;
  isLoading?: boolean;
}

export function TradingSummary({ className = "", isLoading = false }: TradingSummaryProps) {
  const [currentTime, setCurrentTime] = useState<{
    dateTitle: string;
    timeUTC: string;
  } | null>(null);

  // Use useEffect to set the time on the client side only
  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      setCurrentTime({
        dateTitle: now.toLocaleDateString('en-US', {
          month: 'long',
          day: 'numeric',
          year: 'numeric'
        }),
        timeUTC: now.toLocaleTimeString('en-US', {
          timeZone: 'UTC',
          hour12: false,
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit'
        })
      });
    };

    // Set initial time
    updateTime();

    // Update time every second
    const interval = setInterval(updateTime, 1000);

    return () => clearInterval(interval);
  }, []);

  if (isLoading) {
    return (
      <div className={`space-y-6 ${className}`}>
        {/* Header Skeleton */}
        <div className="space-y-2">
          <Skeleton className="h-7 w-48" />
          <Skeleton className="h-4 w-36" />
        </div>

        {/* Trading Summary Content Skeleton */}
        <div className="space-y-4">
          <div className="space-y-2">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-3/4" />
          </div>
          
          <div className="space-y-2">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-2/3" />
          </div>
          
          <div className="space-y-2">
            <Skeleton className="h-4 w-5/6" />
          </div>
        </div>

        {/* Key Metrics Skeleton */}
        <div className="pt-4 border-t border-border/40">
          <Skeleton className="h-4 w-32 mb-3" />
          <div className="space-y-2">
            <div className="flex justify-between">
              <Skeleton className="h-3 w-24" />
              <Skeleton className="h-3 w-20" />
            </div>
            <div className="flex justify-between">
              <Skeleton className="h-3 w-20" />
              <Skeleton className="h-3 w-16" />
            </div>
            <div className="flex justify-between">
              <Skeleton className="h-3 w-28" />
              <Skeleton className="h-3 w-12" />
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={`space-y-6 ${className}`}>
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="space-y-2">
          <h2 className="text-xl font-semibold tracking-tight">
            {currentTime?.dateTitle || 'Loading...'} Summary
          </h2>
        </div>
        <p className="text-sm text-muted-foreground mt-1">
          Last updated {currentTime?.timeUTC || '--:--:--'} UTC
        </p>
      </div>

      {/* Trading Summary Content */}
      <div className="space-y-4 text-xs leading-relaxed">
        <p>
          Tightness at Malin persists this morning following unplanned curtailments on the 
          Ruby Pipeline (~150 MMCF/d offline) and lower hydro across the Northwest. Gas basis 
          surged $0.35 overnight, pushing implied heat rates above 10 at peak. Calpine's 
          Goose Lake units are rumored to be derating, amplifying the westbound pull from SoCal.
        </p>

        <p>
          Traders are leaning long into Mid-C morning with expectations of $8+ prints if the SCE 
          demand forecast verifies. Malin congestion risk is real—watch for firming flow caps at 
          the CA border if SoCal pulls harder.
        </p>

        <p className="font-medium text-foreground">
          No clear resolution on Ruby until at least EOD Tuesday; expect volatility to remain elevated.
        </p>
      </div>

      {/* Key Metrics or Additional Info Section */}
      <div className="pt-4 border-t border-border/40">
        <h3 className="text-sm font-medium text-muted-foreground mb-3">
          Key Market Drivers
        </h3>
        <div className="space-y-2 text-xs text-muted-foreground">
          <div className="flex justify-between">
            <span>Ruby Pipeline Status:</span>
            <span className="text-destructive font-medium">~150 MMCF/d Offline</span>
          </div>
          <div className="flex justify-between">
            <span>Heat Rate Target:</span>
            <span className="text-foreground font-medium">10+ at Peak</span>
          </div>
          <div className="flex justify-between">
            <span>Expected Mid-C Print:</span>
            <span className="text-foreground font-medium">$8+</span>
          </div>
        </div>
      </div>
    </div>
  );
} 