"""
Energy Agent powered by the generic SQLAgent.
This file defines the specific tools, prompts, and configurations for the energy domain.
"""
from dotenv import load_dotenv
load_dotenv()
import json
import logging
import os
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import asyncio
import requests

# --- Local Dependencies ---
from sql_agent import SQLAgent, ToolOrchestrator, _build_where_clause, is_safe_identifier

# --- Configuration & Utilities ---
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

GOOGLE_GEOCODING_API_KEY = os.getenv("GOOGLE_GEOCODING_API_KEY")
LLM_MODEL = "gpt-4o-mini"
todays_date = str(datetime.now().date())


def geocode_location_google(location: str) -> Optional[Dict[str, float]]:
    """Geocodes a location string using the Google Geocoding API."""
    if not GOOGLE_GEOCODING_API_KEY:
        return None
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": location, "key": GOOGLE_GEOCODING_API_KEY}
    try:
        resp = requests.get(url, params=params, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == "OK" and data.get("results"):
            return data["results"][0]["geometry"]["location"]
    except Exception as e:
        logger.error(f"[GEOCODE] Exception for '{location}': {e}")
    return None


class EnergyAgentTools:
    """
    Container for all tools available to the Energy Agent.
    Each static method is a tool the agent can call.
    """
    orchestrator = ToolOrchestrator()

    @staticmethod
    async def get_all_metrics() -> Dict[str, Any]:
        """
        Retrieves the complete legend of all available metrics from the 'dim_metric' table.
        This is a crucial discovery tool to understand what `metric_id` corresponds to a
        human-readable description (e.g., 'inflow', 'outflow', 'generation_hydro').
        """
        query = "SELECT metric_id, code, description, units FROM dim_metric ORDER BY metric_id;"
        return await EnergyAgentTools.orchestrator.execute_sql(query, [])

    @staticmethod
    async def get_unique_column_values(table_name: str, column_name: str, limit: int = 20) -> Dict[str, Any]:
        """
        Retrieves a list of unique, non-null values from a specific column in a given table.
        This is a critical discovery tool. When a function like `get_icr_data` returns an error
        that a filter is required, you must use this to find valid filter values.
        The correct workflow is:
        1. Call `get_table_schema` for the target table (e.g., 'fact_icr') to find a relevant column (e.g., 'status').
        2. Call this tool (`get_unique_column_values`) to get a list of possible values for that column.
        3. Re-call the original function with a `filters_include` using one of the discovered values.
        """
        if not is_safe_identifier(table_name) or not is_safe_identifier(column_name):
            return {"success": False, "error": "Invalid table or column name."}
        
        query = f"SELECT DISTINCT {column_name} FROM {table_name} WHERE {column_name} IS NOT NULL ORDER BY 1 LIMIT %s;"
        result = await EnergyAgentTools.orchestrator.execute_sql(query, [limit])

        if result.get("success"):
            flat_list = [row[column_name] for row in result.get("data", []) if column_name in row]
            return {"success": True, "data": flat_list}
        else:
            return result

    @staticmethod
    async def get_table_schema(table_name: str) -> Dict[str, Any]:
        """Gets the schema (column names and data types) for a given table."""
        if not is_safe_identifier(table_name):
            return {"success": False, "error": "Invalid table name."}
        query = "SELECT column_name, data_type FROM information_schema.columns WHERE table_schema = 'public' AND table_name = %s ORDER BY ordinal_position;"
        return await EnergyAgentTools.orchestrator.execute_sql(query, [table_name])

    @staticmethod
    async def get_icr_data(filters_include: Optional[Dict[str, List[str]]] = None, filters_exclude: Optional[Dict[str, List[str]]] = None, sort_column: Optional[str] = 'request_date', sort_order: Optional[str] = 'DESC', limit: Optional[int] = None) -> Dict[str, Any]:
        """Retrieves Interconnection Request (ICR) data, which must be filtered."""
        base_query = "SELECT request_number, project_name, status, state, county, max_summer_mw, fuel_source_1, request_date FROM fact_icr"
        where_clause, params = _build_where_clause(filters_include, filters_exclude)
        
        if not where_clause:
            return {"success": False, "error": "A filter must be provided for ICR data. Use `get_table_schema` and `get_unique_column_values` to find a valid filter."}
        
        safe_sort_order = "ASC" if str(sort_order).upper() == "ASC" else "DESC"
        safe_sort_column = sort_column if is_safe_identifier(sort_column) else 'request_date'
        
        if safe_sort_column not in base_query:
            base_query = base_query.replace(" FROM", f", {safe_sort_column} FROM")
            
        query = f"{base_query} {where_clause} ORDER BY {safe_sort_column} {safe_sort_order} NULLS LAST"
        if limit is not None:
            query += " LIMIT %s"
            params.append(limit)
        return await EnergyAgentTools.orchestrator.execute_sql(query, params)

    @staticmethod
    async def get_power_infrastructure(location: Optional[str] = None, radius_km: int = 50, filters_include: Optional[Dict[str, List[str]]] = None, limit: Optional[int] = None) -> Dict[str, Any]:
        """Retrieves data on power infrastructure like substations and transmission lines."""
        base_query = "SELECT gid, openinfra_name, voltage, power, operator, ST_AsGeoJSON(geom) as geometry FROM power_infra"
        where_parts, params = [], []
        if location:
            coords = geocode_location_google(location)
            if coords:
                where_parts.append("ST_DWithin(geom::geography, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s)")
                params.extend([coords["lng"], coords["lat"], radius_km * 1000])
        
        attr_clause, attr_params = _build_where_clause(filters_include)
        if attr_clause:
            where_parts.append(attr_clause.replace("WHERE ", ""))
            params.extend(attr_params)
            
        query = f"{base_query} WHERE {' AND '.join(where_parts)}" if where_parts else base_query
        query += " ORDER BY voltage DESC NULLS LAST"
        if limit is not None:
            query += " LIMIT %s"
            params.append(limit)
        return await EnergyAgentTools.orchestrator.execute_sql(query, params)

    @staticmethod
    async def get_power_plants(location: Optional[str] = None, radius_km: int = 50, filters_include: Optional[Dict[str, List[str]]] = None, sort_column: Optional[str] = 'output_electricity', sort_order: Optional[str] = 'DESC', limit: Optional[int] = None) -> Dict[str, Any]:
        """Retrieves data on power plants."""
        base_query = "SELECT plant_id, name, operator, plant_source, output_electricity, start_date, ST_AsGeoJSON(geom) as geometry FROM dim_plants"
        where_parts, params = [], []
        if location:
            coords = geocode_location_google(location)
            if coords:
                where_parts.append("ST_DWithin(geom::geography, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s)")
                params.extend([coords["lng"], coords["lat"], radius_km * 1000])

        attr_clause, attr_params = _build_where_clause(filters_include)
        if attr_clause:
            where_parts.append(attr_clause.replace("WHERE ", ""))
            params.extend(attr_params)

        where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        safe_sort_order = "ASC" if str(sort_order).upper() == "ASC" else "DESC"
        safe_sort_column = sort_column if is_safe_identifier(sort_column) else 'output_electricity'
        query = f"{base_query} {where_clause} ORDER BY {safe_sort_column} {safe_sort_order} NULLS LAST"
        if limit is not None:
            query += " LIMIT %s"
            params.append(limit)
        return await EnergyAgentTools.orchestrator.execute_sql(query, params)

    @staticmethod
    async def get_power_generators(location: Optional[str] = None, radius_km: int = 50, filters_include: Optional[Dict[str, List[str]]] = None, sort_column: Optional[str] = 'size', sort_order: Optional[str] = 'DESC', limit: Optional[int] = None) -> Dict[str, Any]:
        """Retrieves data on individual power generators."""
        base_query = "SELECT generator_id, plant_id, generator_source, generator_method, operator, size, start_date, ST_AsGeoJSON(geom) as geometry FROM dim_generators"
        where_parts, params = [], []
        if location:
            coords = geocode_location_google(location)
            if coords:
                where_parts.append("ST_DWithin(geom::geography, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s)")
                params.extend([coords["lng"], coords["lat"], radius_km * 1000])

        attr_clause, attr_params = _build_where_clause(filters_include)
        if attr_clause:
            where_parts.append(attr_clause.replace("WHERE ", ""))
            params.extend(attr_params)

        where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        safe_sort_order = "ASC" if str(sort_order).upper() == "ASC" else "DESC"
        safe_sort_column = sort_column if is_safe_identifier(sort_column) else 'size'
        query = f"{base_query} {where_clause} ORDER BY {safe_sort_column} {safe_sort_order} NULLS LAST"
        if limit is not None:
            query += " LIMIT %s"
            params.append(limit)
        return await EnergyAgentTools.orchestrator.execute_sql(query, params)

    @staticmethod
    async def get_dam_locations(location: Optional[str] = None, radius_km: int = 50, filters_include: Optional[Dict[str, List[str]]] = None, sort_column: Optional[str] = 'capacity_mw', sort_order: Optional[str] = 'DESC', limit: Optional[int] = None) -> Dict[str, Any]:
        """Retrieves data for dams."""
        base_query = "SELECT dam_id, dam_name, latitude, longitude, state, county, year_completed, capacity_mw, storage_max_acft FROM dim_dam"
        where_parts, params = [], []
        if location:
            coords = geocode_location_google(location)
            if coords:
                where_parts.append("ST_DWithin(ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s)")
                params.extend([coords["lng"], coords["lat"], radius_km * 1000])

        attr_clause, attr_params = _build_where_clause(filters_include)
        if attr_clause:
            where_parts.append(attr_clause.replace("WHERE ", ""))
            params.extend(attr_params)

        where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        safe_sort_order = "ASC" if str(sort_order).upper() == "ASC" else "DESC"
        safe_sort_column = sort_column if is_safe_identifier(sort_column) else 'capacity_mw'
        query = f"{base_query} {where_clause} ORDER BY {safe_sort_column} {safe_sort_order} NULLS LAST"
        if limit is not None:
            query += " LIMIT %s"
            params.append(limit)
        return await EnergyAgentTools.orchestrator.execute_sql(query, params)

    @staticmethod
    async def get_snotel_stations(location: Optional[str] = None, radius_km: int = 50, filters_include: Optional[Dict[str, List[str]]] = None, limit: Optional[int] = None) -> Dict[str, Any]:
        """Retrieves data for SNOTEL weather stations."""
        base_query = "SELECT station_id, name, station_triplet, state_code, county_name, latitude, longitude, elevation FROM dim_station"
        where_parts, params = [], []
        if location:
            coords = geocode_location_google(location)
            if not coords:
                return {"success": False, "error": f"Could not geocode location: {location}"}
            where_parts.append("ST_DWithin(ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s)")
            params.extend([coords["lng"], coords["lat"], radius_km * 1000])

        attr_clause, attr_params = _build_where_clause(filters_include)
        if attr_clause:
            where_parts.append(attr_clause.replace("WHERE ", ""))
            params.extend(attr_params)

        where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        query = f"{base_query} {where_clause} ORDER BY elevation DESC NULLS LAST"
        if limit is not None:
            query += " LIMIT %s"
            params.append(limit)
        return await EnergyAgentTools.orchestrator.execute_sql(query, params)

    @staticmethod
    async def get_bpa_generation_mix(days_back: int = 2) -> Dict[str, Any]:
        """Retrieves the generation mix for the Bonneville Power Administration (BPA) for the last few days."""
        query = "SELECT f.timestamp_utc as timestamp, m.description as generation_type, f.value_mw as generation_mw FROM fact_bpa_generation f JOIN dim_metric m ON f.metric_id = m.metric_id WHERE f.timestamp_utc >= NOW() - INTERVAL '%s days' ORDER BY f.timestamp_utc DESC, generation_type ASC;"
        return await EnergyAgentTools.orchestrator.execute_sql(query, [days_back])

    @staticmethod
    async def get_dam_ops_data(filters_include: Optional[Dict[str, List[Any]]] = None, start_date: Optional[str] = None, end_date: Optional[str] = None, limit: Optional[int] = None) -> Dict[str, Any]:
        """Retrieves operational data for dams, like inflow, outflow, and elevation."""
        base_query = "SELECT ts_utc, dam_id, metric_id, value_num, quality FROM fact_dam_ops"
        where_clause, params = _build_where_clause(filters_include)
        date_clauses = []
        if start_date:
            date_clauses.append("ts_utc >= %s")
            params.append(start_date)
        if end_date:
            date_clauses.append("ts_utc <= %s")
            params.append(end_date)
        if date_clauses:
            full_date_clause = " AND ".join(date_clauses)
            where_clause += f" AND {full_date_clause}" if where_clause else f"WHERE {full_date_clause}"

        query = f"{base_query} {where_clause} ORDER BY ts_utc DESC"
        if limit is not None:
            query += " LIMIT %s"
            params.append(limit)
        return await EnergyAgentTools.orchestrator.execute_sql(query, params)

SYSTEM_PROMPT = """You are an expert, autonomous energy market analyst. Your goal is to answer user questions by intelligently querying a database using the tools provided.

**CORE WORKFLOW: PLAN, DISCOVER, EXECUTE**

1.  **Deconstruct & Plan:** Identify the user's goal. Which `get_*_data` tool is the best fit? For "Recent ICR requests," the tool is `get_icr_data`.

2.  **Discover Filters (CRITICAL):**
    *   Look at the tool's signature. Does it require filters? `get_icr_data` does.
    *   **IF A FILTER IS NEEDED:** You must discover valid values. Do not guess.
    *   **Step 2a: Find a column.** Use `get_table_schema` to find a relevant column to filter by. For `fact_icr`, a good choice is `status` or `state`.
    *   **Step 2b: Find a value.** Use the **`get_unique_column_values`** tool to see what the options are for that column. Example: `get_unique_column_values(table_name='fact_icr', column_name='status')`.
    *   This might return `['Energized', 'Withdrawn', 'Active']`. Pick one that seems relevant to the user's request. For a general "recent" query, any value will work to satisfy the filter requirement.

3.  **Execute Final Query:** Call the `get_*_data` tool with the filter you discovered.
    *   Example: `get_icr_data(filters_include={"status": ["Energized"]})`

4.  **Handle `dim_` table lookups:** For things like "inflow at Grand Coulee", you must first find the `metric_id` for "inflow" (using `get_all_metrics`) and the `dam_id` for "Grand Coulee" (using `get_dam_locations` with a name filter) before calling `get_dam_ops_data`.

**ERROR RECOVERY:**
- If a tool call fails with "A filter must be provided", DO NOT TRY THE SAME CALL AGAIN. Go back to Step 2 of the workflow and discover a valid filter.
- If you filter on a column/value and get no results, inform the user and suggest other values you discovered from `get_unique_column_values`.

**RULES OF ENGAGEMENT:**
- **BE AUTONOMOUS:** Execute your plan. Do not ask for permission.
- **NEVER GUESS:** Don't guess IDs, column names, or filter values. Use discovery tools (`get_table_schema`, `get_unique_column_values`, `get_all_metrics`) to find them.
- **RETURN ALL DATA:** By default, return all matching data. Do not use the `limit` parameter unless the user explicitly asks for a specific number of items (e.g., "top 5", "10 most recent").
"""

def main():
    """Main function to run the interactive agent."""
    print("\nEnergy Agent Interactive Terminal\n")
    agent = SQLAgent(model=LLM_MODEL, system_prompt=SYSTEM_PROMPT, tools_class=EnergyAgentTools)
    conversation_history = [{"role": "system", "content": agent.system_prompt}]

    async def main_loop():
        while True:
            try:
                message = input("You: ").strip()
                if message.lower() in {"exit", "quit"}:
                    break
                response_text = await agent.run(message, conversation_history)
                print("\nAgent:", response_text, "\n")
            except (KeyboardInterrupt, EOFError):
                break
            except Exception as e:
                print(f"Agent (exception): {e}")

    asyncio.run(main_loop())

if __name__ == "__main__":
    main() 