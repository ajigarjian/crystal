"use client"

import * as React from "react"
import { Line, Bar, ComposedChart, CartesianGrid, XAxis, YAxis, Label, Legend } from "recharts"
// import { toZonedTime, format as formatDate } from "date-fns-tz" // Temporarily removed for UTC display

import { useIsMobile } from "@/hooks/use-mobile"
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  ChartConfig,
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  ToggleGroup,
  ToggleGroupItem,
} from "@/components/ui/toggle-group"
import { InflowDataPoint, getInflowTimeseries, TimeRangeOption } from "@/lib/firebase" 

// Define the new time range options type
// type TimeRangeOption = "mtd" | "14d" | "7d"; // Already in firebase.ts, no need to redefine if imported

interface ProcessedChartData {
  date: string;
  inflow: number;
  type: 'observed' | 'forecast' | 'forecast_error';
  timestamp: number;
  observed: number | null;
  forecast: number | null;
  // Replace dummy volume with actual forecast error
  forecast_error: number | null;
}

// Temporarily removed PACIFIC_TIMEZONE constant
// const PACIFIC_TIMEZONE = "America/Los_Angeles"

const chartConfig = {
  inflow: {
    label: "Inflow (cfs) - UTC",
    color: "hsl(var(--chart-1))", 
  },
  observed: {
    label: "Observed Inflow", 
    color: "hsl(120, 50%, 30%)", // Darker green
  },
  forecast: {
    label: "Forecast Inflow",
    color: "hsl(340, 50%, 40%)", // Darker red
  },
  forecast_error: {
    label: "Forecast Error (cfs)",
    color: "hsl(0, 70%, 50%)", // Red for errors
  },
} satisfies ChartConfig

// Helper to format date string (basic version for UTC)
// Updated to handle new TimeRangeOption types
const formatUtcDate = (isoString: string, range: TimeRangeOption): string => {
  const dateObj = new Date(isoString);
  if (String(dateObj) === "Invalid Date") {
    return "Invalid Date (UTC)"; 
  }
  
  // For different ranges, show different levels of detail
  if (range === "7d") {
    // For 7 days, show day and abbreviated month
    return dateObj.toLocaleDateString('en-US', { 
      day: 'numeric', 
      month: 'short',
      timeZone: 'UTC' 
    });
  } else {
    // For longer ranges, just show the day
    return dateObj.getUTCDate().toString();
  }
};

const formatUtcDateForDisplay = (isoString: string): string => {
  const dateObj = new Date(isoString);
  // Format as YYYY-MM-DD for data key and internal use
  return `${dateObj.getUTCFullYear()}-${(dateObj.getUTCMonth() + 1).toString().padStart(2, '0')}-${dateObj.getUTCDate().toString().padStart(2, '0')}`;
};

interface ChartAreaInteractiveProps {
  selectedDamId: number;
}

// Add this helper function before the component
const generateEveryOtherDayTicks = (dataMin: number, dataMax: number): number[] => {
  const ticks: number[] = [];
  const startDate = new Date(dataMin);
  const endDate = new Date(dataMax);
  
  // Start from the beginning of the first day
  const currentDate = new Date(startDate.getUTCFullYear(), startDate.getUTCMonth(), startDate.getUTCDate());
  
  while (currentDate <= endDate) {
    ticks.push(currentDate.getTime());
    currentDate.setUTCDate(currentDate.getUTCDate() + 2); // Move to every other day
  }
  
  return ticks;
};

// Remove the generateDummyVolumeData function and replace with:
const processForecastError = (value: number, dataType: string): number | null => {
  return dataType === 'forecast_error' ? value : null;
};

