"use client";

import { Button } from "@/components/ui/button";
import { useEffect, useRef, useState } from "react";
import { ArrowRight, Send } from "lucide-react";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardFooter, CardHeader } from "@/components/ui/card";
import { processQuery } from '@/lib/api';

// Pre-generate the data text outside the component
const DATA_TEXTS = generateDataTexts(150);

export default function Home() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [mousePosition, setMousePosition] = useState({ x: 0, y: 0 });
  const trailPositions = useRef<Array<{x: number, y: number}>>([]);
  const requestRef = useRef<number>();
  const previousTimeRef = useRef<number>();
  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  
  // State to hold the randomized positions and styles
  const [textStyles, setTextStyles] = useState<Array<{
    top: string;
    left: string;
    animation: string;
    fontSize: string;
    opacity: number;
    transform: string;
  }>>([]);
  
  // Initialize trail positions
  useEffect(() => {
    // Initialize with 5 points at the center
    const centerX = window.innerWidth / 2;
    const centerY = window.innerHeight / 2;
    trailPositions.current = Array(5).fill({ x: centerX, y: centerY });
    
    // Generate random styles for text elements on client-side only
    const newTextStyles = DATA_TEXTS.map((_, i) => {
      // Create a more structured distribution by dividing the screen into a grid
      const gridCols = 10;
      const gridRows = 10;
      
      // Calculate grid position
      const gridCol = i % gridCols;
      const gridRow = Math.floor(i / gridCols) % gridRows;
      
      // Add randomness within the grid cell (±10%)
      const randomOffsetX = (Math.random() - 0.5) * 20;
      const randomOffsetY = (Math.random() - 0.5) * 20;
      
      // Calculate final position with margins to prevent edge clipping
      const left = (gridCol * (100 / gridCols)) + randomOffsetX;
      const top = (gridRow * (100 / gridRows)) + randomOffsetY;
      
      // Define the "safe zones"
      const isInAPIButtonZone = gridCol >= 8 && gridRow <= 1;
      
      // Center zone for Crystal logo and subheader (middle columns, middle rows)
      const isInCenterLogoZone = 
        (gridCol >= 3 && gridCol <= 6) && // Middle columns
        (gridRow >= 4 && gridRow <= 5);   // Middle rows
      
      // Chat interface zone (bottom-center area)
      const isInChatInterfaceZone = 
        (gridCol >= 2 && gridCol <= 7) && // Middle-wide columns
        (gridRow >= 6 && gridRow <= 9);   // Bottom rows
      
      // If in any safe zone, move the text elsewhere
      let safeLeft = left;
      let safeTop = top;
      
      if (isInAPIButtonZone) {
        // Move to a different area (middle-left in this case)
        safeLeft = 20 + (Math.random() * 20);
        safeTop = 40 + (Math.random() * 20);
      } else if (isInCenterLogoZone) {
        // Move to bottom area
        safeLeft = 30 + (Math.random() * 40);
        safeTop = 70 + (Math.random() * 20);
      } else if (isInChatInterfaceZone) {
        // Move to top or sides
        if (Math.random() > 0.5) {
          // Move to top
          safeLeft = 10 + (Math.random() * 80);
          safeTop = 10 + (Math.random() * 30);
        } else {
          // Move to sides
          safeLeft = Math.random() > 0.5 ? 
            5 + (Math.random() * 15) : // Left side
            80 + (Math.random() * 15); // Right side
          safeTop = 30 + (Math.random() * 40);
        }
      } else {
        // Otherwise just ensure positions stay within visible bounds (5% to 95%)
        safeLeft = Math.max(5, Math.min(95, left));
        safeTop = Math.max(5, Math.min(95, top));
      }
      
      const animationDelay = Math.random() * 10;
      const animationDuration = 15 + Math.random() * 20;
      const animationType = i % 2 === 0 ? 'float' : 'float-alt';
      
      return {
        top: `${safeTop}%`,
        left: `${safeLeft}%`,
        animation: `${animationType} ${animationDuration}s ease-in-out ${animationDelay}s infinite`,
        fontSize: `${Math.max(0.7, Math.random() * 0.3 + 0.7)}rem`,
        opacity: 0.3 + Math.random() * 0.5,
        transform: `rotate(${(Math.random() - 0.5) * 10}deg)`,
      };
    });
    
    setTextStyles(newTextStyles);
  }, []);
  
  // Animation loop for the trail effect
  const animate = (time: number) => {
    if (previousTimeRef.current !== undefined) {
      // Update trail positions with physics
      const mousePos = { x: mousePosition.x, y: mousePosition.y };
      
      // Update the first point to follow the mouse with some easing
      if (trailPositions.current.length > 0) {
        const firstPoint = trailPositions.current[0];
        const dx = mousePos.x - firstPoint.x;
        const dy = mousePos.y - firstPoint.y;
        
        // Apply easing (0.2 = more lag, 0.8 = less lag)
        trailPositions.current[0] = {
          x: firstPoint.x + dx * 0.3,
          y: firstPoint.y + dy * 0.3
        };
        
        // Update the rest of the trail to follow the point ahead of it
        for (let i = 1; i < trailPositions.current.length; i++) {
          const point = trailPositions.current[i];
          const prevPoint = trailPositions.current[i - 1];
          const dx = prevPoint.x - point.x;
          const dy = prevPoint.y - point.y;
          
          trailPositions.current[i] = {
            x: point.x + dx * 0.3,
            y: point.y + dy * 0.3
          };
        }
      }
      
      // Update CSS variables for all trail points
      if (containerRef.current) {
        // Main spotlight follows the mouse directly
        containerRef.current.style.setProperty('--mouse-x', `${mousePos.x}px`);
        containerRef.current.style.setProperty('--mouse-y', `${mousePos.y}px`);
        
        // Trail points
        trailPositions.current.forEach((pos, i) => {
          containerRef.current?.style.setProperty(`--trail-x-${i}`, `${pos.x}px`);
          containerRef.current?.style.setProperty(`--trail-y-${i}`, `${pos.y}px`);
        });
      }
    }
    
    previousTimeRef.current = time;
    requestRef.current = requestAnimationFrame(animate);
  };
  
  useEffect(() => {
    requestRef.current = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(requestRef.current as number);
  }, [mousePosition]);
  
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!containerRef.current) return;
      
      const rect = containerRef.current.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      
      setMousePosition({ x, y });
    };
    
    const container = containerRef.current;
    if (container) {
      container.addEventListener('mousemove', handleMouseMove);
    }
    
    return () => {
      if (container) {
        container.removeEventListener('mousemove', handleMouseMove);
      }
    };
  }, []);

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInputValue(e.target.value);
  };

  const handleSubmit = async () => {
    if (!inputValue.trim()) return;
    
    console.log("Submitting query:", inputValue);
    setIsLoading(true);
    
    try {
      const response = await processQuery(inputValue);
      console.log("API Response:", response);
      
      // You can access specific parts of the response:
      if (response.summary) {
        console.log("Summary:", response.summary);
      }
      
      if (response.datasets) {
        console.log("Datasets:", response.datasets.length);
        response.datasets.forEach((dataset, index) => {
          console.log(`Dataset ${index + 1}: ${dataset.title}`);
          console.log(`Relevance: ${dataset.relevance_score}`);
        });
      }
      
    } catch (error) {
      console.error("Error processing query:", error);
    } finally {
      setIsLoading(false);
      setInputValue("");
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="flex items-center justify-center min-h-screen bg-neutral-50 dark:bg-neutral-50 p-4">
      <div
        ref={containerRef}
        className="w-full h-[calc(100vh-2rem)] rounded-lg bg-cover bg-center flex flex-col items-center justify-center relative overflow-hidden"
        style={{
          backgroundImage: "url('/images/crystal-bg0.png')",
          '--mouse-x': '50%',
          '--mouse-y': '50%',
          '--trail-x-0': '50%',
          '--trail-y-0': '50%',
          '--trail-x-1': '50%',
          '--trail-y-1': '50%',
          '--trail-x-2': '50%',
          '--trail-y-2': '50%',
          '--trail-x-3': '50%',
          '--trail-y-3': '50%',
          '--trail-x-4': '50%',
          '--trail-y-4': '50%',
        } as React.CSSProperties}
      >
        {/* API Link in upper right corner */}
        <div className="absolute top-6 right-6 z-30">
          <Button 
            variant="link" 
            className="text-white flex items-center gap-1 hover:text-white/80 transition-colors"
            style={{ fontFamily: 'var(--font-geist-sans)' }}
          >
            API <ArrowRight className="h-4 w-4" />
          </Button>
        </div>

        {/* Data Text Background Layer */}
        <div className="absolute inset-0 z-0 data-text-background">
          {DATA_TEXTS.map((text, i) => (
            <div 
              key={i} 
              className="data-text-item text-xs font-mono text-white absolute"
              style={textStyles[i] ? {
                top: textStyles[i].top,
                left: textStyles[i].left,
                animation: textStyles[i].animation,
                fontSize: textStyles[i].fontSize,
                opacity: textStyles[i].opacity,
                transform: textStyles[i].transform,
                maxWidth: '300px',
                textWrap: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis'
              } : {}}
            >
              {text}
            </div>
          ))}
        </div>
        
        {/* Background Image Layer with trail effect */}
        <div 
          className="absolute inset-0 z-10 bg-cover bg-center trail-mask" 
          style={{ backgroundImage: "url('/images/crystal-bg0.png')" }}
        ></div>
        
        {/* Content */}
        <div className="flex items-center z-20 relative">
          <img 
            src="/images/gem.svg" 
            alt="Crystal Gem Logo" 
            className="h-12 w-12 mr-3" 
            style={{ filter: "brightness(0) invert(1)" }}
          />
          <h1 className="text-6xl font-bold text-white" style={{ fontFamily: 'var(--font-geist-sans)' }}>
            Crystal
          </h1>
        </div>
        <div className="relative mt-2 z-20">
          <div
            className="absolute inset-0 bg-black opacity-25"
            style={{ filter: "blur(15px)" }}
          ></div>
          <h2 className="relative text-xl sm:text-2xl text-white" style={{ fontFamily: 'var(--font-geist-sans)' }}>
            Connect your queries to government data.
          </h2>
        </div>
        
        {/* Chat Interface */}
        <div className="mt-8 z-20 relative w-full max-w-3xl">
          <Card className="bg-white/10 backdrop-blur-xl border-white/20">
            <CardContent className="pt-3 pb-0">
              <div className="flex flex-wrap gap-2">
                {["Air quality in Greenwich Village", "Seattle Section 8 vacancy rates", "Orange grove emissions factors"].map((sampleQuery, i) => (
                  <button
                    key={i}
                    onClick={() => setInputValue(sampleQuery)}
                    className="text-sm bg-white/10 hover:bg-white/20 text-white/80 hover:text-white px-3 py-1 rounded-full transition-colors"
                  >
                    {sampleQuery}
                  </button>
                ))}
              </div>
            </CardContent>
            <CardFooter className="pt-1 pb-3">
              <div className="flex w-full items-end gap-2">
                <Textarea
                  placeholder="Ask a question about government data..."
                  className="min-h-[60px] bg-white/10 border-white/20 text-white placeholder:text-white/90 resize-none text-base"
                  value={inputValue}
                  onChange={handleInputChange}
                  onKeyDown={handleKeyDown}
                />
                <Button 
                  size="icon" 
                  className="shrink-0 bg-white/20 hover:bg-white/30 text-white h-[60px] w-[60px]"
                  onClick={handleSubmit}
                  disabled={isLoading || !inputValue.trim()}
                >
                  {isLoading ? (
                    <div className="h-6 w-6 animate-spin rounded-full border-2 border-white border-t-transparent" />
                  ) : (
                    <Send className="h-6 w-6" />
                  )}
                </Button>
              </div>
            </CardFooter>
          </Card>
        </div>
      </div>
    </div>
  );
}

