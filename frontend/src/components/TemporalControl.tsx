"use client"

import * as React from "react"
import { addHours, subHours, format, startOfDay, endOfDay, addDays, parseISO, isWithinInterval } from "date-fns"
import { CalendarIcon, PlayIcon, PauseIcon, SkipBackIcon, SkipForwardIcon, InfoIcon } from "lucide-react"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Slider } from "@/components/ui/slider"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { Calendar } from "@/components/ui/calendar"
import { cn } from "@/lib/utils"

interface TemporalControlProps {
  selectedDateTime: Date;
  onDateTimeChange: (datetime: Date) => void;
  isLoading?: boolean;
  hasCachedData?: boolean;
  cacheTimeRange?: {
    start_date: string;
    end_date: string;
    weeks: number;
  };
  className?: string;
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
}

export function TemporalControl({ 
  selectedDateTime, 
  onDateTimeChange, 
  isLoading = false,
  hasCachedData = false,
  cacheTimeRange,
  className,
  isCollapsed = false,
  onToggleCollapse
}: TemporalControlProps) {
  const [isPlaying, setIsPlaying] = React.useState(false)
  const [calendarOpen, setCalendarOpen] = React.useState(false)
  const [isShowingNow, setIsShowingNow] = React.useState(true) // Start as true since we initialize with "now"
  
  const playIntervalRef = React.useRef<NodeJS.Timeout | null>(null)
  
  // Calculate time boundaries (24 hours from start of selected day)
  const dayStart = startOfDay(selectedDateTime)
  const dayEnd = endOfDay(selectedDateTime)
  
  // Calculate current hour position (0-23)
  const currentHour = selectedDateTime.getHours()
  
  // Calculate available date range from cache
  const availableDateRange = React.useMemo(() => {
    if (!cacheTimeRange) return null
    
    try {
      const startDate = parseISO(cacheTimeRange.start_date)
      const endDate = parseISO(cacheTimeRange.end_date)
      
      return {
        start: startOfDay(startDate),
        end: startOfDay(endDate)
      }
    } catch (error) {
      console.error('Error parsing cache time range:', error)
      return null
    }
  }, [cacheTimeRange])
  
  // Function to check if a date is available in cache
  const isDateAvailable = React.useCallback((date: Date) => {
    if (!availableDateRange) return true // If no cache info, allow any date
    
    const dateToCheck = startOfDay(date)
    return isWithinInterval(dateToCheck, availableDateRange)
  }, [availableDateRange])
  
  // Function to check if current selectedDateTime is "now" (within 1 hour tolerance)
  const checkIsNow = React.useCallback(() => {
    const now = new Date()
    now.setMinutes(0, 0, 0) // Round to nearest hour
    
    const selectedRounded = new Date(selectedDateTime)
    selectedRounded.setMinutes(0, 0, 0) // Round to nearest hour
    
    // Check if they're the same hour
    return selectedRounded.getTime() === now.getTime()
  }, [selectedDateTime])
  
  // Update isShowingNow when selectedDateTime changes
  React.useEffect(() => {
    setIsShowingNow(checkIsNow())
  }, [checkIsNow])
  
  // Function to check if we can go to the next day
  const canGoToNextDay = React.useCallback(() => {
    const nextDay = startOfDay(addDays(selectedDateTime, 1))
    return isDateAvailable(nextDay)
  }, [selectedDateTime, isDateAvailable])
  
  // Function to check if we can go to the previous day
  const canGoToPreviousDay = React.useCallback(() => {
    const currentDayStart = startOfDay(selectedDateTime)
    
    // If we're already at 00:00, check if previous day is available
    if (selectedDateTime.getTime() === currentDayStart.getTime()) {
      const previousDay = addDays(currentDayStart, -1)
      return isDateAvailable(previousDay)
    }
    
    // If we're not at 00:00, we can always go to 00:00 of current day
    return true
  }, [selectedDateTime, isDateAvailable])
  
  // Auto-play functionality
  React.useEffect(() => {
    if (isPlaying) {
      playIntervalRef.current = setInterval(() => {
        setIsPlaying(prev => {
          if (prev) {
            // Check if we're at the end of the day
            const nextHour = addHours(selectedDateTime, 1)
            if (nextHour.getDate() === selectedDateTime.getDate()) {
              onDateTimeChange(nextHour)
              return true
            } else {
              // Stop at end of day
              return false
            }
          }
          return false
        })
      }, 1000) // Fixed 1 second interval
    } else {
      if (playIntervalRef.current) {
        clearInterval(playIntervalRef.current)
        playIntervalRef.current = null
      }
    }
    
    return () => {
      if (playIntervalRef.current) {
        clearInterval(playIntervalRef.current)
      }
    }
  }, [isPlaying, selectedDateTime, onDateTimeChange])
  
  const handleSliderChange = (value: number[]) => {
    const newHour = value[0]
    const newDateTime = new Date(dayStart)
    newDateTime.setHours(newHour)
    onDateTimeChange(newDateTime)
  }
  
  const handlePlayPause = () => {
    setIsPlaying(!isPlaying)
  }
  
  const handleStepBackward = () => {
    const currentDayStart = startOfDay(selectedDateTime)
    
    // Check if we're already at 00:00 of the current day
    if (selectedDateTime.getTime() === currentDayStart.getTime()) {
      // If we're at 00:00, go to previous day (00:00 of previous day)
      const previousDay = addDays(currentDayStart, -1)
      
      // Only navigate if the previous day is available in cache
      if (isDateAvailable(previousDay)) {
        onDateTimeChange(previousDay)
      }
    } else {
      // If we're not at 00:00, go to start of current day (00:00)
      onDateTimeChange(currentDayStart)
    }
  }
  
  const handleStepForward = () => {
    // Go to start of next day (00:00 of next day)
    const nextDay = startOfDay(addDays(selectedDateTime, 1))
    
    // Only navigate if the next day is available in cache
    if (isDateAvailable(nextDay)) {
      onDateTimeChange(nextDay)
    }
  }
  
  const handleDateChange = (date: Date | undefined) => {
    if (date && isDateAvailable(date)) {
      // Keep the same hour but change the date
      const newDateTime = new Date(date)
      newDateTime.setHours(selectedDateTime.getHours())
      onDateTimeChange(newDateTime)
      setCalendarOpen(false)
    }
  }
  
  const handleCurrentTime = () => {
    const now = new Date()
    // Round to nearest hour
    now.setMinutes(0, 0, 0)
    onDateTimeChange(now)
    // State will be updated automatically via useEffect that watches selectedDateTime
  }
  
  // If collapsed, show only the expand button as a half circle
  if (isCollapsed) {
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              onClick={onToggleCollapse}
              className="w-8 h-8 bg-white border border-gray-300 hover:bg-gray-50 flex items-center justify-center shadow-sm transition-colors"
              style={{
                borderRadius: '0 50% 50% 0',
                borderLeft: 'none',
                margin: '0'
              }}
              aria-label="Expand temporal control"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-gray-600">
                <path d="M9 18l6-6-6-6" />
              </svg>
            </button>
          </TooltipTrigger>
          <TooltipContent side="right">
            <p>Expand</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    )
  }

  return (
    <Card className={cn("w-full relative", className)}>
      {/* Collapse Button */}
      {onToggleCollapse && (
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                onClick={onToggleCollapse}
                className="absolute -right-4 top-1/2 -translate-y-1/2 w-8 h-8 rounded-full bg-white border border-gray-300 hover:bg-gray-50 flex items-center justify-center shadow-sm transition-colors z-10"
                aria-label="Collapse temporal control"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-gray-600">
                  <path d="M15 18l-6-6 6-6" />
                </svg>
              </button>
            </TooltipTrigger>
            <TooltipContent side="right">
              <p>Collapse</p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      )}
      
      <CardHeader className="pb-3">
        {/* Main Title with Tooltip */}
        <div className="flex items-center justify-center gap-2 mb-3">
          <h3 className="text-sm font-semibold">Line Capacity Factors</h3>
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <InfoIcon className="h-4 w-4 text-muted-foreground cursor-help" />
              </TooltipTrigger>
              <TooltipContent side="bottom" className="max-w-sm">
                <p>
                  View transmission line capacity factors in the past, present or future. Use the controls to explore different dates and times.
                </p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
        
        {/* Time Control Row */}
        <CardTitle className="text-sm font-medium flex items-center justify-center">
          <div className="flex items-center gap-2">
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant={isShowingNow ? "default" : "outline"}
                    size="sm"
                    onClick={handleCurrentTime}
                    disabled={isLoading}
                    className={isShowingNow ? "bg-blue-600 hover:bg-blue-700 text-white" : ""}
                  >
                    {isShowingNow ? (
                      <span className="flex items-center gap-1">
                        <div className="w-2 h-2 bg-green-400 rounded-full animate-pulse"></div>
                        Now
                      </span>
                    ) : (
                      "Now"
                    )}
                  </Button>
                </TooltipTrigger>
                <TooltipContent>
                  {isShowingNow ? "Currently viewing live data" : "Jump to current time"}
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
            <Popover open={calendarOpen} onOpenChange={setCalendarOpen}>
              <PopoverTrigger asChild>
                <Button variant="outline" size="sm" className="font-normal">
                  <CalendarIcon className="mr-2 h-4 w-4" />
                  {format(selectedDateTime, 'MMM dd, yyyy')}
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-auto p-0">
                <div className="p-3">
                  {availableDateRange && (
                    <div className="text-xs text-muted-foreground mb-2 text-center">
                      Available: {format(availableDateRange.start, 'MMM dd')} - {format(availableDateRange.end, 'MMM dd, yyyy')}
                    </div>
                  )}
                  <Calendar
                    mode="single"
                    selected={selectedDateTime}
                    onSelect={handleDateChange}
                    disabled={(date) => !isDateAvailable(date)}
                    initialFocus
                    fromDate={availableDateRange?.start}
                    toDate={availableDateRange?.end}
                  />
                </div>
              </PopoverContent>
            </Popover>
          </div>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        
        {/* Time Slider */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>00:00</span>
            <span className="font-mono font-semibold text-sm">{format(selectedDateTime, 'HH:mm')} UTC</span>
            <span>23:00</span>
          </div>
          <Slider
            value={[currentHour]}
            onValueChange={handleSliderChange}
            max={23}
            min={0}
            step={1}
            className="w-full"
            disabled={isLoading}
          />
        </div>
        
        {/* Playback Controls */}
        <div className="flex items-center justify-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleStepBackward}
            disabled={isLoading || !canGoToPreviousDay()}
          >
            <SkipBackIcon className="h-4 w-4" />
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={handlePlayPause}
            disabled={isLoading || currentHour >= 23}
          >
            {isPlaying ? <PauseIcon className="h-4 w-4" /> : <PlayIcon className="h-4 w-4" />}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={handleStepForward}
            disabled={isLoading || !canGoToNextDay()}
          >
            <SkipForwardIcon className="h-4 w-4" />
          </Button>
        </div>
      </CardContent>
    </Card>
  )
} 