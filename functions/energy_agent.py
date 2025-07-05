"""
Energy Agent using PydanticAI for Mid-C Market Analysis and Infrastructure Data
"""

from dotenv import load_dotenv
load_dotenv()
import json
import logging
import os
import re
from typing import Dict, Any, List, Optional, Union
from datetime import datetime, timedelta

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from helpers.db_utils import execute_query, get_connection_pool, check_usage_limit
import requests
import traceback
import psycopg2

# Configure logging
logger = logging.getLogger(__name__)

GOOGLE_GEOCODING_API_KEY = os.getenv("GOOGLE_GEOCODING_API_KEY")

todays_date = str(datetime.now().date())
print(todays_date)

def geocode_location_google(location: str) -> Optional[Dict[str, float]]:
    """Geocode a location string to a GeoJSON Point using Google Geocoding API."""
    if not GOOGLE_GEOCODING_API_KEY:
        print("[GEOCODE] No Google Geocoding API key set.")
        return None
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": location, "key": GOOGLE_GEOCODING_API_KEY}
    try:
        resp = requests.get(url, params=params, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == "OK" and data.get("results"):
            loc = data["results"][0]["geometry"]["location"]
            lat, lon = loc["lat"], loc["lng"]
            print(f"[GEOCODE] '{location}' -> lat={lat}, lon={lon}")
            return {"lat": lat, "lon": lon}
        else:
            print(f"[GEOCODE] No results for '{location}': {data.get('status')}")
    except Exception as e:
        print(f"[GEOCODE] Exception for '{location}': {e}")
    return None

class ConversationState(BaseModel):
    """State to maintain conversation context"""
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    previous_queries: List[str] = Field(default_factory=list)
    context: Dict[str, Any] = Field(default_factory=dict)

class EnergyAgentTools:
    """Tools for the energy agent to access infrastructure data"""
    
    @staticmethod
    def check_sql_safety(query: str) -> bool:
        """Check if a query contains unsafe SQL operations"""
        unsafe_patterns = [
            r'\bCREATE\b', r'\bDROP\b', r'\bALTER\b', r'\bINSERT\b', 
            r'\bUPDATE\b', r'\bDELETE\b', r'\bTRUNCATE\b', r'\bEXEC\b',
            r'\bMERGE\b', r'\bREPLACE\b', r'\bGRANT\b', r'\bREVOKE\b',
            r'\bSET\b', r'\bDECLARE\b', r'--', r'/\*', r'\*/', r';.*'
        ]
        
        query_upper = query.upper()
        for pattern in unsafe_patterns:
            if re.search(pattern, query_upper, re.IGNORECASE):
                return False
        return True
    
    @staticmethod
    def get_ttc_flowgate_data(flowgate_name: Optional[str] = None, limit: int = 100) -> Dict[str, Any]:
        """
        Get Total Transfer Capability (TTC) flowgate data for transmission analysis.
        Uses: fact_ttc_hourly (datetime_utc, flowgate_id, value_mw), dim_flowgate (flowgate_id, flowgate_code)
        """
        try:
            query = """
            SELECT
                t.datetime_utc as timestamp,
                d.flowgate_code,
                t.value_mw
            FROM fact_ttc_hourly t
            JOIN dim_flowgate d ON t.flowgate_id = d.flowgate_id
            WHERE d.is_active = TRUE
            """
            params = []
            
            if flowgate_name:
                query += " AND d.flowgate_code ILIKE %s"
                params.append(f"%{flowgate_name}%")
            
            query += f" ORDER BY t.datetime_utc DESC LIMIT {limit}"
            print(f"[SQL QUERY] {query} | params={params}")
            results = execute_query(query, params)
            print(f"[SQL RESULT] rows={len(results)} preview={results[:2]}")
            return {
                "success": True,
                "data": results,
                "count": len(results),
                "description": "Total Transfer Capability (TTC) for specified flowgates"
            }
                
        except Exception as e:
            logger.error(f"Error fetching TTC flowgate data: {e}")
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def get_power_infrastructure(region: Optional[str] = None, limit: int = 1000, location: Optional[str] = None, radius_km: int = 50) -> Dict[str, Any]:
        """
        Get power infrastructure data (transmission lines, substations, etc).
        Uses: power_infra (gid, openinfra_name, voltage, power, operator, geom)
        """
        try:
            query = """
            SELECT 
                gid, openinfra_name, voltage, power, operator,
                ST_AsGeoJSON(geom) as geometry
            FROM power_infra
            WHERE 1=1
            """
            params = []
            if location:
                coords = geocode_location_google(location)
                if coords:
                    lat, lon = coords["lat"], coords["lon"]
                    query += " AND ST_DWithin(geom::geography, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s)"
                    params.extend([lon, lat, radius_km * 1000])
                else:
                    return {"success": False, "error": f"Could not geocode location: {location}"}
            elif region:
                query += " AND operator ILIKE %s"
                params.append(f"%{region}%")
            query += f" ORDER BY voltage DESC NULLS LAST LIMIT {limit}"
            print(f"[SQL QUERY] {query} | params={params}")
            results = execute_query(query, params)
            print(f"[SQL RESULT] rows={len(results)} preview={results[:2]}")
            return {
                "success": True,
                "data": results,
                "count": len(results),
                "description": "Power infrastructure (transmission lines, substations, etc)"
            }
        except Exception as e:
            logger.error(f"Error fetching power infrastructure: {e}")
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def get_power_generators(region: Optional[str] = None, fuel_type: Optional[str] = None, limit: int = 1000, location: Optional[str] = None, radius_km: int = 50) -> Dict[str, Any]:
        """
        Get power generator data.
        Uses: dim_generators (generator_id, plant_id, generator_source, generator_method, operator, manufacturer, geom, start_date, size)
        """
        try:
            query = """
            SELECT 
                generator_id, plant_id, generator_source, generator_method, operator, manufacturer,
                size, start_date, ST_AsGeoJSON(geom) as geometry
            FROM dim_generators
            WHERE 1=1
            """
            params = []
            if location:
                coords = geocode_location_google(location)
                if coords:
                    lat, lon = coords["lat"], coords["lon"]
                    query += " AND ST_DWithin(geom::geography, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s)"
                    params.extend([lon, lat, radius_km * 1000])
                else:
                    return {"success": False, "error": f"Could not geocode location: {location}"}
            elif region:
                query += " AND operator ILIKE %s"
                params.append(f"%{region}%")
            if fuel_type:
                query += " AND generator_source ILIKE %s"
                params.append(f"%{fuel_type}%")
            query += f" ORDER BY size DESC NULLS LAST LIMIT {limit}"
            print(f"[SQL QUERY] {query} | params={params}")
            results = execute_query(query, params)
            print(f"[SQL RESULT] rows={len(results)} preview={results[:2]}")
            return {
                "success": True,
                "data": results,
                "count": len(results),
                "description": "Power generators (units, type, operator, size, etc)"
            }
        except Exception as e:
            logger.error(f"Error fetching power generators: {e}")
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def get_power_plants(region: Optional[str] = None, fuel_type: Optional[str] = None, limit: int = 500, location: Optional[str] = None, radius_km: int = 50) -> Dict[str, Any]:
        """
        Get power plant data.
        Uses: dim_plants (plant_id, name, operator, plant_source, output_electricity, start_date, geom)
        """
        try:
            query = """
            SELECT 
                plant_id, name, operator, plant_source, output_electricity, start_date,
                ST_AsGeoJSON(geom) as geometry
            FROM dim_plants
            WHERE 1=1
            """
            params = []
            if location:
                coords = geocode_location_google(location)
                if coords:
                    lat, lon = coords["lat"], coords["lon"]
                    query += " AND ST_DWithin(geom::geography, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s)"
                    params.extend([lon, lat, radius_km * 1000])
                else:
                    return {"success": False, "error": f"Could not geocode location: {location}"}
            elif region:
                query += " AND operator ILIKE %s"
                params.append(f"%{region}%")
            if fuel_type:
                query += " AND plant_source ILIKE %s"
                params.append(f"%{fuel_type}%")
            query += f" ORDER BY output_electricity DESC NULLS LAST LIMIT {limit}"
            print(f"[SQL QUERY] {query} | params={params}")
            results = execute_query(query, params)
            print(f"[SQL RESULT] rows={len(results)} preview={results[:2]}")
            return {
                "success": True,
                "data": results,
                "count": len(results),
                "description": "Power plants (name, operator, fuel, capacity, location)"
            }
        except Exception as e:
            logger.error(f"Error fetching power plants: {e}")
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def get_dam_locations(region: Optional[str] = None, limit: int = 500, location: Optional[str] = None, radius_km: int = 50) -> Dict[str, Any]:
        """
        Get dam location data.
        Uses: dim_dam (dam_id, dam_name, latitude, longitude, state, county, year_completed, capacity_mw, storage_max_acft)
        """
        try:
            query = """
            SELECT 
                dam_id, dam_name, latitude, longitude, state, county, year_completed, capacity_mw, storage_max_acft,
                ST_SetSRID(ST_MakePoint(longitude, latitude), 4326) as geometry
            FROM dim_dam
            WHERE 1=1
            """
            params = []
            if location:
                coords = geocode_location_google(location)
                if coords:
                    lat, lon = coords["lat"], coords["lon"]
                    query += " AND ST_DWithin(ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s)"
                    params.extend([lon, lat, radius_km * 1000])
                else:
                    return {"success": False, "error": f"Could not geocode location: {location}"}
            elif region:
                query += " AND (state ILIKE %s OR county ILIKE %s)"
                params.extend([f"%{region}%", f"%{region}%"])
            query += f" ORDER BY capacity_mw DESC NULLS LAST LIMIT {limit}"
            print(f"[SQL QUERY] {query} | params={params}")
            results = execute_query(query, params)
            print(f"[SQL RESULT] rows={len(results)} preview={results[:2]}")
            return {
                "success": True,
                "data": results,
                "count": len(results),
                "description": "Dam locations and storage/capacity data"
            }
        except Exception as e:
            logger.error(f"Error fetching dam locations: {e}")
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def get_bpa_generation_mix(days_back: int = 1) -> Dict[str, Any]:
        """
        Get latest BPA generation mix data.
        Uses: fact_bpa_generation (timestamp_utc, metric_id, value_mw), dim_metric (metric_id, description)
        """
        try:
            query = """
            SELECT
                f.timestamp_utc as timestamp,
                m.description as generation_type,
                f.value_mw as generation_mw
            FROM fact_bpa_generation f
            JOIN dim_metric m ON f.metric_id = m.metric_id
            WHERE f.timestamp_utc >= NOW() - INTERVAL '%s days'
            ORDER BY f.timestamp_utc DESC, f.value_mw DESC
            """
            
            print(f"[SQL QUERY] {query} | params={[days_back]}")
            results = execute_query(query, [days_back])
            print(f"[SQL RESULT] rows={len(results)} preview={results[:2]}")
            return {
                "success": True,
                "data": results,
                "count": len(results),
                "description": f"BPA generation mix data (by type and MW) for the last {days_back} days"
            }
                
        except Exception as e:
            logger.error(f"Error fetching BPA generation mix: {e}")
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def get_snotel_stations(location: Optional[str] = None, limit: int = 100, radius_km: int = 50) -> Dict[str, Any]:
        """
        Get SNOTEL station data using spatial query if location is provided.
        Uses: dim_station (station_id, name, station_triplet, state_code, county_name, latitude, longitude, elevation, begin_date, is_active)
        """
        try:
            query = """
            SELECT 
                station_id, name, station_triplet, state_code, county_name,
                latitude, longitude, elevation, begin_date, is_active
            FROM dim_station
            WHERE 1=1
            """
            params = []
            if location:
                coords = geocode_location_google(location)
                if coords:
                    lat, lon = coords["lat"], coords["lon"]
                    query += " AND ST_DWithin(ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s)"
                    params.extend([lon, lat, radius_km * 1000])
                else:
                    return {"success": False, "error": f"Could not geocode location: {location}"}
            query += f" ORDER BY elevation DESC LIMIT {limit}"
            print(f"[SQL QUERY] {query} | params={params}")
            results = execute_query(query, params)
            print(f"[SQL RESULT] rows={len(results)} preview={results[:2]}")
            return {
                "success": True,
                "data": results,
                "count": len(results),
                "description": "SNOTEL weather and snow monitoring stations"
            }
        except Exception as e:
            logger.error(f"Error fetching SNOTEL stations: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def get_icr_data(state: Optional[str] = None, status: Optional[str] = None, cluster: Optional[str] = None, limit: int = 100) -> Dict[str, Any]:
        """Get Interconnection Request (ICR) data from fact_icr with optional filters"""
        try:
            query = """
            SELECT 
                request_number, request_date, project_name, requestor, comments, 
                point_of_interconnection, status, state, county, connection_type, 
                requested_in_service_date, agreed_to, max_summer_mw, max_winter_mw, 
                interconnection_type, generator_type_1, fuel_source_1, mw1, 
                generator_type_2, fuel_source_2, mw2, generator_type_3, fuel_source_3, mw3, 
                mw_total, cluster, related_transmission_request, reason_not_completed, 
                feasibility_study, phase1_cluster_study, system_impact_study, phase2_cluster_study, 
                facilities_study, surplus_interconnection_service_request, repower
            FROM fact_icr
            WHERE 1=1
            """
            params = []
            if state:
                query += " AND state ILIKE %s"
                params.append(state)
            if status:
                query += " AND status ILIKE %s"
                params.append(status)
            if cluster:
                query += " AND cluster ILIKE %s"
                params.append(cluster)
            query += f" ORDER BY request_date DESC LIMIT {limit}"
            print(f"[SQL QUERY] {query} | params={params}")
            results = execute_query(query, params)
            print(f"[SQL RESULT] rows={len(results)} preview={results[:2]}")
            return {
                "success": True,
                "data": results,
                "count": len(results),
                "description": "Interconnection Request (ICR) data from fact_icr"
            }
        except Exception as e:
            logger.error(f"Error fetching ICR data: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def get_dam_id_by_location(location: str, max_distance_km: int = 20) -> Optional[int]:
        """Geocode a location and find the closest dam_id in dim_dam within max_distance_km."""
        coords = geocode_location_google(location)
        if not coords:
            print(f"[DAM_ID] Could not geocode location: {location}")
            return None
        lat, lon = coords["lat"], coords["lon"]
        query = '''
            SELECT dam_id, dam_name, latitude, longitude,
                   ST_Distance(
                       ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography,
                       ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                   ) as distance_m
            FROM dim_dam
            ORDER BY distance_m ASC
            LIMIT 1;
        '''
        params = [lon, lat]
        print(f"[SQL QUERY] {query} | params={params}")
        results = execute_query(query, params)
        print(f"[SQL RESULT] rows={len(results)} preview={results[:2]}")
        if results and results[0]["distance_m"] <= max_distance_km * 1000:
            print(f"[DAM_ID] Closest dam_id to '{location}' is {results[0]['dam_id']} at {results[0]['distance_m']} meters")
            return results[0]["dam_id"]
        print(f"[DAM_ID] No dam found within {max_distance_km} km of '{location}'")
        return None

    @staticmethod
    def get_dam_inflow(dam_id: int, metric_id: Optional[int] = None, start_time: Optional[str] = None, end_time: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """Query fact_dam_ops for inflow (or other) data for a dam_id."""
        query = '''
            SELECT ts_utc, dam_id, metric_id, value_num, quality, source_id
            FROM fact_dam_ops
            WHERE dam_id = %s
        '''
        params = [dam_id]
        if metric_id:
            query += ' AND metric_id = %s'
            params.append(metric_id)
        if start_time:
            query += ' AND ts_utc >= %s'
            params.append(start_time)
        if end_time:
            query += ' AND ts_utc <= %s'
            params.append(end_time)
        query += ' ORDER BY ts_utc DESC LIMIT %s'
        params.append(limit)
        print(f"[SQL QUERY] {query} | params={params}")
        results = execute_query(query, params)
        print(f"[SQL RESULT] rows={len(results)} preview={results[:2]}")
        return results

# Create the PydanticAI agent
energy_agent = Agent(
    'openai:gpt-4o-mini',  # Using a cost-effective model
    deps_type=ConversationState,
    system_prompt=f"""Todays date is {todays_date}. You are an expert energy analyst specializing in the Mid-C (Mid-Columbia) electricity market and power infrastructure.\n\nYour role is to provide insights on:\n- Power generation and transmission infrastructure\n- Energy market analysis and forecasting\n- Dam operations and hydroelectric generation\n- Transmission capacity and flowgate constraints\n- Renewable energy integration\n- Grid reliability and operational challenges\n\nIMPORTANT SECURITY RULES:\n- You can ONLY perform READ operations on data\n- You must REFUSE any requests to modify, create, update, or delete data\n- You cannot execute any SQL statements containing CREATE, UPDATE, DELETE, INSERT, ALTER, DROP, or similar modification commands\n- You are strictly read-only and for analysis purposes only\n\nWhen users ask about data modifications, politely explain that you can only provide analysis and insights based on existing data.\n\nYou have access to real-time and historical data on:\n- Power infrastructure (transmission lines, substations)\n- Power generators and plants\n- Dam locations and reservoir data\n- BPA generation mix and market data\n- SNOTEL weather stations for hydroelectric forecasting\n- TTC flowgate transmission capacity data\n- Interconnection Requests (ICR) from fact_icr (project, status, MW, cluster, etc.)\n\nREFERENCE/LEGEND TABLES:\n- All fact tables are linked to dim_ tables (e.g., dim_dam, dim_flowgate, dim_generators, dim_icr, dim_metric, dim_model, dim_plants, dim_segment, dim_source, dim_station, dim_substation, dim_transmission) which provide lookup/legend information for codes, names, units, and relationships.\n- Use these dim_ tables to explain or clarify any codes, IDs, or categorical values in the fact tables.\n\nProvide detailed, technical analysis while being accessible to both technical and non-technical audiences. Always cite the data sources you use and explain the limitations of your analysis.\n""",
    retries=2,
)

@energy_agent.tool
async def get_ttc_flowgate_data_tool(ctx: RunContext[ConversationState], flowgate_name: Optional[str] = None, limit: int = 100) -> Dict[str, Any]:
    """Get TTC flowgate transmission capacity data for market analysis"""
    print(f"[TOOL CALL] get_ttc_flowgate_data_tool(flowgate_name={flowgate_name}, limit={limit})")
    # Check for SQL injection attempts
    if flowgate_name and not EnergyAgentTools.check_sql_safety(flowgate_name):
        return {"success": False, "error": "Invalid input detected. Only read operations are allowed."}
    
    result = EnergyAgentTools.get_ttc_flowgate_data(flowgate_name, limit)
    
    # Update conversation context
    ctx.deps.context['last_query'] = 'ttc_flowgate_data'
    ctx.deps.previous_queries.append('ttc_flowgate_data')
    
    return result

@energy_agent.tool
async def get_power_infrastructure_tool(ctx: RunContext[ConversationState], region: Optional[str] = None, limit: int = 1000, location: Optional[str] = None, radius_km: int = 50) -> Dict[str, Any]:
    """Get power infrastructure data including transmission lines and substations"""
    print(f"[TOOL CALL] get_power_infrastructure_tool(region={region}, limit={limit}, location={location}, radius_km={radius_km})")
    # If region/location is 'Mid-C' (case-insensitive, with or without dashes/spaces), treat as None
    def is_midc(val):
        return val and val.strip().replace('-', '').replace(' ', '').lower() == 'midc'
    if is_midc(region):
        region = None
    if is_midc(location):
        location = None
    # Simplified: If location is None but region is provided, try to geocode region as a location
    if location is None and region:
        test_coords = geocode_location_google(region)
        if test_coords:
            location = region
            region = None
    if location and not EnergyAgentTools.check_sql_safety(location):
        return {"success": False, "error": "Invalid input detected. Only read operations are allowed."}
    if region and not EnergyAgentTools.check_sql_safety(region):
        return {"success": False, "error": "Invalid input detected. Only read operations are allowed."}
    
    result = EnergyAgentTools.get_power_infrastructure(region, limit, location, radius_km)
    
    ctx.deps.context['last_query'] = 'power_infrastructure'
    ctx.deps.previous_queries.append('power_infrastructure')
    
    return result

@energy_agent.tool
async def get_power_generators_tool(ctx: RunContext[ConversationState], region: Optional[str] = None, fuel_type: Optional[str] = None, limit: int = 1000, location: Optional[str] = None, radius_km: int = 50) -> Dict[str, Any]:
    """Get power generator data filtered by region and fuel type"""
    print(f"[TOOL CALL] get_power_generators_tool(region={region}, fuel_type={fuel_type}, limit={limit}, location={location}, radius_km={radius_km})")
    def is_midc(val):
        return val and val.strip().replace('-', '').replace(' ', '').lower() == 'midc'
    if is_midc(region):
        region = None
    if is_midc(location):
        location = None
    if location is None and region:
        test_coords = geocode_location_google(region)
        if test_coords:
            location = region
            region = None
    if location and not EnergyAgentTools.check_sql_safety(location):
        return {"success": False, "error": "Invalid input detected. Only read operations are allowed."}
    if region and not EnergyAgentTools.check_sql_safety(region):
        return {"success": False, "error": "Invalid input detected. Only read operations are allowed."}
    if fuel_type and not EnergyAgentTools.check_sql_safety(fuel_type):
        return {"success": False, "error": "Invalid input detected. Only read operations are allowed."}
    
    result = EnergyAgentTools.get_power_generators(region, fuel_type, limit, location, radius_km)
    
    ctx.deps.context['last_query'] = 'power_generators'
    ctx.deps.previous_queries.append('power_generators')
    
    return result

@energy_agent.tool
async def get_power_plants_tool(ctx: RunContext[ConversationState], region: Optional[str] = None, fuel_type: Optional[str] = None, limit: int = 500, location: Optional[str] = None, radius_km: int = 50) -> Dict[str, Any]:
    """Get power plant data with aggregated capacity information"""
    print(f"[TOOL CALL] get_power_plants_tool(region={region}, fuel_type={fuel_type}, limit={limit}, location={location}, radius_km={radius_km})")
    def is_midc(val):
        return val and val.strip().replace('-', '').replace(' ', '').lower() == 'midc'
    if is_midc(region):
        region = None
    if is_midc(location):
        location = None
    if location is None and region:
        test_coords = geocode_location_google(region)
        if test_coords:
            location = region
            region = None
    if location and not EnergyAgentTools.check_sql_safety(location):
        return {"success": False, "error": "Invalid input detected. Only read operations are allowed."}
    if region and not EnergyAgentTools.check_sql_safety(region):
        return {"success": False, "error": "Invalid input detected. Only read operations are allowed."}
    if fuel_type and not EnergyAgentTools.check_sql_safety(fuel_type):
        return {"success": False, "error": "Invalid input detected. Only read operations are allowed."}
    
    result = EnergyAgentTools.get_power_plants(region, fuel_type, limit, location, radius_km)
    
    ctx.deps.context['last_query'] = 'power_plants'
    ctx.deps.previous_queries.append('power_plants')
    
    return result

@energy_agent.tool
async def get_dam_locations_tool(ctx: RunContext[ConversationState], region: Optional[str] = None, limit: int = 500, location: Optional[str] = None, radius_km: int = 50) -> Dict[str, Any]:
    """Get dam location and reservoir capacity data"""
    print(f"[TOOL CALL] get_dam_locations_tool(region={region}, limit={limit}, location={location}, radius_km={radius_km})")
    def is_midc(val):
        return val and val.strip().replace('-', '').replace(' ', '').lower() == 'midc'
    if is_midc(region):
        region = None
    if is_midc(location):
        location = None
    if location is None and region:
        test_coords = geocode_location_google(region)
        if test_coords:
            location = region
            region = None
    if location and not EnergyAgentTools.check_sql_safety(location):
        return {"success": False, "error": "Invalid input detected. Only read operations are allowed."}
    if region and not EnergyAgentTools.check_sql_safety(region):
        return {"success": False, "error": "Invalid input detected. Only read operations are allowed."}
    
    result = EnergyAgentTools.get_dam_locations(region, limit, location, radius_km)
    
    ctx.deps.context['last_query'] = 'dam_locations'
    ctx.deps.previous_queries.append('dam_locations')
    
    return result

@energy_agent.tool
async def get_bpa_generation_mix_tool(ctx: RunContext[ConversationState], days_back: int = 1) -> Dict[str, Any]:
    """Get BPA generation mix data for market analysis"""
    print(f"[TOOL CALL] get_bpa_generation_mix_tool(days_back={days_back})")
    if days_back < 1 or days_back > 365:
        return {"success": False, "error": "Days back must be between 1 and 365"}
    
    result = EnergyAgentTools.get_bpa_generation_mix(days_back)
    
    ctx.deps.context['last_query'] = 'bpa_generation_mix'
    ctx.deps.previous_queries.append('bpa_generation_mix')
    
    return result

@energy_agent.tool
async def get_snotel_stations_tool(ctx: RunContext[ConversationState], location: Optional[str] = None, limit: int = 100, radius_km: int = 50) -> Dict[str, Any]:
    """Get SNOTEL weather station data for hydroelectric forecasting (spatial only)"""
    print(f"[TOOL CALL] get_snotel_stations_tool(location={location}, limit={limit}, radius_km={radius_km})")
    if location and not EnergyAgentTools.check_sql_safety(location):
        return {"success": False, "error": "Invalid input detected. Only read operations are allowed."}
    result = EnergyAgentTools.get_snotel_stations(location, limit, radius_km)
    ctx.deps.context['last_query'] = 'snotel_stations'
    ctx.deps.previous_queries.append('snotel_stations')
    return result

@energy_agent.tool
async def get_icr_data_tool(ctx: RunContext[ConversationState], state: Optional[str] = None, status: Optional[str] = None, cluster: Optional[str] = None, limit: int = 100) -> Dict[str, Any]:
    """Get Interconnection Request (ICR) data from fact_icr with optional filters for state, status, and cluster."""
    print(f"[TOOL CALL] get_icr_data_tool(state={state}, status={status}, cluster={cluster}, limit={limit})")
    if state and not EnergyAgentTools.check_sql_safety(state):
        return {"success": False, "error": "Invalid input detected. Only read operations are allowed."}
    if status and not EnergyAgentTools.check_sql_safety(status):
        return {"success": False, "error": "Invalid input detected. Only read operations are allowed."}
    if cluster and not EnergyAgentTools.check_sql_safety(cluster):
        return {"success": False, "error": "Invalid input detected. Only read operations are allowed."}
    result = EnergyAgentTools.get_icr_data(state, status, cluster, limit)
    ctx.deps.context['last_query'] = 'icr_data'
    ctx.deps.previous_queries.append('icr_data')
    return result

@energy_agent.tool
async def analyze_conversation_context(ctx: RunContext[ConversationState]) -> Dict[str, Any]:
    """Analyze the conversation context and previous queries"""
    return {
        "success": True,
        "data": {
            "session_id": ctx.deps.session_id,
            "previous_queries": ctx.deps.previous_queries[-5:],  # Last 5 queries
            "context": ctx.deps.context,
            "query_count": len(ctx.deps.previous_queries)
        },
        "description": "Conversation context and history"
    }

@energy_agent.tool
async def get_dam_inflow_tool(ctx: RunContext[ConversationState], location: str, metric_id: Optional[int] = None, start_time: Optional[str] = None, end_time: Optional[str] = None, limit: int = 100) -> Dict[str, Any]:
    """Get dam inflow (or other metric) data for a dam by name/location using fact_dam_ops."""
    print(f"[TOOL CALL] get_dam_inflow_tool(location={location}, metric_id={metric_id}, start_time={start_time}, end_time={end_time}, limit={limit})")
    if not location or not EnergyAgentTools.check_sql_safety(location):
        return {"success": False, "error": "Invalid or missing location. Only read operations are allowed."}
    dam_id = EnergyAgentTools.get_dam_id_by_location(location)
    if not dam_id:
        return {"success": False, "error": f"Could not find a dam near '{location}'."}
    results = EnergyAgentTools.get_dam_inflow(dam_id, metric_id, start_time, end_time, limit)
    return {
        "success": True,
        "dam_id": dam_id,
        "data": results,
        "count": len(results),
        "description": f"Inflow/metric data for dam_id {dam_id} near '{location}'"
    }

async def run_energy_agent(message: str, session_id: str = None, user_id: str = None) -> Dict[str, Any]:
    """Run the energy agent with a user message"""
    try:
        # Check for SQL modification attempts in the message
        if not EnergyAgentTools.check_sql_safety(message):
            return {
                "success": False,
                "error": "I can only provide read-only analysis and insights. I cannot perform any data modifications, creation, updates, or deletions.",
                "response": "I'm designed to be a read-only energy analyst. I can help you analyze existing data and provide insights, but I cannot modify any data. Please rephrase your question to focus on analysis or information retrieval."
            }
        
        # Initialize conversation state
        state = ConversationState(
            session_id=session_id or f"session_{datetime.now().timestamp()}",
            user_id=user_id,
            context={"today": todays_date}
        )
        
        # Run the agent
        result = await energy_agent.run(message, deps=state)
        
        return {
            "success": True,
            "response": result.output,
            "session_id": state.session_id,
            "message_count": len(state.previous_queries)
        }
        
    except Exception as e:
        logger.error(f"Error running energy agent: {e}")
        logger.error(traceback.format_exc())
        return {
            "success": False,
            "error": str(e),
            "response": "I apologize, but I encountered an error processing your request. Please try again or rephrase your question."
        }

def index_all_tables_and_preview():
    """Print all tables, their schemas, and top 5 rows for each."""
    from helpers.db_utils import get_connection_pool
    pool = get_connection_pool()
    conn = pool.getconn()
    try:
        with conn.cursor() as cursor:
            print("\n--- DATABASE TABLES AND SCHEMAS ---\n")
            # Get all user tables
            cursor.execute("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
                ORDER BY table_name;
            """)
            tables = [row[0] for row in cursor.fetchall()]
            for table in tables:
                print(f"\nTable: {table}")
                # Get columns
                cursor.execute("""
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_name = %s
                    ORDER BY ordinal_position;
                """, (table,))
                columns = cursor.fetchall()
                print("Columns:")
                for col, dtype in columns:
                    print(f"  - {col}: {dtype}")
                # Get top 5 rows
                try:
                    cursor.execute(f'SELECT * FROM "{table}" LIMIT 5;')
                    rows = cursor.fetchall()
                    if rows:
                        print("Top 5 rows:")
                        for row in rows:
                            print(row)
                    else:
                        print("(No rows)")
                except Exception as e:
                    print(f"Could not fetch rows: {e}")
    finally:
        pool.putconn(conn)

if __name__ == "__main__":
    import asyncio
    import sys
    print("\nEnergy Agent Interactive Terminal\nType 'exit' or 'quit' to end the session.\n")
    os.environ["FUNCTIONS_EMULATOR"] = "True"
    session_id = f"local_{datetime.now().timestamp()}"
    user_id = "local_user"
    if '--index-db' in sys.argv:
        index_all_tables_and_preview()
        sys.exit(0)
    while True:
        try:
            message = input("You: ").strip()
            if message.lower() in {"exit", "quit"}:
                print("Exiting Energy Agent.")
                break
            if not message:
                continue
            result = asyncio.run(run_energy_agent(message, session_id=session_id, user_id=user_id))
            if result.get("success"):
                print("Agent:", json.dumps(result.get("response"), indent=2, default=str))
            else:
                print("Agent (error):", result.get("error"))
        except (KeyboardInterrupt, EOFError):
            print("\nExiting Energy Agent.")
            break
        except Exception as e:
            print(f"Agent (exception): {e}")