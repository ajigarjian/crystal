"""
Energy Agent using Native Python and OpenAI API.
v6: The Proactive Agent. Uses schema discovery to act autonomously and intelligently.
"""
from dotenv import load_dotenv
load_dotenv()
import json
import logging
import os
import re
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import asyncio
import inspect
import requests
from openai import AsyncOpenAI

os.environ["FUNCTIONS_EMULATOR"] = "True"

# --- Local Dependencies ---
from helpers.db_utils import execute_query

# --- Configuration & Utilities (Unchanged) ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
GOOGLE_GEOCODING_API_KEY = os.getenv("GOOGLE_GEOCODING_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LLM_MODEL = "gpt-4o-mini"
client = AsyncOpenAI(api_key=OPENAI_API_KEY)
todays_date = str(datetime.now().date())

def geocode_location_google(location: str) -> Optional[Dict[str, float]]:
    if not GOOGLE_GEOCODING_API_KEY: return None
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": location, "key": GOOGLE_GEOCODING_API_KEY}
    try:
        resp = requests.get(url, params=params, timeout=5); resp.raise_for_status(); data = resp.json()
        if data.get("status") == "OK" and data.get("results"): return data["results"][0]["geometry"]["location"]
    except Exception as e: logger.error(f"[GEOCODE] Exception for '{location}': {e}")
    return None

def is_sql_safe(query: str) -> bool:
    query_upper = query.upper().strip()
    if not query_upper.startswith("SELECT"): return False
    unsafe = ["INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "TRUNCATE", "GRANT", "REVOKE", "EXEC"]
    if any(k in query_upper for k in unsafe): return False
    if "SELECT *" in query_upper and "WHERE" not in query_upper: return False
    return True

def is_safe_identifier(name: str) -> bool:
    return name is not None and re.match(r'^[a-zA-Z0-9_]+$', name) is not None

# --- Core Logic: Generic WHERE Clause Builder (Unchanged) ---
def _build_where_clause(filters_include: Optional[Dict[str, List[str]]] = None, filters_exclude: Optional[Dict[str, List[str]]] = None) -> Tuple[str, List[Any]]:
    clauses, params = [], []
    if filters_include:
        for col, values in filters_include.items():
            if is_safe_identifier(col) and values:
                op, val = ("ILIKE %s", values[0]) if len(values) == 1 else ("IN %s", tuple(values))
                clauses.append(f"{col} {op}"); params.append(val)
    if filters_exclude:
        for col, values in filters_exclude.items():
            if is_safe_identifier(col) and values:
                op, val = ("NOT ILIKE %s", values[0]) if len(values) == 1 else ("NOT IN %s", tuple(values))
                clauses.append(f"{col} {op}"); params.append(val)
    if not clauses: return "", []
    return f"WHERE {' AND '.join(clauses)}", params

class ToolOrchestrator:
    # (Unchanged from previous version)
    async def get_unique_column_values(self, table_name: str, column_name: str, limit: int = 20) -> List[str]:
        if not is_safe_identifier(table_name) or not is_safe_identifier(column_name): return []
        try:
            query = f"SELECT DISTINCT {column_name} FROM {table_name} WHERE {column_name} IS NOT NULL LIMIT %s"
            results = execute_query(query, [limit])
            return [str(row[column_name]) for row in results if row.get(column_name)]
        except Exception: return []

    async def execute_sql(self, query: str, params: List) -> Dict[str, Any]:
        """Direct SQL execution, to be used by tools after they build the query."""
        if not is_sql_safe(query): return {"success": False, "error": "Query is not safe."}
        try:
            logger.info(f"[SQL QUERY] {query} | PARAMS: {params}")
            results = execute_query(query, params)
            logger.info(f"[SQL RESULT] Found {len(results)} rows.")
            return {"success": True, "data": results}
        except Exception as e:
            return {"success": False, "error": str(e)}

class EnergyAgentTools:
    """Tools now include schema discovery for proactive planning."""
    orchestrator = ToolOrchestrator()

    # --- THE NEW DISCOVERY TOOL ---
    @staticmethod
    async def get_table_schema(table_name: str) -> Dict[str, Any]:
        """
        Retrieves the schema (column names and data types) for a given database table.
        This is a discovery tool used for planning queries.
        Args:
            table_name (str): The name of the table to inspect (e.g., 'fact_icr').
        """
        if not is_safe_identifier(table_name):
            return {"success": False, "error": "Invalid table name."}
        
        query = """
            SELECT column_name, data_type FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position;
        """
        return await EnergyAgentTools.orchestrator.execute_sql(query, [table_name])

    # --- DATA TOOLS ARE NOW SIMPLER ---
    # They just build the query and let the orchestrator run it.
    @staticmethod
    async def get_icr_data(
        filters_include: Optional[Dict[str, List[str]]] = None,
        filters_exclude: Optional[Dict[str, List[str]]] = None,
        limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get Interconnection Request (ICR) data from the 'fact_icr' table using flexible filters.
        Args:
            filters_include (Optional[Dict[str, List[str]]]): Columns and values to include. E.g., {"state": ["WA"]}.
            filters_exclude (Optional[Dict[str, List[str]]]): Columns and values to exclude. E.g., {"status": ["WITHDRAWN"]}.
            limit (Optional[int]): Max number of records to return.
        """
        base_query = "SELECT request_number, project_name, status, state, county, max_summer_mw, fuel_source_1 FROM fact_icr"
        where_clause, params = _build_where_clause(filters_include, filters_exclude)
        if not where_clause:
            return {"success": False, "error": "A filter must be provided for ICR data."}
        query = f"{base_query} {where_clause} ORDER BY request_date DESC"
        if limit:
            query += " LIMIT %s"; params.append(limit)
        return await EnergyAgentTools.orchestrator.execute_sql(query, params)

    @staticmethod
    async def get_power_infrastructure(
        location: str, radius_km: int = 50,
        filters_include: Optional[Dict[str, List[str]]] = None,
        limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get power infrastructure from 'power_infra' near a location with optional filters.
        Args:
            location (str): A required city or landmark to search near.
            radius_km (int): The search radius in kilometers.
            filters_include (Optional[Dict[str, List[str]]]): Filter by columns like 'operator' or 'power'.
            limit (Optional[int]): Max number of records to return.
        """
        coords = geocode_location_google(location)
        if not coords: return {"success": False, "error": f"Could not geocode location: {location}"}
        
        base_query = "SELECT gid, openinfra_name, voltage, power, operator, ST_AsGeoJSON(geom) as geometry FROM power_infra"
        spatial_clause = "ST_DWithin(geom::geography, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s)"
        params = [coords["lon"], coords["lat"], radius_km * 1000]
        
        attr_clause, attr_params = _build_where_clause(filters_include)
        
        where_parts = [spatial_clause]
        if attr_clause:
            where_parts.append(attr_clause.replace("WHERE ", "")) # Combine clauses
            params.extend(attr_params)

        query = f"{base_query} WHERE {' AND '.join(where_parts)} ORDER BY voltage DESC NULLS LAST"
        if limit:
            query += " LIMIT %s"; params.append(limit)
            
        return await EnergyAgentTools.orchestrator.execute_sql(query, params)

class SimpleEnergyAgent:
    def __init__(self, model: str):
        self.model = model
        self.tools = self._register_tools()
        self.tool_schemas = self._create_tool_schemas()
        self.system_prompt = self._get_system_prompt()

    def _register_tools(self) -> Dict[str, callable]:
        return {name: func for name, func in inspect.getmembers(EnergyAgentTools, inspect.isfunction) if not name.startswith("_")}

    def _get_system_prompt(self) -> str:
        return f"""You are an expert, autonomous energy market analyst. Your goal is to answer user questions by intelligently querying a database using the tools provided.

**PROACTIVE DISCOVERY AND EXECUTION STRATEGY**

Your primary operating principle is "Discover, then Act." You must be proactive and avoid asking the user for clarification unless a request is impossible to fulfill.

1.  **Interpret Intent:** Understand the user's goal. "ICR backlog" means "Show me all non-finished Interconnection Requests."
2.  **Discover Schema (if needed):** If you are unsure what columns you can filter on for a table (e.g., 'fact_icr'), your **first step** is to use the `get_table_schema` tool. This gives you the knowledge needed to build a query.
3.  **Formulate a Plan:** Based on the schema, make an expert assumption.
    *   *Example Plan:* "The user wants the ICR backlog. After checking the schema, I see a `status` column. I will assume 'backlog' means excluding any requests with statuses like 'ENERGIZED', 'WITHDRAWN', or 'DECOMMISSIONED'."
4.  **Execute Confidently:** Call the appropriate data-fetching tool (e.g., `get_icr_data`) with your formulated filters.
5.  **Summarize Results:** Directly present the answer to the user.

**RULES OF ENGAGEMENT:**
- **BE AUTONOMOUS:** Do not ask for permission to run a query. Do not explain your plan to the user before executing it. Act like a confident expert who delivers answers.
- **USE `get_table_schema`:** This is your key to understanding how to answer ambiguous questions.
- **MAKE REASONABLE ASSUMPTIONS:** It is better to make a smart guess and deliver results than to ask a clarifying question.
- **NEVER HALLUCINATE FILTERS:** Only use column names you have discovered via the schema tool.
- **READ-ONLY:** You cannot modify data. Politely refuse any such requests.
"""

    def _create_tool_schemas(self) -> List[Dict]:
        # (Unchanged from v5)
        schemas = []
        for name, func in self.tools.items():
            sig = inspect.signature(func)
            doc = inspect.getdoc(func); description = doc.strip() if doc else ""
            properties = {}; required = []
            for param in sig.parameters.values():
                if param.name in ["self", "cls"]: continue
                param_type_str = str(param.annotation)
                if 'Dict[str, List[str]]' in param_type_str:
                    param_type = {"type": "object", "additionalProperties": {"type": "array", "items": {"type": "string"}}}
                elif 'int' in param_type_str: param_type = {"type": "integer"}
                else: param_type = {"type": "string"}
                properties[param.name] = {**param_type, "description": f"Parameter: {param.name}"}
                if param.default is inspect.Parameter.empty: required.append(param.name)
            schemas.append({"type": "function", "function": {"name": name, "description": description, "parameters": {"type": "object", "properties": properties, "required": required}}})
        return schemas

    async def run(self, message: str, conversation_history: List[Dict]) -> str:
        # The run loop is robust and handles the multi-step tool calls automatically.
        conversation_history.append({"role": "user", "content": message})
        try:
            # The agent might loop through tool calls (e.g., schema -> data) up to 3 times
            for _ in range(3):
                response = await client.chat.completions.create(model=self.model, messages=conversation_history, tools=self.tool_schemas, tool_choice="auto")
                response_message = response.choices[0].message

                if not response_message.tool_calls:
                    # If no more tools to call, we have our final answer.
                    return response_message.content or "I have finished processing the request."
                
                conversation_history.append(response_message)
                for tool_call in response_message.tool_calls:
                    logger.info(f"Executing tool `{tool_call.function.name}` with args: {tool_call.function.arguments}")
                    if func := self.tools.get(tool_call.function.name):
                        try:
                            args = json.loads(tool_call.function.arguments)
                            result = await func(**args)
                            conversation_history.append({"tool_call_id": tool_call.id, "role": "tool", "name": tool_call.function.name, "content": json.dumps(result, default=str)})
                        except Exception as e:
                            logger.error(f"Error executing tool {tool_call.function.name}: {e}", exc_info=True)
                            conversation_history.append({"tool_call_id": tool_call.id, "role": "tool", "name": tool_call.function.name, "content": json.dumps({"success": False, "error": str(e)})})
            
            # If the loop finishes, get one last summary from the model
            final_response = await client.chat.completions.create(model=self.model, messages=conversation_history)
            return final_response.choices[0].message.content

        except Exception as e:
            logger.error(f"Agent run failed: {e}", exc_info=True)
            return f"An error occurred: {e}"

# --- Main Interactive Loop ---
if __name__ == "__main__":
    print("\nEnergy Agent Interactive Terminal (v6 - Proactive & Autonomous)\n")
    agent = SimpleEnergyAgent(model=LLM_MODEL)
    conversation_history = [{"role": "system", "content": agent.system_prompt}]
    async def main_loop():
        while True:
            try:
                message = input("You: ").strip()
                if message.lower() in {"exit", "quit"}: break
                response_text = await agent.run(message, conversation_history)
                print("\nAgent:", response_text, "\n")
            except (KeyboardInterrupt, EOFError): break
            except Exception as e: print(f"Agent (exception): {e}")
    asyncio.run(main_loop())