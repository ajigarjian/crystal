"use client"

import * as React from "react"
import { Line, LineChart, CartesianGrid, XAxis, YAxis, Label } from "recharts"
import { addDays, format, startOfDay } from "date-fns"

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
import { getTTCFlowgateData, TTCDataPoint } from "@/lib/firebase"

interface ProcessedTTCData {
  hour: string;
  ttc_mw: number;
  hour_ending: number;
  quality: 'F' | 'R'; // Forecast or Real
  datetime_utc: string;
}

const chartConfig = {
  ttc_mw: {
    label: "TTC Limit (MW)",
    color: "hsl(142, 71%, 45%)",
  },
} satisfies ChartConfig

// Helper to format hour ending (1-24 to HE01-HE24)
const formatHourEnding = (hourEnding: number): string => {
  return `HE${hourEnding.toString().padStart(2, '0')}`;
};

// Helper to generate date options for the dropdown
const generateDateOptions = () => {
  const today = new Date();
  const options = [];
  
  // Add past 7 days
  for (let i = 7; i >= 0; i--) {
    const date = addDays(today, -i);
    options.push({
      value: format(date, 'yyyy-MM-dd'),
      label: i === 0 ? 'Today' : i === 1 ? 'Yesterday' : format(date, 'MMM dd'),
      isToday: i === 0
    });
  }
  
  // Add future 14 days (2 weeks forecast)
  for (let i = 1; i <= 14; i++) {
    const date = addDays(today, i);
    options.push({
      value: format(date, 'yyyy-MM-dd'),
      label: format(date, 'MMM dd'),
      isToday: false
    });
  }
  
  return options;
};

interface ChartTTCFlowgateProps {
  selectedFlowgate: string;
}

export function ChartTTCFlowgate({ selectedFlowgate }: ChartTTCFlowgateProps) {
  const isMobile = useIsMobile()
  const [selectedDate, setSelectedDate] = React.useState<string>(format(new Date(), 'yyyy-MM-dd'))
  const [processedTTCData, setProcessedTTCData] = React.useState<ProcessedTTCData[]>([])
  const [isLoading, setIsLoading] = React.useState(true)
  
  // Add state for current hour data
  const [currentHourData, setCurrentHourData] = React.useState<{
    value: number;
    datetime: string;
  } | null>(null)

  const dateOptions = React.useMemo(() => generateDateOptions(), []);

  // Fetch current hour data separately
  React.useEffect(() => {
    const fetchCurrentHourData = async () => {
      try {
        const today = format(new Date(), 'yyyy-MM-dd')
        const rawData: TTCDataPoint[] = await getTTCFlowgateData(selectedFlowgate, today)
        
        if (rawData.length > 0) {
          // Get current hour (1-24 format)
          const now = new Date()
          const currentHour = now.getUTCHours() + 1 // Convert 0-23 to 1-24
          
          // Find data for current hour, or closest available
          let currentPoint = rawData.find(point => point.hour_ending === currentHour)
          if (!currentPoint && rawData.length > 0) {
            // If no exact match, get the latest available data point
            currentPoint = rawData.reduce((latest, current) => 
              current.hour_ending > latest.hour_ending ? current : latest
            )
          }
          
          if (currentPoint) {
            // Format the datetime in the requested format
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

  React.useEffect(() => {
    const fetchData = async () => {
      setIsLoading(true)
      try {
        const rawData: TTCDataPoint[] = await getTTCFlowgateData(selectedFlowgate, selectedDate)
        
        const transformed: ProcessedTTCData[] = rawData.map(point => ({
          hour: formatHourEnding(point.hour_ending),
          ttc_mw: Math.trunc(point.value_mw),
          hour_ending: point.hour_ending,
          quality: point.quality,
          datetime_utc: point.datetime_utc
        }))
        
        // Sort by hour_ending to ensure proper order
        transformed.sort((a, b) => a.hour_ending - b.hour_ending)
        
        setProcessedTTCData(transformed)
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
  }, [selectedFlowgate, selectedDate])

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
        <CardAction>
          <Select
            value={selectedDate}
            onValueChange={(value: string) => {
              if (value) setSelectedDate(value)
            }}
          >
            <SelectTrigger
              className="flex w-48 @[767px]/card:w-48"
              size="sm"
              aria-label="Select a date"
            >
              <SelectValue placeholder="Select date" />
            </SelectTrigger>
            <SelectContent className="rounded-xl max-h-[200px]">
              {dateOptions.map((option) => (
                <SelectItem key={option.value} value={option.value} className="rounded-lg">
                  {option.label}
                  {option.isToday && " (Today)"}
                </SelectItem>
              ))}
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
              <p>Loading TTC data...</p>
            </div>
          ) : processedTTCData.length === 0 && !isLoading ? (
            <div className="flex h-full w-full items-center justify-center">
              <p>No TTC data available for the selected flowgate and date.</p>
            </div>
          ) : (
            <LineChart data={processedTTCData} margin={{ left: 40, right: 10, top: 5, bottom: 20 }}>
              <CartesianGrid vertical={false} />
              <XAxis
                dataKey="hour_ending"
                tickLine={false}
                axisLine={false}
                tickMargin={8}
                tickFormatter={formatHourEnding}
                domain={[1, 24]}
                type="number"
                scale="linear"
                ticks={[1, 6, 12, 18, 24]}
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
                        const hourEnding = dataPoint.hour_ending
                        const quality = dataPoint.quality
                        const qualityLabel = quality === 'F' ? 'Forecast' : 'Real'
                        return `${formatHourEnding(hourEnding)} (${qualityLabel})`
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
                dot={{ r: 4 }}
                activeDot={{ r: 6 }}
                connectNulls={false}
              />
            </LineChart>
          )}
        </ChartContainer>
      </CardContent>
    </Card>
  )
} 