"use client"

import * as React from "react"
import { Line, LineChart, CartesianGrid, XAxis, YAxis, Label } from "recharts"
import { format, subDays, eachDayOfInterval } from "date-fns"
import { IconTable, IconChartLine } from "@tabler/icons-react"

import { useIsMobile } from "@/hooks/use-mobile"
import { cn } from "@/lib/utils"
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
  ToggleGroup,
  ToggleGroupItem,
} from "@/components/ui/toggle-group"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { getSnotelStationObservations, SnotelObservationDataPoint } from "@/lib/firebase"

interface ProcessedWTEQData {
  date: string;
  wteq_inches: number;
  timestamp: number;
  displayDate: string;
  tooltip_label: string;
  quality: string;
}

type TimeRangeOption = "30d" | "14d" | "7d";

const chartConfig = {
  wteq_inches: {
    label: "Snow Water Equiv. (in)",
    color: "hsl(142, 71%, 45%)", // Green color matching the request
  },
} satisfies ChartConfig

interface ChartSnotelWTEQProps {
  selectedStationId: number;
  stationName: string;
}

const timeRangeOptions = [
  { value: "30d" as const, label: "Last 30 days", days: 30 },
  { value: "14d" as const, label: "Last 14 days", days: 14 },
  { value: "7d" as const, label: "Last 7 days", days: 7 },
];

