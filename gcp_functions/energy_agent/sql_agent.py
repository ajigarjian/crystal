"""
Generic, reusable agent for interacting with SQL databases using a tool-based approach.
"""
import json
import logging
import inspect
from typing import Dict, Any, List, Optional, Tuple
import re
import os

from dotenv import load_dotenv
from openai import AsyncOpenAI

# --- Local Dependencies ---
from helpers.db_utils import execute_query

load_dotenv()

# --- Configuration & Utilities ---
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logging.getLogger("httpx").setLevel(logging.DEBUG)
logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = AsyncOpenAI(api_key=OPENAI_API_KEY)


def is_sql_safe(query: str) -> bool:
    """Performs a basic safety check on the SQL query."""
    query_upper = query.upper().strip()
    if not query_upper.startswith("SELECT"):
        return False
    unsafe_keywords = ["INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "TRUNCATE", "GRANT", "REVOKE", "EXEC"]
    if any(keyword in query_upper for keyword in unsafe_keywords):
        return False
    # Allow SELECT * with a WHERE clause, but disallow it without one for safety.
    if "SELECT *" in query_upper and "WHERE" not in query_upper:
        return False
    return True


def is_safe_identifier(name: str) -> bool:
    """Checks if a table or column name is a safe, simple identifier."""
    return name is not None and re.match(r'^[a-zA-Z0-9_]+$', name) is not None


def _build_where_clause(
    filters_include: Optional[Dict[str, List[Any]]] = None,
    filters_exclude: Optional[Dict[str, List[Any]]] = None
) -> Tuple[str, List[Any]]:
    """
    Builds a SQL WHERE clause and parameters from filter dictionaries.
    """
    clauses, params = [], []

    def _process_filters(filter_dict, op_map_single, op_map_multi):
        if not filter_dict:
            return
        if isinstance(filter_dict, str):
            try:
                filter_dict = json.loads(filter_dict)
            except json.JSONDecodeError:
                logger.error(f"Could not parse filter string: {filter_dict}")
                return

        for col, values in filter_dict.items():
            if is_safe_identifier(col) and values:
                clauses.append(f"{col} IS NOT NULL")
                if len(values) == 1:
                    op = op_map_single['str'] if isinstance(values[0], str) else op_map_single['num']
                    clauses.append(f"{col} {op}")
                    params.append(values[0])
                else:
                    clauses.append(f"{col} {op_map_multi}")
                    params.append(tuple(values))

    if filters_include:
        _process_filters(filters_include, {'str': 'ILIKE %s', 'num': '= %s'}, 'IN %s')
    if filters_exclude:
        _process_filters(filters_exclude, {'str': 'NOT ILIKE %s', 'num': '!= %s'}, 'NOT IN %s')

    if not clauses:
        return "", []
    return f"WHERE {' AND '.join(clauses)}", params


class ToolOrchestrator:
    """Handles the execution of SQL queries against the database."""
    async def execute_sql(self, query: str, params: List) -> Dict[str, Any]:
        """
        Executes a given SQL query after a safety check.
        
        Returns:
            A dictionary with 'success' status and either 'data' or 'error'.
        """
        if not is_sql_safe(query):
            return {"success": False, "error": "Query is not safe."}
        try:
            logger.debug(f"[SQL QUERY] {query} | PARAMS: {params}")
            results = execute_query(query, params)
            logger.debug(f"[SQL RESULT] Found {len(results)} rows.")
            return {"success": True, "data": results}
        except Exception as e:
            logger.error(f"SQL execution failed in orchestrator: {e}", exc_info=True)
            return {"success": False, "error": f"Database query failed: {e}"}


class SQLAgent:
    """
    A generic agent that uses tools to answer questions by querying a database.
    It is initialized with a specific system prompt and a class containing tool definitions.
    """
    def __init__(self, model: str, system_prompt: str, tools_class: type):
        self.model = model
        self.tools = self._register_tools(tools_class)
        self.tool_schemas = self._create_tool_schemas()
        self.system_prompt = system_prompt

    def _register_tools(self, tools_class: type) -> Dict[str, callable]:
        """
        Registers all static methods from the provided tools_class that are not private.
        """
        return {name: func for name, func in inspect.getmembers(tools_class, inspect.isfunction) if not name.startswith("_")}

    def _create_tool_schemas(self) -> List[Dict]:
        """
        Generates OpenAI-compatible tool schemas from the registered tool functions.
        """
        schemas = []
        for name, func in self.tools.items():
            sig = inspect.signature(func)
            doc = inspect.getdoc(func)
            description = doc.strip() if doc else ""
            properties = {}
            required = []
            for param in sig.parameters.values():
                if param.name in ["self", "cls"]:
                    continue
                param_type_str = str(param.annotation)
                if 'Dict' in param_type_str:
                    param_type = {"type": "object", "additionalProperties": {"type": "array", "items": {}}}
                elif 'int' in param_type_str:
                    param_type = {"type": "integer"}
                else:
                    param_type = {"type": "string"}
                properties[param.name] = {**param_type, "description": f"Parameter: {param.name}"}
                if param.default is inspect.Parameter.empty:
                    required.append(param.name)
            schemas.append({
                "type": "function",
                "function": {"name": name, "description": description, "parameters": {"type": "object", "properties": properties, "required": required}}
            })
        return schemas

    async def run(self, message: str, conversation_history: List[Dict]):
        """
        Main execution loop for the agent.
        Takes a user message and conversation history, and yields the agent's actions and final response.
        """
        conversation_history.append({"role": "user", "content": message})

        try:
            for i in range(7):  # Loop limit for chained tool calls
                logger.debug(f"--- Agent Iteration {i+1} ---")
                response = await client.chat.completions.create(
                    model=self.model,
                    messages=conversation_history,
                    tools=self.tool_schemas,
                    tool_choice="auto"
                )
                response_message = response.choices[0].message

                if not response_message.tool_calls:
                    logger.info("No more tool calls from LLM. Finalizing response.")
                    if response_message.content:
                        yield json.dumps({"type": "text", "content": response_message.content})
                    return

                conversation_history.append(response_message)

                for tool_call in response_message.tool_calls:
                    tool_name = tool_call.function.name
                    logger.info(f"LLM wants to run tool `{tool_name}` with args: {tool_call.function.arguments}")

                    if func := self.tools.get(tool_name):
                        try:
                            args = json.loads(tool_call.function.arguments)
                            yield json.dumps({
                                "type": "tool_code",
                                "content": {
                                    "name": tool_name,
                                    "arguments": args
                                }
                            })
                            result = await func(**args)

                            logger.debug(f"RAW tool result for `{tool_name}`: {result}")
                            content = json.dumps(result, default=str)

                            conversation_history.append({
                                "tool_call_id": tool_call.id,
                                "role": "tool",
                                "name": tool_name,
                                "content": content
                            })
                        except Exception as e:
                            error_content = {"success": False, "error": f"An unexpected error occurred in the tool '{tool_name}': {str(e)}"}
                            logger.error(f"FATAL ERROR executing tool `{tool_name}`.", exc_info=True)
                            conversation_history.append({
                                "tool_call_id": tool_call.id,
                                "role": "tool",
                                "name": tool_name,
                                "content": json.dumps(error_content)
                            })

            # After the loop, get a final response from the model
            final_response_stream = await client.chat.completions.create(
                model=self.model, 
                messages=conversation_history,
                stream=True
            )
            async for chunk in final_response_stream:
                content = chunk.choices[0].delta.content
                if content:
                    yield json.dumps({"type": "text", "content": content})

        except Exception as e:
            logger.error(f"Agent run failed entirely: {e}", exc_info=True)
            yield json.dumps({"type": "error", "content": f"An error occurred: {str(e)}"}) 