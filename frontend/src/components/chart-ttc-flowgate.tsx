"use client"

import * as React from "react"
import { Line, LineChart, CartesianGrid, XAxis, YAxis, Label } from "recharts"
import { addDays, format, startOfDay, differenceInDays, eachDayOfInterval } from "date-fns"
import { CalendarIcon } from "lucide-react"
import { IconTable, IconChartLine } from "@tabler/icons-react"
import { DateRange } from "react-day-picker"

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
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import { Button } from "@/components/ui/button"
import { Calendar } from "@/components/ui/calendar"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { getTTCFlowgateData, TTCDataPoint } from "@/lib/firebase"

interface ProcessedTTCData {
  label: string;
  ttc_mw: number;
  position: number; // Sequential position for X-axis
  quality: 'F' | 'R';
  datetime_utc: string;
  tooltip_label: string;
  date: string;
  hour_ending: number;
}

// Interface for table data structure
interface TableRowData {
  date: string;
  displayDate: string;
  hours: { [key: number]: { value: number; isForecast: boolean } | null };
}

const chartConfig = {
  ttc_mw: {
    label: "TTC Limit (MW)",
    color: "hsl(142, 71%, 45%)",
  },
} satisfies ChartConfig

interface ChartTTCFlowgateProps {
  selectedFlowgate: string;
}

// Helper function to determine if a data point is in the future (PPT timezone)
const isDataPointInFuture = (date: string, hourEnding: number): boolean => {
  if (!date) return false
  
  try {
    // Create the datetime for the hour ending in PPT
    const dataPointDateTime = `${date}T${hourEnding.toString().padStart(2, '0')}:00:00`
    
    // Get current time in Pacific timezone
    const nowInPacific = new Date().toLocaleString("en-US", {
      timeZone: "America/Los_Angeles",
      year: 'numeric',
      month: '2-digit', 
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false
    })
    
    // Convert data point to Pacific time for comparison
    const tempDate = new Date(dataPointDateTime)
    const dataPointInPacific = tempDate.toLocaleString("en-US", {
      timeZone: "America/Los_Angeles",
      year: 'numeric',
      month: '2-digit',
      day: '2-digit', 
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false
    })
    
    // Compare as strings in MM/DD/YYYY, HH:MM:SS format
    return dataPointInPacific > nowInPacific
  } catch (error) {
    console.error('Error parsing date for future check:', error)
    return false
  }
}

// Helper function to get quality label based on datetime
const getQualityLabel = (date: string, hourEnding: number, originalQuality: string): string => {
  if (isDataPointInFuture(date, hourEnding)) {
    return 'Forecast'
  } else {
    // For past data points, don't show any quality label
    return ''
  }
}

