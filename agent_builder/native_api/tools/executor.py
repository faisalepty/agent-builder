# agent_builder/native_api/tools/executor.py
#
# ToolExecutor — dispatches tool calls from the LLM to their executors.
#
# Supports parallel execution when called with multiple tool calls.
#
import asyncio
import inspect
import json
import logging
import random
from typing import Any, List

import frappe

from agent_builder.native_api.agent.conversation import Conversation
from agent_builder.native_api.tools.decorator import ToolRegistry

logger = logging.getLogger(__name__)

_MAX_RETRIES = 2
_BASE_BACKOFF = 0.5


class ToolExecutor:
    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    async def execute_calls(self, tool_calls: Any, conversation: Conversation) -> None:
        """
        Execute tool calls concurrently.
        """

        async def execute_single(tc: Any) -> None:
            """Execute a single tool call."""
            func_name: str = tc.function.name
            result = await self._dispatch(func_name, tc.function.arguments)
            conversation.add_tool_result(tc.id, func_name, result)

        await asyncio.gather(*[execute_single(tc) for tc in tool_calls])

    async def _dispatch(self, func_name: str, raw_args: str) -> str:
        """
        Dispatch a single tool call to its executor function.
        """
        try:
            func_args: dict = json.loads(raw_args)
        except json.JSONDecodeError as e:
            return json.dumps({"error": f"Could not parse arguments for '{func_name}': {e}"})

        executor_func = self.registry.executors.get(func_name)
        if not executor_func:
            available = ", ".join(self.registry.executors) or "none"
            return json.dumps({"error": f"Tool '{func_name}' not found. Available tools: {available}"})

        sig = inspect.signature(executor_func)
        params = list(sig.parameters.keys())
        use_args_dict = len(params) >= 1 and params[0] == "args"

        last_error: str = ""
        for attempt in range(_MAX_RETRIES + 1):
            try:
                if inspect.iscoroutinefunction(executor_func):
                    if use_args_dict:
                        result_data = await executor_func(args=func_args)
                    else:
                        result_data = await executor_func(**func_args)
                else:
                    if use_args_dict:
                        result_data = executor_func(args=func_args)
                    else:
                        result_data = executor_func(**func_args)
                
                # Serialize dicts/lists to JSON string so workflow engine 
                # can safely json.loads() it back into an object.
                if isinstance(result_data, (dict, list)):
                    return json.dumps(result_data, default=str)
                if isinstance(result_data, str):
                    return result_data
                return str(result_data)

            except Exception as exc:
                last_error = f"Execution error in '{func_name}': {exc}"
                frappe.log_error(
                    f"Tool '{func_name}' attempt {attempt+1}/{_MAX_RETRIES+1} failed: {exc}",
                    frappe.get_traceback(),
                )

                if isinstance(exc, (TypeError, ValueError, KeyError)):
                    break

                if attempt < _MAX_RETRIES:
                    delay = _BASE_BACKOFF * (2**attempt) + random.uniform(0, 0.3)
                    await asyncio.sleep(delay)

        return json.dumps({"error": last_error})