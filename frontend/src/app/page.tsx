"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useEffect, useRef, useState, useMemo } from "react";
import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { warmFunctions } from "@/lib/firebase";
import { useRouter } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import queryExamples from "@/components/QueryExamples";

// Reduce the number of data texts for better performance
const DATA_TEXTS = generateDataTexts(40); // Reduced from 150 to 40

export default function Home() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [mousePosition, setMousePosition] = useState({ x: 0, y: 0 });
  const trailPositions = useRef<Array<{x: number, y: number}>>([]);
  const requestRef = useRef<number | undefined>(undefined);
  const previousTimeRef = useRef<number | undefined>(undefined);
  const [query, setQuery] = useState("");
  const [isMobile, setIsMobile] = useState(false);
  const router = useRouter();
  
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
    // Initialize with just the center point we need
    const centerX = window.innerWidth / 2;
    const centerY = window.innerHeight / 2;
    trailPositions.current = [
      { x: centerX, y: centerY },
      { x: centerX, y: centerY },
      { x: centerX, y: centerY }
    ];
    
    // Generate random styles for text elements on client-side only - simplified
    const newTextStyles = DATA_TEXTS.map((_, i) => {
      // Create a more structured distribution by dividing the screen into sections
      const gridCols = 8; // Fewer columns
      const gridRows = 6; // Fewer rows
      
      // Calculate grid position
      const gridCol = i % gridCols;
      const gridRow = Math.floor(i / gridCols) % gridRows;
      
      // Add minimal randomness
      const randomOffsetX = (Math.random() - 0.5) * 10;
      const randomOffsetY = (Math.random() - 0.5) * 10;
      
      // Calculate final position with margins to prevent edge clipping
      const left = (gridCol * (100 / gridCols)) + randomOffsetX;
      const top = (gridRow * (100 / gridRows)) + randomOffsetY;
      
      // Define a single large safe zone for the center content
      const isInSafeZone = 
        (gridCol >= 2 && gridCol <= 5) && // Middle columns
        (gridRow >= 1 && gridRow <= 4);   // Middle rows
      
      // If in safe zone, move to edges
      let safeLeft = left;
      let safeTop = top;
      
      if (isInSafeZone) {
        // Create larger margins around important elements
        // Move to one of the corners or edges
        const position = Math.floor(Math.random() * 4); // 0-3 for different positions
        
        switch(position) {
          case 0: // Left side
            safeLeft = 5 + (Math.random() * 10);
            safeTop = 20 + (Math.random() * 60);
            break;
          case 1: // Right side
            safeLeft = 85 + (Math.random() * 10);
            safeTop = 20 + (Math.random() * 60);
            break;
          case 2: // Top
            safeLeft = 20 + (Math.random() * 60);
            safeTop = 5 + (Math.random() * 10);
            break;
          case 3: // Bottom
            safeLeft = 20 + (Math.random() * 60);
            safeTop = 85 + (Math.random() * 10);
            break;
        }
      } else {
        // Otherwise just ensure positions stay within visible bounds (5% to 95%)
        safeLeft = Math.max(5, Math.min(95, left));
        safeTop = Math.max(5, Math.min(95, top));
      }
      
      // Simplified animations with longer durations to reduce CPU load
      const animationDelay = Math.random() * 5;
      const animationDuration = 25 + Math.random() * 15; // Slower animations
      const animationType = i % 2 === 0 ? 'float' : 'float-alt';
      
      return {
        top: `${safeTop}%`,
        left: `${safeLeft}%`,
        animation: `${animationType} ${animationDuration}s ease-in-out ${animationDelay}s infinite`,
        fontSize: `${Math.max(0.7, Math.random() * 0.2 + 0.7)}rem`, // More consistent sizes
        opacity: 0.3 + Math.random() * 0.3, // Lower max opacity
        transform: `rotate(${(Math.random() - 0.5) * 5}deg)`, // Less rotation
      };
    });
    
    setTextStyles(newTextStyles);
  }, []);
  
  // Optimized animation loop for the trail effect
  const animate = (time: number) => {
    if (previousTimeRef.current !== undefined) {
      // Update trail positions with physics - only using one trail point for performance
      const mousePos = { x: mousePosition.x, y: mousePosition.y };
      
      // Update the trail point to follow the mouse with easing
      if (trailPositions.current.length > 0) {
        const point = trailPositions.current[2]; // We only need the middle point now
        const dx = mousePos.x - point.x;
        const dy = mousePos.y - point.y;
        
        // Apply easing
        trailPositions.current[2] = {
          x: point.x + dx * 0.2,
          y: point.y + dy * 0.2
        };
      }
      
      // Update CSS variables - minimized to only what we need
      if (containerRef.current) {
        // Main spotlight follows the mouse directly
        containerRef.current.style.setProperty('--mouse-x', `${mousePos.x}px`);
        containerRef.current.style.setProperty('--mouse-y', `${mousePos.y}px`);
        
        // Just one trail point now (optimized)
        const pos = trailPositions.current[2];
        containerRef.current.style.setProperty('--trail-x-2', `${pos.x}px`);
        containerRef.current.style.setProperty('--trail-y-2', `${pos.y}px`);
      }
    }
    
    previousTimeRef.current = time;
    requestRef.current = requestAnimationFrame(animate);
  };
  
  useEffect(() => {
    // Run animation
    requestRef.current = requestAnimationFrame(animate);
    return () => {
      if (requestRef.current) {
        cancelAnimationFrame(requestRef.current as number);
      }
    };
  }, [mousePosition]);
  
  useEffect(() => {
    // Throttled mouse move handler to avoid too many updates
    let lastCall = 0;
    const throttleDelay = 30; // ms between updates (roughly 30fps)
    
    const handleMouseMove = (e: MouseEvent) => {
      const now = Date.now();
      
      // Skip if it's been less than throttleDelay since last update
      if (now - lastCall < throttleDelay) return;
      
      lastCall = now;
      
      if (!containerRef.current) return;
      
      const rect = containerRef.current.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      
      setMousePosition({ x, y });
    };
    
    // Only add the event listener if not mobile
    if (!isMobile) {
      const container = containerRef.current;
      if (container) {
        container.addEventListener('mousemove', handleMouseMove);
      }
      
      return () => {
        if (container) {
          container.removeEventListener('mousemove', handleMouseMove);
        }
      };
    }
  }, [isMobile]); // Depend on isMobile so it changes when screen size changes

  // Add this effect to warm functions when the page loads
  useEffect(() => {
    warmFunctions();
  }, []);

  // Add this effect to check for mobile
  useEffect(() => {
    const checkMobile = () => {
      setIsMobile(window.innerWidth < 640);
    };
    
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);
  
  // Replace the existing exampleQueries implementation with this:
  const exampleQueries = useMemo(() => {
    // Use a consistent seed for the shuffle
    const shuffleWithSeed = (array: string[]) => {
      const seededRandom = (seed: number) => {
        let x = Math.sin(seed++) * 10000;
        return x - Math.floor(x);
      };
      
      // Create a copy of the array
      const shuffled = [...array];
      let seed = 1; // Use a fixed seed
      
      // Fisher-Yates shuffle with seeded random
      for (let i = shuffled.length - 1; i > 0; i--) {
        const j = Math.floor(seededRandom(seed++) * (i + 1));
        [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
      }
      
      return shuffled;
    };

    return shuffleWithSeed(queryExamples).slice(0, 3);
  }, []); // Empty dependency array means this only runs once
  
  // Get displayed examples based on screen size
  const displayedExamples = isMobile ? exampleQueries : exampleQueries;
  
  // Add this handler for example clicks
  const handleExampleClick = (exampleQuery: string) => {
    router.push(`/alpha?query=${encodeURIComponent(exampleQuery)}`);
  };
  
  // Add this handler for search submission
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim()) {
      router.push(`/alpha?query=${encodeURIComponent(query)}`);
    }
  };
  
  // Add this handler for keydown events
  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (query.trim()) {
        router.push(`/alpha?query=${encodeURIComponent(query)}`);
      }
    }
  };

  return (
    <div className="flex items-center justify-center min-h-screen bg-neutral-50 dark:bg-neutral-50 p-4">
      <div
        ref={containerRef}
        className="w-full h-[calc(100vh-2rem)] rounded-lg bg-cover bg-center flex flex-col justify-center relative overflow-hidden"
        style={{
          backgroundImage: "url('/images/crystalbackground.png')",
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
        {/* Navigation links */}
        <div className="absolute top-6 right-6 z-30 flex gap-4">
          <Link href="/privacy">
            <Button 
              variant="link" 
              className="text-white flex items-center gap-1 hover:text-white/80 transition-colors"
              style={{ fontFamily: 'var(--font-geist-sans)' }}
            >
              Privacy <ArrowRight className="h-4 w-4" />
            </Button>
          </Link>
          <Link href="/waitlist">
            <Button 
              variant="link" 
              className="text-white flex items-center gap-2 hover:text-white/80 transition-colors"
              style={{ fontFamily: 'var(--font-geist-sans)' }}
            >
              Join <Badge className="bg-purple-500 hover:bg-purple-500 text-xs py-0 px-1.5 font-normal rounded-sm">BETA</Badge> Waitlist <ArrowRight className="h-4 w-4" />
            </Button>
          </Link>
        </div>
        
        {/* Data Text Background Layer - Optimized with will-change and transform properties */}
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
                transform: `${textStyles[i].transform} translateZ(0)`, 
                willChange: 'transform, opacity',
                maxWidth: '300px',
                textWrap: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                visibility: isMobile ? 'hidden' : 'visible' // Hide on mobile for performance
              } : {}}
            >
              {/* Only render visible elements on non-mobile */}
              {!isMobile && text}
            </div>
          ))}
        </div>
        
        {/* Background Image Layer with trail effect and darker overlay */}
        <div 
          className="absolute inset-0 z-10 bg-cover bg-center trail-mask after:absolute after:inset-0 after:bg-black/70 after:backdrop-blur-sm" 
          style={{ backgroundImage: "url('/images/crystalbackground.png')" }}
        ></div>
        
        {/* Content */}
        <div className="flex items-center justify-center z-20 relative w-full">
          <img 
            src="/images/gem.svg" 
            alt="Crystal Gem Logo" 
            className="h-12 w-12 mr-3" 
            style={{ filter: "brightness(0) invert(1)" }}
          />
          <div className="relative">
            <h1 className="text-6xl font-bold text-white" style={{ fontFamily: 'var(--font-geist-sans)' }}>
              Crystal
              <Badge 
                className="ml-2 absolute -top-3 -right-16 bg-green-500 hover:bg-green-500 text-xs font-normal uppercase tracking-wide"
              >
                Alpha
              </Badge>
            </h1>
          </div>
        </div>
        <div className="relative p-2 mt-2 z-20 text-center w-full">
          <h2 className="relative text-xl sm:text-2xl text-white" style={{ fontFamily: 'var(--font-geist-sans)' }}>
            Querying for Deep<span className="text-green-500 animate-pulse drop-shadow-[0_0_8px_rgba(34,197,94,0.8)]" style={{ textShadow: '0 0 10px rgba(34, 197, 94, 0.8)' }}>er</span> Research into Public Records
          </h2>
        </div>
        
        {/* Example queries */}
        <div className="z-20 relative w-full max-w-3xl mx-auto px-4 mt-8">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {displayedExamples.map((exampleQuery, index) => (
              <button
                key={index}
                onClick={() => handleExampleClick(exampleQuery)}
                className="bg-white/10 hover:bg-white/20 text-white text-sm p-3 rounded-lg border border-white/20 transition-colors text-left hover:border-green-400/50"
              >
                {exampleQuery}
              </button>
            ))}
          </div>
        </div>
        
        {/* Search input */}
        <div className="z-20 relative w-full max-w-md mx-auto px-4 mt-8">
          <form onSubmit={handleSubmit} className="flex w-full items-end gap-2">
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask about public data..."
              className="min-h-10 bg-white/20 border-white/30 text-white placeholder:text-white/70 focus:border-green-400/70"
            />
            <Button 
              type="submit"
              className="bg-green-500/80 hover:bg-green-500/90 text-white h-10"
              disabled={!query.trim()}
            >
              Search
            </Button>
          </form>
        </div>
        
        {/* Add footer with X logo */}
        <div className="absolute bottom-4 w-full flex justify-center z-20">
          <a 
            href="https://x.com/askwithcrystal" 
            target="_blank" 
            rel="noopener noreferrer"
            className="p-2 bg-white/10 hover:bg-white/20 rounded-full transition-colors"
            aria-label="Follow us on X"
          >
            <img 
              src="/images/xlogo.png" 
              alt="X logo" 
              className="h-5 w-5" 
              style={{ filter: "brightness(0) invert(1)" }}
            />
          </a>
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