export function ChartTTCFlowgate({ selectedFlowgate }: ChartTTCFlowgateProps) {
  const isMobile = useIsMobile()
  
  // View state - true for chart, false for table
  const [isChartView, setIsChartView] = React.useState(true)
  
  // Date range state
  const [dateRange, setDateRange] = React.useState<DateRange | undefined>({
    from: new Date(),
    to: new Date()
  })
  
  const [processedTTCData, setProcessedTTCData] = React.useState<ProcessedTTCData[]>([])
  const [isLoading, setIsLoading] = React.useState(true)
  
  // Current hour data for subtitle
  const [currentHourData, setCurrentHourData] = React.useState<{
    value: number;
    datetime: string;
  } | null>(null)

  // Process data for table view
  const getTableData = (): TableRowData[] => {
    if (!dateRange?.from || !dateRange?.to) return []
    
    const days = eachDayOfInterval({ start: dateRange.from, end: dateRange.to })
    const tableData: TableRowData[] = []
    
    days.forEach(day => {
      const dateStr = format(day, 'yyyy-MM-dd')
      const displayDate = format(day, 'MMM dd, yyyy')
      
      const rowData: TableRowData = {
        date: dateStr,
        displayDate,
        hours: {}
      }
      
      // Initialize all hours to null
      for (let hour = 1; hour <= 24; hour++) {
        rowData.hours[hour] = null
      }
      
      // Fill in data from processedTTCData
      processedTTCData.forEach(dataPoint => {
        if (dataPoint.date === dateStr) {
          rowData.hours[dataPoint.hour_ending] = {
            value: dataPoint.ttc_mw,
            isForecast: isDataPointInFuture(dateStr, dataPoint.hour_ending)
          }
        }
      })
      
      tableData.push(rowData)
    })
    
    return tableData
  }

  // Fetch current hour data for subtitle
  React.useEffect(() => {
    const fetchCurrentHourData = async () => {
      try {
        const today = format(new Date(), 'yyyy-MM-dd')
        const rawData: TTCDataPoint[] = await getTTCFlowgateData(selectedFlowgate, today)
        
        if (rawData.length > 0) {
          const now = new Date()
          const currentHour = now.getUTCHours() + 1
          
          let currentPoint = rawData.find(point => point.hour_ending === currentHour)
          if (!currentPoint && rawData.length > 0) {
            currentPoint = rawData.reduce((latest, current) => 
              current.hour_ending > latest.hour_ending ? current : latest
            )
          }
          
          if (currentPoint) {
            const dateStr = format(now, 'MM/dd/yyyy HH:mm')
            setCurrentHourData({
              value: Math.trunc(currentPoint.value_mw),
              datetime: `${dateStr} UTC`
            })
          }
        }
      } catch (error) {
        console.error("Failed to fetch current hour TTC data:", error)
        setCurrentHourData(null)
      }
    }
    
    if (selectedFlowgate) {
      fetchCurrentHourData()
    }
  }, [selectedFlowgate])

  // Fetch and process ALL hourly data for the date range
  React.useEffect(() => {
    const fetchData = async () => {
      if (!dateRange?.from || !dateRange?.to) return
      
      setIsLoading(true)
      try {
        // Get all days in the range
        const days = eachDayOfInterval({ start: dateRange.from, end: dateRange.to })
        const allHourlyData: ProcessedTTCData[] = []
        let position = 1
        
        // Fetch data for each day and create complete 24-hour sets
        for (const day of days) {
          const dateStr = format(day, 'yyyy-MM-dd')
          const dayData = await getTTCFlowgateData(selectedFlowgate, dateStr)
          
          // Create all 24 hours for this day (HE01 through HE24)
          for (let hour = 1; hour <= 24; hour++) {
            const hourData = dayData.find(point => point.hour_ending === hour)
            
            if (hourData && hourData.value_mw > 0) {
              // Determine actual quality based on current time
              const actualQuality = isDataPointInFuture(dateStr, hour) ? 'F' : 'R'
              
              allHourlyData.push({
                label: `HE${hour.toString().padStart(2, '0')}`,
                ttc_mw: Math.trunc(hourData.value_mw),
                position: position,
                quality: actualQuality,
                datetime_utc: hourData.datetime_utc,
                tooltip_label: `${format(day, 'MMM dd')} HE${hour.toString().padStart(2, '0')}`,
                date: dateStr,
                hour_ending: hour
              })
            }
            
            position++
          }
        }
        
        setProcessedTTCData(allHourlyData)
      } catch (error) {
        console.error("Failed to fetch or process TTC data:", error)
        setProcessedTTCData([])
      } finally {
        setIsLoading(false)
      }
    }
    
    if (selectedFlowgate) {
      fetchData()
    } else {
      setProcessedTTCData([])
      setIsLoading(false)
    }
  }, [selectedFlowgate, dateRange])

  // Calculate X-axis ticks and labels based on date range
  const getXAxisConfig = () => {
    if (!dateRange?.from || !dateRange?.to) return { ticks: [], formatter: (value: number) => '' }
    
    const days = eachDayOfInterval({ start: dateRange.from, end: dateRange.to })
    const totalDays = days.length
    
    if (totalDays === 1) {
      // Single day: show hour labels (HE01, HE06, HE12, HE18, HE24)
      const hourTicks = [1, 6, 12, 18, 24].filter(tick => tick <= processedTTCData.length)
      return {
        ticks: hourTicks,
        formatter: (value: number) => {
          const dataPoint = processedTTCData.find(d => d.position === value)
          return dataPoint?.label || `HE${((value - 1) % 24 + 1).toString().padStart(2, '0')}`
        }
      }
    } else {
      // Multiple days: show day labels at the start of each day
      const dayTicks: number[] = []
      const dayLabels: { [key: number]: string } = {}
      
      days.forEach((day, dayIndex) => {
        // Position of HE01 for this day (each day has 24 hours)
        const dayStartPosition = (dayIndex * 24) + 1
        
        // Only add tick if we have data at this position
        if (dayStartPosition <= processedTTCData.length) {
          dayTicks.push(dayStartPosition)
          dayLabels[dayStartPosition] = format(day, 'MMM dd')
        }
      })
      
      return {
        ticks: dayTicks,
        formatter: (value: number) => dayLabels[value] || ''
      }
    }
  }

  const xAxisConfig = getXAxisConfig()
  const tableData = getTableData()

  if (!selectedFlowgate) {
    return (
      <Card className="@container/card shadow-none">
        <CardHeader>
          <CardTitle>Hourly TTC Path Limits</CardTitle>
          <CardDescription>
            Select a flowgate from the map or search to view TTC limits
          </CardDescription>
        </CardHeader>
        <CardContent className="px-2 pt-4 sm:px-6 sm:pt-6">
          <div className="flex h-[250px] w-full items-center justify-center text-muted-foreground">
            No flowgate selected
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card className="@container/card shadow-none">
      <CardHeader>
        <CardTitle>Hourly TTC Path Limits</CardTitle>
        <CardDescription>
          {currentHourData ? (
            `${currentHourData.value.toLocaleString()} MW ${currentHourData.datetime}`
          ) : (
            selectedFlowgate
          )}
        </CardDescription>
        <CardAction className="flex gap-2 flex-wrap items-center">
          {/* View Toggle Buttons */}
          <div className="flex rounded-md border flex-shrink-0">
            <Button
              variant={isChartView ? "default" : "ghost"}
              size="sm"
              onClick={() => setIsChartView(true)}
              className="rounded-r-none border-r h-8"
            >
              <IconChartLine className="h-4 w-4" />
            </Button>
            <Button
              variant={!isChartView ? "default" : "ghost"}
              size="sm"
              onClick={() => setIsChartView(false)}
              className="rounded-l-none h-8"
            >
              <IconTable className="h-4 w-4" />
            </Button>
          </div>
          
          {/* Date Range Picker */}
          <Popover>
            <PopoverTrigger asChild>
              <Button
                variant="outline"
                size="sm"
                className={cn(
                  "flex-1 min-w-0 max-w-[200px] @[540px]/card:max-w-[240px] justify-start text-left font-normal overflow-hidden h-8",
                  !dateRange && "text-muted-foreground"
                )}
              >
                <CalendarIcon className="mr-2 h-4 w-4 flex-shrink-0" />
                <span className="truncate">
                  {dateRange?.from ? (
                    dateRange.to ? (
                      dateRange.from.getTime() === dateRange.to.getTime() ? (
                        // Same date selected
                        format(dateRange.from, "MMM dd, yyyy")
                      ) : (
                        // Date range selected - use shorter format for mobile
                        <>
                          <span className="hidden @[540px]/card:inline">
                            {format(dateRange.from, "MMM dd, yyyy")} - {format(dateRange.to, "MMM dd, yyyy")}
                          </span>
                          <span className="@[540px]/card:hidden">
                            {format(dateRange.from, "MMM dd")} - {format(dateRange.to, "MMM dd")}
                          </span>
                        </>
                      )
                    ) : (
                      format(dateRange.from, "MMM dd, yyyy")
                    )
                  ) : (
                    "Pick a date range"
                  )}
                </span>
              </Button>
            </PopoverTrigger>
            <PopoverContent 
              className="w-auto p-0" 
              align="end" 
              side="bottom"
              sideOffset={4}
              alignOffset={0}
              avoidCollisions={true}
              collisionPadding={8}
            >
              <Calendar
                initialFocus
                mode="range"
                defaultMonth={dateRange?.from || new Date()}
                selected={dateRange}
                onSelect={setDateRange}
                numberOfMonths={isMobile ? 1 : 2}
                disabled={(date) =>
                  date > addDays(new Date(), 21) || date < addDays(new Date(), -30)
                }
              />
            </PopoverContent>
          </Popover>
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
                <p>Loading TTC data...</p>
              </div>
            ) : processedTTCData.length === 0 && !isLoading ? (
              <div className="flex h-full w-full items-center justify-center">
                <p>No TTC data available for the selected range.</p>
              </div>
            ) : (
              <LineChart data={processedTTCData} margin={{ left: 40, right: 10, top: 5, bottom: 20 }}>
                <CartesianGrid vertical={false} />
                <XAxis
                  dataKey="position"
                  tickLine={false}
                  axisLine={false}
                  tickMargin={8}
                  tickFormatter={xAxisConfig.formatter}
                  domain={[1, processedTTCData.length || 24]}
                  type="number"
                  scale="linear"
                  ticks={xAxisConfig.ticks}
                />
                <YAxis 
                  tickLine={false}
                  axisLine={false}
                  tickMargin={8}
                  tickFormatter={(value) => {
                    if (typeof value === 'number') {
                      return value.toLocaleString()
                    }
                    return String(value)
                  }}
                  domain={[
                    (dataMin: number) => Math.floor(dataMin * 0.95),
                    (dataMax: number) => Math.ceil(dataMax * 1.05)
                  ]}
                >
                  <Label 
                    value="TTC Limit (MW)" 
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
                          const qualityLabel = getQualityLabel(
                            dataPoint.date, 
                            dataPoint.hour_ending, 
                            dataPoint.quality
                          )
                          // Only show quality label if it exists (i.e., for Forecast)
                          return qualityLabel 
                            ? `${dataPoint.tooltip_label} (${qualityLabel})`
                            : dataPoint.tooltip_label
                        }
                        return "TTC Limit"
                      }}
                      formatter={(value, name, props) => {
                        const dataPoint = props.payload
                        return [
                          `${dataPoint.ttc_mw.toLocaleString()} MW`
                        ]
                      }}
                      indicator="dot"
                    />
                  }
                />
                <Line
                  dataKey="ttc_mw"
                  type="linear"
                  stroke="hsl(142, 71%, 45%)"
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
                <p>Loading TTC data...</p>
              </div>
            ) : tableData.length === 0 ? (
              <div className="flex h-full w-full items-center justify-center">
                <p>No TTC data available for the selected range.</p>
              </div>
            ) : (
              <div className="h-full overflow-hidden rounded-md border">
                <div className="h-full overflow-auto">
                  <Table>
                    <TableHeader className="sticky top-0 bg-background z-10">
                      <TableRow>
                        <TableHead className="w-[120px] font-semibold">Date</TableHead>
                        {Array.from({ length: 24 }, (_, i) => i + 1).map(hour => (
                          <TableHead key={hour} className="text-center min-w-[60px] font-semibold">
                            HE{hour.toString().padStart(2, '0')}
                          </TableHead>
                        ))}
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {tableData.map((row) => (
                        <TableRow key={row.date}>
                          <TableCell className="font-medium whitespace-nowrap">
                            {row.displayDate}
                          </TableCell>
                          {Array.from({ length: 24 }, (_, i) => i + 1).map(hour => {
                            const cellData = row.hours[hour]
                            return (
                              <TableCell 
                                key={hour} 
                                className={cn(
                                  "text-center text-xs",
                                  cellData?.isForecast && "bg-blue-50 dark:bg-blue-950/20"
                                )}
                              >
                                {cellData ? (
                                  <div className="flex flex-col">
                                    <span className="font-mono">
                                      {cellData.value.toLocaleString()}
                                    </span>
                                    {cellData.isForecast && (
                                      <span className="text-[10px] text-blue-600 dark:text-blue-400">
                                        F
                                      </span>
                                    )}
                                  </div>
                                ) : (
                                  <span className="text-muted-foreground">-</span>
                                )}
                              </TableCell>
                            )
                          })}
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