// Updated CustomErrorBar with bars positioned closer to the bottom
const CustomErrorBar = (props: any) => {
  const { payload, x, y, width, height, setHoveredErrorBar } = props;
  
  if (!payload || payload.forecast_error === null || payload.forecast_error === undefined) {
    return null;
  }
  
  const errorValue = payload.forecast_error;
  const isPositive = errorValue > 0;
  const fill = isPositive ? "hsl(0, 70%, 50%)" : "hsl(220, 70%, 50%)";
  
  // Calculate bar dimensions
  const barWidth = Math.max(width, 8); // Slightly wider for easier hovering
  const barX = x - (barWidth - width) / 2;
  
  const maxErrorHeight = 30;
  const errorMagnitude = Math.abs(errorValue);
  const maxError = 10000;
  const barHeight = Math.min((errorMagnitude / maxError) * maxErrorHeight, maxErrorHeight);
  
  // Position closer to the actual bottom of the chart area
  const chartBottom = 220;// Increased from 200 to move bars closer to bottom
  const barY = chartBottom - barHeight;
  
  return (
    <rect
      x={barX}
      y={barY}
      width={barWidth}
      height={barHeight}
      fill={fill}
      fillOpacity={0.7}
      stroke={fill}
      strokeWidth={0.5}
      rx={1}
      // Add hover handlers
      onMouseEnter={(e) => {
        const rect = e.currentTarget.getBoundingClientRect();
        setHoveredErrorBar({
          x: rect.left + rect.width / 2,
          y: rect.top,
          value: errorValue,
          date: payload.date
        });
      }}
      onMouseLeave={() => {
        setHoveredErrorBar(null);
      }}
      style={{ cursor: 'pointer' }}
    />
  );
};

// Custom tooltip component for error bars
const ErrorBarTooltip = ({ data }: { data: { x: number; y: number; value: number; date: string } }) => {
  const errorType = data.value > 0 ? 'Under-forecasted' : 'Over-forecasted';
  const dateObj = new Date(data.date);
  // Remove time from error bar tooltips - just show date
  const formattedDate = dateObj.toLocaleDateString('en-US', { 
    year: 'numeric', month: 'short', day: 'numeric',
    timeZone: 'UTC' 
  });

  return (
    <div
      style={{
        position: 'fixed',
        left: data.x,
        top: data.y - 10,
        transform: 'translate(-50%, -100%)',
        backgroundColor: 'rgba(0, 0, 0, 0.8)',
        color: 'white',
        padding: '8px 12px',
        borderRadius: '4px',
        fontSize: '12px',
        pointerEvents: 'none',
        zIndex: 1000,
        whiteSpace: 'nowrap'
      }}
    >
      <div>{formattedDate}</div>
      <div>{Math.abs(data.value).toLocaleString()} cfs ({errorType})</div>
    </div>
  );
};