export function ChartSnotelWTEQ({ selectedStationId, stationName }: ChartSnotelWTEQProps) {
  const isMobile = useIsMobile()
  
  // View state - true for chart, false for table
  const [isChartView, setIsChartView] = React.useState(true)
  
  // Time range state
  const [timeRange, setTimeRange] = React.useState<TimeRangeOption>("14d")
  
  const [processedWTEQData, setProcessedWTEQData] = React.useState<ProcessedWTEQData[]>([])
  const [isLoading, setIsLoading] = React.useState(false)
  
  // Current data for subtitle
  const [currentData, setCurrentData] = React.useState<{
    value: number;
    date: string;
  } | null>(null)

  // Reset all state when selectedStationId changes
  React.useEffect(() => {
    setProcessedWTEQData([])
    setCurrentData(null)
    setIsLoading(false)
  }, [selectedStationId])

  // Set default time range based on mobile/desktop
  React.useEffect(() => {
    if (isMobile) {
      setTimeRange("7d") // Default to 7d for mobile
    } else {
      setTimeRange("14d") // Default to 14d for desktop
    }
  }, [isMobile])

  // Fetch and process WTEQ data
  React.useEffect(() => {
    const fetchData = async () => {
      if (!selectedStationId) {
        setProcessedWTEQData([])
        setCurrentData(null)
        setIsLoading(false)
        return
      }

      setIsLoading(true)
      
      // Reset state at the start of each fetch
      setProcessedWTEQData([])
      setCurrentData(null)
      
      try {
        const selectedRange = timeRangeOptions.find(opt => opt.value === timeRange);
        const days = selectedRange?.days || 14;
        
        console.log(`Fetching SNOTEL data for station ${selectedStationId}, ${days} days`);
        
        const rawData: SnotelObservationDataPoint[] = await getSnotelStationObservations(selectedStationId, days);
        
        console.log("Raw SNOTEL data received:", rawData);
        
        // Handle empty data case explicitly
        if (!rawData || rawData.length === 0) {
          console.log(`No SNOTEL data found for station ${selectedStationId}`);
          setProcessedWTEQData([]);
          setCurrentData(null);
          setIsLoading(false);
          return;
        }
        
        // Process the data for chart display
        const processedData = rawData.map(point => {
          const date = new Date(point.ts_utc);
          const timestamp = date.getTime();
          
          return {
            date: point.ts_utc,
            wteq_inches: Math.round(point.value_num * 10) / 10, // Round to 1 decimal place
            timestamp: timestamp,
            displayDate: format(date, 'MMM dd, yyyy'),
            tooltip_label: format(date, 'MMM dd, yyyy'),
            quality: point.quality
          };
        }).sort((a, b) => a.timestamp - b.timestamp); // Sort by timestamp
        
        console.log("Processed SNOTEL data:", processedData);
        
        setProcessedWTEQData(processedData);
        
        // Set current data (most recent observation)
        if (processedData.length > 0) {
          const latestPoint = processedData[processedData.length - 1];
          setCurrentData({
            value: latestPoint.wteq_inches,
            date: latestPoint.displayDate
          });
        } else {
          setCurrentData(null);
        }
      } catch (error) {
        console.error("Failed to fetch or process SNOTEL data:", error);
        
        // Check if it's a network/fetch error
        if (error instanceof TypeError && error.message.includes('Failed to fetch')) {
          console.error("Network error - this might be a CORS issue or the function isn't running");
        }
        
        setProcessedWTEQData([]);
        setCurrentData(null);
      } finally {
        setIsLoading(false);
      }
    };
    
    fetchData();
  }, [selectedStationId, timeRange]);

  // Calculate X-axis ticks based on time range
  const getXAxisConfig = () => {
    if (processedWTEQData.length === 0) return { ticks: [], formatter: (value: number) => '' };
    
    const selectedRange = timeRangeOptions.find(opt => opt.value === timeRange);
    const days = selectedRange?.days || 14;
    
    if (days <= 7) {
      // For 7 days or less, show every day
      const dayTicks = processedWTEQData.map((_, index) => index);
      return {
        ticks: dayTicks.filter((_, index) => index % 1 === 0), // Show every day
        formatter: (value: number) => {
          const dataPoint = processedWTEQData[value];
          return dataPoint ? format(new Date(dataPoint.date), 'MMM dd') : '';
        }
      };
    } else if (days <= 14) {
      // For 14 days, show every other day
      const dayTicks = processedWTEQData.map((_, index) => index);
      return {
        ticks: dayTicks.filter((_, index) => index % 2 === 0), // Show every other day
        formatter: (value: number) => {
          const dataPoint = processedWTEQData[value];
          return dataPoint ? format(new Date(dataPoint.date), 'MMM dd') : '';
        }
      };
    } else {
      // For 30 days, show every 5th day
      const dayTicks = processedWTEQData.map((_, index) => index);
      return {
        ticks: dayTicks.filter((_, index) => index % 5 === 0), // Show every 5th day
        formatter: (value: number) => {
          const dataPoint = processedWTEQData[value];
          return dataPoint ? format(new Date(dataPoint.date), 'MMM dd') : '';
        }
      };
    }
  };

  const xAxisConfig = getXAxisConfig();

  return (
    <Card className="@container/card shadow-none">
      <CardHeader>
        <CardTitle>Snow Water Equivalent (WTEQ)</CardTitle>
        <CardDescription>
          {currentData ? (
            `${currentData.value}" as of ${currentData.date}`
          ) : (
            `Daily snow water equivalent measurements`
          )}
        </CardDescription>
        <CardAction>
          <div className="flex items-center gap-2">
            {/* View Toggle */}
            <div className="flex items-center gap-1 mr-2">
              <button
                onClick={() => setIsChartView(true)}
                className={cn(
                  "p-2 rounded-md transition-colors",
                  isChartView 
                    ? "bg-primary text-primary-foreground" 
                    : "hover:bg-muted text-muted-foreground"
                )}
                title="Chart view"
              >
                <IconChartLine size={16} />
              </button>
              <button
                onClick={() => setIsChartView(false)}
                className={cn(
                  "p-2 rounded-md transition-colors",
                  !isChartView 
                    ? "bg-primary text-primary-foreground" 
                    : "hover:bg-muted text-muted-foreground"
                )}
                title="Table view"
              >
                <IconTable size={16} />
              </button>
            </div>

            {/* Time Range Controls */}
            <ToggleGroup
              type="single"
              value={timeRange}
              onValueChange={(value: TimeRangeOption) => {
                if (value) setTimeRange(value)
              }}
              variant="outline"
              className="hidden *:data-[slot=toggle-group-item]:!px-4 @[767px]/card:flex"
            >
              <ToggleGroupItem value="30d">Last 30 days</ToggleGroupItem>
              <ToggleGroupItem value="14d">Last 14 days</ToggleGroupItem>
              <ToggleGroupItem value="7d">Last 7 days</ToggleGroupItem>
            </ToggleGroup>
            <Select
              value={timeRange}
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
                {timeRangeOptions.map(option => (
                  <SelectItem key={option.value} value={option.value} className="rounded-lg">
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </CardAction>
      </CardHeader>
      <CardContent className="px-2 pt-4 sm:px-6 sm:pt-6">
        {isChartView ? (
          // Chart View
          <ChartContainer
            config={chartConfig}
            className="aspect-auto h-[250px] w-full"
          >
            {isLoading ? (
              <div className="flex h-full w-full items-center justify-center">
                <p>Loading WTEQ data...</p>
              </div>
            ) : processedWTEQData.length === 0 && !isLoading ? (
              <div className="flex h-full w-full items-center justify-center">
                <p>No WTEQ data available for the selected range.</p>
              </div>
            ) : (
              <LineChart data={processedWTEQData} margin={{ left: 40, right: 10, top: 5, bottom: 20 }}>
                <CartesianGrid vertical={false} />
                <XAxis
                  dataKey="timestamp"
                  tickLine={false}
                  axisLine={false}
                  tickMargin={8}
                  tickFormatter={xAxisConfig.formatter}
                  domain={['dataMin', 'dataMax']}
                  type="number"
                  scale="time"
                  ticks={xAxisConfig.ticks.map(index => processedWTEQData[index]?.timestamp).filter(Boolean)}
                />
                <YAxis 
                  tickLine={false}
                  axisLine={false}
                  tickMargin={8}
                  tickFormatter={(value) => {
                    if (typeof value === 'number') {
                      return `${value.toFixed(1)}"`
                    }
                    return String(value)
                  }}
                  domain={[
                    (dataMin: number) => Math.max(0, Math.floor(dataMin * 0.9)),
                    (dataMax: number) => Math.ceil(dataMax * 1.1)
                  ]}
                >
                  <Label 
                    value="Snow Water Equiv. (inches)" 
                    angle={-90} 
                    position="insideLeft" 
                    style={{ textAnchor: 'middle' }} 
                    dy={0}
                    offset={-30}
                  />
                </YAxis>
                <ChartTooltip
                  cursor={true}
                  content={
                    <ChartTooltipContent
                      labelFormatter={(value, payload) => {
                        if (payload && payload.length > 0) {
                          const dataPoint = payload[0].payload
                          return dataPoint.tooltip_label
                        }
                        return "WTEQ"
                      }}
                      formatter={(value, name, props) => {
                        const dataPoint = props.payload
                        return [
                          `${dataPoint.wteq_inches}" inches`
                        ]
                      }}
                      indicator="dot"
                    />
                  }
                />
                <Line
                  dataKey="wteq_inches"
                  type="linear"
                  stroke="hsl(142, 71%, 45%)" // Green color as requested
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 6 }}
                  connectNulls={false}
                />
              </LineChart>
            )}
          </ChartContainer>
        ) : (
          // Table View
          <div className="h-[250px] w-full">
            {isLoading ? (
              <div className="flex h-full w-full items-center justify-center">
                <p>Loading WTEQ data...</p>
              </div>
            ) : processedWTEQData.length === 0 ? (
              <div className="flex h-full w-full items-center justify-center">
                <p>No WTEQ data available for the selected range.</p>
              </div>
            ) : (
              <div className="h-full overflow-hidden rounded-md border">
                <div 
                  className="h-full overflow-auto [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar]:h-1.5 [&::-webkit-scrollbar-track]:bg-transparent [&::-webkit-scrollbar-thumb]:bg-border [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb:hover]:bg-muted-foreground/50"
                  style={{
                    scrollbarWidth: 'thin',
                    scrollbarColor: 'hsl(var(--border)) transparent',
                  }}
                >
                  <Table>
                    <TableHeader className="sticky top-0 bg-background">
                      <TableRow>
                        <TableHead className="p-2 text-left font-medium">Date</TableHead>
                        <TableHead className="p-2 text-center font-medium">WTEQ (inches)</TableHead>
                        <TableHead className="p-2 text-center font-medium">Quality</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {processedWTEQData.map((dataPoint, index) => (
                        <TableRow key={index} className="border-b transition-colors hover:bg-muted/50">
                          <TableCell className="p-2 align-middle whitespace-nowrap font-medium">
                            {dataPoint.displayDate}
                          </TableCell>
                          <TableCell className="p-2 align-middle whitespace-nowrap text-center font-mono">
                            {dataPoint.wteq_inches.toFixed(1)}"
                          </TableCell>
                          <TableCell className="p-2 align-middle whitespace-nowrap text-center text-xs">
                            {dataPoint.quality}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
} 