// Generate all data texts at once
function generateDataTexts(count: number) {
  const texts = [];
  
  const patterns = [
    "PM2.5 and ozone levels in ${location} during rush hour in ${season} ${year}?",
    "Economic impact of tech layoffs in ${region} from Q2 ${year} to Q1 ${year2}?",
    "Percentage of first-gen students with STEM degrees from ${state} public universities in ${year}?",
    "Seasonal-adjusted unemployment for manufacturing in ${state} vs. national average?",
    "Median housing prices: ${neighborhood} vs. ${neighborhood2} in ${city} since ${year}?",
    "Level 1 trauma centers within 15mi of ${location} with pediatric care?",
    "${type} vs. ${type2} commuters in ${city} during peak/off-peak hours?",
    "Income inequality in ${city} census tracts for $${income}k-$${income2}k households?",
    "Daily NO2/SO2 emissions in ${neighborhood} during ${season} ${year}?",
    "Demographic changes in ${neighborhood}, ${city} since ${year} by age/ethnicity?",
    "Fastest-growing vs. declining industries in ${state} since ${year}?",
    "Per-pupil funding: Title I vs. non-Title I schools in ${city} (${year}-${year2})?",
    "Median price/sqft for 2BR apartments in ${neighborhood} vs. ${city} average?",
    "${city} transit ridership correlation with gas prices since ${year}?",
    "HPV/MMR vaccination rates for ages 4-6 in ${location} by income?",
    "Violent crime in ${neighborhood}, ${city} by time and day?",
    "Average commute time for ${type} users in ${city} during ${season}?",
    "Emissions from orange groves in ${region} since ${year}?",
    "Air quality vs. respiratory admissions in Greenwich Village since 2015?",
    "Impact of ${policy} on ${dataset} in ${location} by demographics?",
    "Water quality metrics for ${river} watershed after ${event} in ${year}?",
    "Correlation between ${disease} cases and ${environmental_factor} in ${county}?",
    "Renewable energy adoption rates in ${state} by income bracket (${year}-${year2})?",
    "Food desert mapping in ${city} with >1mi to fresh produce retailers?",
    "Broadband access disparities in ${rural_area} vs ${urban_area} (${year})?",
    "Maternal health outcomes by zip code in ${city} for ${year}-${year2}?",
    "Correlation between tree canopy coverage and summer temperatures in ${neighborhood}?",
    "Effectiveness of ${program} on ${metric} for ${demographic} in ${location}?",
    "Flood risk assessment for ${neighborhood} under ${inches}\" rainfall scenarios?",
    "Pedestrian safety metrics at ${intersection} before/after ${infrastructure} installation?",
    "Comparative analysis of ${pollutant} levels near ${industry} sites in ${region}?",
    "Impact of ${policy} on small business formation in ${neighborhood} (${year}-${year2})?",
    "Correlation between ${public_service} funding and ${outcome} in ${city} districts?",
    "Affordable housing availability within ${distance}mi of major ${employer} in ${city}?",
    "Childhood ${health_metric} rates in ${neighborhood} vs. ${city} average since ${year}?",
  ];
  
  const regions = ['NYC', 'LA', 'CHI', 'DC', 'SF', 'MIA', 'ATL', 'BOS', 'SEA', 'DEN', 'PHX', 'PHL'];
  const endpoints = ['metrics', 'analysis', 'trends', 'reports', 'forecasts', 'indicators', 'statistics'];
  const params = ['dataset', 'metrics', 'trends', 'pollution', 'demographics', 'economics', 'health'];
  const locations = ['nyc', 'manhattan', 'brooklyn', 'queens', 'bronx', 'staten island', 'harlem', 'tribeca'];
  const datasets = ['air_quality', 'demographics', 'economy', 'education', 'transportation', 'housing', 'health', 'crime'];
  const cities = ['New York', 'Los Angeles', 'Chicago', 'Houston', 'Phoenix', 'Philadelphia', 'San Antonio', 'San Diego', 'Dallas', 'Austin'];
  const states = ['CA', 'NY', 'TX', 'FL', 'IL', 'PA', 'OH', 'GA', 'NC', 'MI', 'NJ', 'VA', 'WA', 'AZ', 'MA'];
  const types = ['bus', 'subway', 'car', 'bike', 'walk', 'scooter', 'rideshare', 'carpool', 'train', 'ferry'];
  const neighborhoods = ['Greenwich Village', 'Williamsburg', 'Silver Lake', 'Lincoln Park', 'Montrose', 'Capitol Hill', 'Mission District', 'Wicker Park', 'Fishtown', 'Buckhead'];
  const seasons = ['summer', 'winter', 'fall', 'spring', 'rainy season', 'dry season', 'peak tourism', 'off-season'];
  const policies = ['congestion pricing', 'rent control', 'school choice', 'emissions cap', 'zoning reform', 'minimum wage', 'tax incentives', 'water restrictions', 'plastic ban'];
  const rivers = ['Hudson', 'Mississippi', 'Colorado', 'Potomac', 'Ohio', 'Delaware', 'Columbia', 'Missouri', 'Rio Grande'];
  const events = ['hurricane', 'flood', 'drought', 'industrial spill', 'infrastructure failure', 'policy change', 'remediation effort'];
  const diseases = ['asthma', 'diabetes', 'heart disease', 'COVID-19', 'influenza', 'Lyme disease', 'lead poisoning'];
  const environmental_factors = ['air pollution', 'water quality', 'green space access', 'industrial proximity', 'traffic density', 'heat islands'];
  const counties = ['Kings County', 'Cook County', 'Harris County', 'Maricopa County', 'Los Angeles County', 'Miami-Dade County', 'Suffolk County'];
  const rural_areas = ['Appalachia', 'Central Valley', 'Navajo Nation', 'Ozarks', 'Mississippi Delta', 'Northern Maine', 'Eastern Kentucky'];
  const urban_areas = ['Manhattan', 'Downtown LA', 'Chicago Loop', 'Miami Metro', 'Seattle Urban Core', 'Boston Metro'];
  
  // Use a seeded random function to ensure consistency
  const seededRandom = createSeededRandom(12345);
  
  for (let i = 0; i < count; i++) {
    const patternIndex = Math.floor(seededRandom() * patterns.length);
    let text = patterns[patternIndex];
    
    text = text
      .replace(/\${id}/g, Math.floor(seededRandom() * 1000).toString(16))
      .replace(/\${val}/g, Math.floor(seededRandom() * 100).toString())
      .replace(/\${region}/g, regions[Math.floor(seededRandom() * regions.length)])
      .replace(/\${year}/g, (2010 + Math.floor(seededRandom() * 14)).toString())
      .replace(/\${year2}/g, (2015 + Math.floor(seededRandom() * 9)).toString())
      .replace(/\${endpoint}/g, endpoints[Math.floor(seededRandom() * endpoints.length)])
      .replace(/\${param}/g, params[Math.floor(seededRandom() * params.length)])
      .replace(/\${time}/g, '1674218521' + i.toString())
      .replace(/\${index}/g, Math.floor(seededRandom() * 100).toString())
      .replace(/\${location}/g, locations[Math.floor(seededRandom() * locations.length)])
      .replace(/\${value}/g, (seededRandom() * 10).toFixed(2))
      .replace(/\${dataset}/g, datasets[Math.floor(seededRandom() * datasets.length)])
      .replace(/\${city}/g, cities[Math.floor(seededRandom() * cities.length)])
      .replace(/\${income}/g, (Math.floor(seededRandom() * 100) + 30).toString())
      .replace(/\${income2}/g, (Math.floor(seededRandom() * 100) + 80).toString())
      .replace(/\${state}/g, states[Math.floor(seededRandom() * states.length)])
      .replace(/\${rate}/g, (seededRandom() * 8 + 2).toFixed(1))
      .replace(/\${count}/g, (Math.floor(seededRandom() * 10000) + 5000).toString())
      .replace(/\${price}/g, (Math.floor(seededRandom() * 900) + 300).toString())
      .replace(/\${type}/g, types[Math.floor(seededRandom() * types.length)])
      .replace(/\${type2}/g, types[Math.floor(seededRandom() * types.length)])
      .replace(/\${percent}/g, (Math.floor(seededRandom() * 60) + 10).toString())
      .replace(/\${neighborhood}/g, neighborhoods[Math.floor(seededRandom() * neighborhoods.length)])
      .replace(/\${neighborhood2}/g, neighborhoods[Math.floor(seededRandom() * neighborhoods.length)])
      .replace(/\${season}/g, seasons[Math.floor(seededRandom() * seasons.length)])
      .replace(/\${policy}/g, policies[Math.floor(seededRandom() * policies.length)])
      .replace(/\${river}/g, rivers[Math.floor(seededRandom() * rivers.length)])
      .replace(/\${event}/g, events[Math.floor(seededRandom() * events.length)])
      .replace(/\${disease}/g, diseases[Math.floor(seededRandom() * diseases.length)])
      .replace(/\${environmental_factor}/g, environmental_factors[Math.floor(seededRandom() * environmental_factors.length)])
      .replace(/\${county}/g, counties[Math.floor(seededRandom() * counties.length)])
      .replace(/\${rural_area}/g, rural_areas[Math.floor(seededRandom() * rural_areas.length)])
      .replace(/\${urban_area}/g, urban_areas[Math.floor(seededRandom() * urban_areas.length)])
      .replace(/\${inches}/g, (Math.floor(seededRandom() * 10) + 1).toString())
      .replace(/\${distance}/g, (Math.floor(seededRandom() * 20) + 1).toString())
      .replace(/\${employer}/g, "employer")
      .replace(/\${health_metric}/g, "health metric")
      .replace(/\${program}/g, "program")
      .replace(/\${metric}/g, "metric")
      .replace(/\${demographic}/g, "demographic")
      .replace(/\${intersection}/g, "intersection")
      .replace(/\${infrastructure}/g, "infrastructure")
      .replace(/\${pollutant}/g, "pollutant")
      .replace(/\${industry}/g, "industry")
      .replace(/\${public_service}/g, "public service")
      .replace(/\${outcome}/g, "outcome");
    
    texts.push(text);
  }
  
  return texts;
}

// Create a seeded random function for consistent results
function createSeededRandom(seed: number) {
  return function() {
    seed = (seed * 9301 + 49297) % 233280;
    return seed / 233280;
  };
}