export function ChartAreaInteractive({ selectedDamId }: ChartAreaInteractiveProps) {
  const isMobile = useIsMobile()
  const [timeRange, setTimeRange] = React.useState<TimeRangeOption>("14d") 
  const [processedChartData, setProcessedChartData] = React.useState<ProcessedChartData[]>([])
  const [isLoading, setIsLoading] = React.useState(true)
  
  // Move the hoveredErrorBar state INSIDE the component
  const [hoveredErrorBar, setHoveredErrorBar] = React.useState<{
    x: number;
    y: number;
    value: number;
    date: string;
  } | null>(null);

  React.useEffect(() => {
    if (isMobile) {
      setTimeRange("7d") // Default to 7d for mobile
    } else {
      setTimeRange("14d") // Default to 14d for desktop
    }
  }, [isMobile])

  React.useEffect(() => {
    const fetchData = async () => {
      setIsLoading(true)
      try {
        const rawData: InflowDataPoint[] = await getInflowTimeseries(timeRange, selectedDamId)
        
        // Add comprehensive logging
        console.log('=== RAW DATA FROM BACKEND ===')
        console.log('Total data points received:', rawData.length)
        console.log('Raw data sample:', rawData.slice(0, 5))
        
        // Log data types breakdown
        const dataTypeBreakdown = rawData.reduce((acc, point) => {
          acc[point.data_type] = (acc[point.data_type] || 0) + 1
          return acc
        }, {} as Record<string, number>)
        console.log('Data type breakdown:', dataTypeBreakdown)
        
        // Log forecast_error data specifically
        const forecastErrorData = rawData.filter(point => point.data_type === 'forecast_error')
        console.log('Forecast error data points:', forecastErrorData.length)
        if (forecastErrorData.length > 0) {
          console.log('Sample forecast error data:', forecastErrorData.slice(0, 3))
        }
        
        const transformed = rawData.map(point => {
          const timestamp = new Date(point.ts_utc).getTime()
          const inflowValue = Math.trunc(point.value_num);
          
          const processedPoint = {
            date: point.ts_utc,
            timestamp: timestamp,
            observed: point.data_type === 'observed' ? inflowValue : null,
            forecast: point.data_type === 'forecast' ? inflowValue : null,
            inflow: point.data_type !== 'forecast_error' ? inflowValue : Math.abs(inflowValue), // Show absolute value for tooltip
            type: point.data_type,
            // Use actual forecast error - this is the key fix
            forecast_error: point.data_type === 'forecast_error' ? inflowValue : null
          }
          
          // Log observed data processing
          if (point.data_type === 'observed') {
            console.log('Processing observed point:', {
              original: point,
              processed: processedPoint
            })
          }
          
          // Log forecast_error processing
          if (point.data_type === 'forecast_error') {
            console.log('Processing forecast_error point:', {
              original: point,
              processed: processedPoint
            })
          }
          
          return processedPoint
        })
        
        // Log final processed data
        console.log('=== PROCESSED DATA ===')
        console.log('Total processed points:', transformed.length)
        
        // Add debugging for observed data
        const observedData = transformed.filter(point => point.observed !== null)
        console.log('Observed data points:', observedData.length)
        if (observedData.length > 0) {
          console.log('Sample observed data:', observedData.slice(0, 3))
          console.log('Observed data values:', observedData.map(d => ({ timestamp: d.timestamp, observed: d.observed })))
        }
        
        const processedForecastErrors = transformed.filter(point => point.forecast_error !== null)
        console.log('Processed forecast error points:', processedForecastErrors.length)
        if (processedForecastErrors.length > 0) {
          console.log('Sample processed forecast errors:', processedForecastErrors.slice(0, 3))
        }
        
        // Add debugging for Y-axis domain
        const allInflowValues = transformed
          .filter(point => point.observed !== null || point.forecast !== null)
          .map(point => point.observed || point.forecast)
          .filter(val => val !== null);
        
        console.log('All inflow values for Y-axis:', {
          min: Math.min(...allInflowValues),
          max: Math.max(...allInflowValues),
          observedRange: observedData.map(d => d.observed),
          forecastRange: transformed.filter(p => p.forecast !== null).map(d => d.forecast)
        });
        
        setProcessedChartData(transformed)
      } catch (error) {
        console.error("Failed to fetch or process inflow data:", error)
        setProcessedChartData([]) 
      } finally {
        setIsLoading(false)
      }
    }
    fetchData()
  }, [timeRange, selectedDamId])

  return (
    <Card className="@container/card shadow-none">
      <CardHeader>
        <CardTitle>Inflows</CardTitle> {/* Title updated to cfs */}
        <CardDescription>
          <span className="hidden @[540px]/card:block">
            {processedChartData.length > 0 ? (
              (() => {
                // Find the latest observed data point
                const latestObserved = processedChartData
                  .filter(d => d.type === 'observed')
                  .slice(-1)[0]; // Get the last observed point
                
                if (latestObserved) {
                  return `${latestObserved.inflow.toLocaleString()} cfs ${new Date(latestObserved.date).toLocaleDateString('en-US', { month: '2-digit', day: '2-digit', year: 'numeric' })} ${new Date(latestObserved.date).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'UTC' })} UTC`;
                } else {
                  return "No observed data available for the selected period.";
                }
              })()
            ) : (
              "Daily inflow (cubic feet per second) for the selected period (times in UTC)."
            )}
          </span>
          <span className="@[540px]/card:hidden">
            {/* More dynamic description for mobile */}
            {timeRange === "mtd" ? "Month to Date (UTC)" : timeRange === "14d" ? "Last 14 days (UTC)" : "Last 7 days (UTC)"}
          </span>
        </CardDescription>
        <CardAction>
          <ToggleGroup
            type="single"
            value={timeRange}
            // Updated onValueChange type
            onValueChange={(value: TimeRangeOption) => {
              if (value) setTimeRange(value)
            }}
            variant="outline"
            className="hidden *:data-[slot=toggle-group-item]:!px-4 @[767px]/card:flex"
          >
            {/* Updated ToggleGroupItems */}
            <ToggleGroupItem value="mtd">Month to Date</ToggleGroupItem>
            <ToggleGroupItem value="14d">Last 14 days</ToggleGroupItem>
            <ToggleGroupItem value="7d">Last 7 days</ToggleGroupItem>
          </ToggleGroup>
          <Select
            value={timeRange}
            // Updated onValueChange type
            onValueChange={(value: TimeRangeOption) => {
               if (value) setTimeRange(value)
            }}
          >
            <SelectTrigger
              className="flex w-40 **:data-[slot=select-value]:block **:data-[slot=select-value]:truncate @[767px]/card:hidden"
              size="sm"
              aria-label="Select a time range"
            >
              <SelectValue placeholder="Select time range" />
            </SelectTrigger>
            <SelectContent className="rounded-xl">
              {/* Updated SelectItems */}
              <SelectItem value="mtd" className="rounded-lg">
                Month to Date
              </SelectItem>
              <SelectItem value="14d" className="rounded-lg">
                Last 14 days
              </SelectItem>
              <SelectItem value="7d" className="rounded-lg">
                Last 7 days
              </SelectItem>
            </SelectContent>
          </Select>
        </CardAction>
      </CardHeader>
      <CardContent className="px-2 pt-4 sm:px-6 sm:pt-6">
        <ChartContainer
          config={chartConfig}
          className="aspect-auto h-[250px] w-full"
        >
          {isLoading ? (
            <div className="flex h-full w-full items-center justify-center">
              <p>Loading chart data...</p>
            </div>
          ) : processedChartData.length === 0 && !isLoading ? (
             <div className="flex h-full w-full items-center justify-center">
              <p>No inflow data available for the selected period.</p>
            </div>
          ) : (
            <ComposedChart data={processedChartData} margin={{ left: 30, right: 10, top: 5, bottom: 0 }}>
              <CartesianGrid vertical={false} />
              <XAxis
                dataKey="timestamp"
                type="number"
                scale="time"
                domain={['dataMin', 'dataMax']}
                tickLine={false}
                axisLine={false}
                tickMargin={8}
                ticks={processedChartData.length > 0 ? generateEveryOtherDayTicks(
                  Math.min(...processedChartData.map(d => d.timestamp)),
                  Math.max(...processedChartData.map(d => d.timestamp))
                ) : []}
                tickFormatter={(timestamp) => {
                  const date = new Date(timestamp);
                  return date.getUTCDate().toString();
                }}
              />
              {/* Left Y-axis for inflow lines */}
              <YAxis 
                yAxisId="left"
                tickLine={false}
                axisLine={false}
                tickMargin={8}
                tickFormatter={(value) => {
                  if (typeof value === 'number') {
                    return value.toLocaleString(); 
                  }
                  return String(value);
                }}
                domain={[
                  (dataMin: number) => (Math.floor((dataMin * 0.95) / 5000) * 5000),
                  (dataMax: number) => (Math.ceil((dataMax * 1.05) / 5000) * 5000)
                ]}
              >
                <Label 
                  value="Inflow (cfs)" 
                  angle={-90} 
                  position="insideLeft" 
                  style={{ textAnchor: 'middle' }} 
                  dy={0}
                  offset={-20}
                />
              </YAxis>
              {/* Right Y-axis for forecast error bars */}
              <YAxis 
                yAxisId="right"
                orientation="right"
                hide={true}
                domain={[
                  (dataMin: number) => Math.min(dataMin * 1.1, 0), // Allow negative values
                  (dataMax: number) => Math.max(dataMax * 1.1, 0)  // Allow positive values
                ]}
              />
              <ChartTooltip
                cursor={true}
                animationDuration={0}
                content={(props) => {
                  const { active, payload, label } = props;
                  
                  // If we're hovering over an error bar, don't show the line tooltip
                  if (hoveredErrorBar) {
                    return null;
                  }
                  
                  // Only show tooltip if we have an active payload with actual data
                  if (!active || !payload || payload.length === 0) {
                    return null;
                  }
                  
                  // Filter out null/undefined values and forecast_error data for the main tooltip
                  const validPayload = payload.filter(entry => {
                    const dataType = entry.payload?.type;
                    return dataType !== 'forecast_error' && 
                           entry.value !== null && 
                           entry.value !== undefined &&
                           entry.dataKey !== 'forecast_error';
                  });
                  
                  // If no valid data to show, don't render tooltip
                  if (validPayload.length === 0) {
                    return null;
                  }
                  
                  return (
                    <ChartTooltipContent
                      active={active}
                      payload={validPayload}
                      label={label}
                      labelFormatter={(value, payload) => {
                        if (payload && payload.length > 0 && payload[0].payload.date) {
                          const dateStringFromPayload = payload[0].payload.date;
                          const dateObj = new Date(dateStringFromPayload);
                          const dataType = payload[0].payload.type;
                          
                          if (String(dateObj) === "Invalid Date") {
                            return "Invalid Date UTC";
                          }
                          const formattedDate = dateObj.toLocaleDateString('en-US', { 
                            year: 'numeric', month: 'short', day: 'numeric', 
                            hour: '2-digit', minute: '2-digit', timeZone: 'UTC' 
                          }) + " UTC";
                          // Capitalize the data type in the title
                          const capitalizedType = dataType.charAt(0).toUpperCase() + dataType.slice(1);
                          return `${formattedDate} (${capitalizedType})`;
                        }
                        return "Inflow (UTC)";
                      }}
                      formatter={(value, name, props) => {
                        // Remove the type label from the body - just show the value
                        return [
                          `${props.payload.inflow.toLocaleString()} cfs`
                        ];
                      }}
                      indicator="dot"
                    />
                  );
                }}
              />
              {/* Forecast error bars */}
              <Bar
                yAxisId="right"
                dataKey="forecast_error"
                shape={(props: any) => <CustomErrorBar {...props} setHoveredErrorBar={setHoveredErrorBar} />}
                stroke="none"
                fill="transparent"
              />
              {/* Observed inflow line */}
              <Line
                yAxisId="left"
                dataKey="observed"
                type="linear" 
                stroke="hsl(120, 70%, 40%)"
                strokeWidth={2}
                activeDot={{ r: 8 }}
                connectNulls={true}
              />
              {/* Forecast inflow line */}
              <Line
                yAxisId="left"
                dataKey="forecast"
                type="linear" 
                stroke="hsl(340, 50%, 40%)"
                strokeWidth={2}
                strokeDasharray="5 5"
                dot={false}
                activeDot={{ r: 6, fill: "hsl(340, 50%, 40%)" }}
                connectNulls={false}
              />
            </ComposedChart>
          )}
        </ChartContainer>
        {hoveredErrorBar && <ErrorBarTooltip data={hoveredErrorBar} />}
      </CardContent>
    </Card>
  )
}
