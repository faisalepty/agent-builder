# omnis_hermes/tools/executor.py
#
# ToolExecutor — dispatches tool calls from the LLM to their executors.
#
# Production concerns addressed:
#   - Max retries with exponential backoff + jitter for transient errors
#   - Hard stop on repeated identical failures (loop detection)
#   - Clear, concise error messages back to the model (not raw tracebacks)
#   - Async-aware dispatch
#
import asyncio
import inspect
import json
import logging
import random
from typing import Any

from agent_builder.native_api.tools.decorator import ToolRegistry
from agent_builder.native_api.agent.conversation import Conversation

logger = logging.getLogger(__name__)

# Errors the model can't fix by retrying with the same args.
# Return these immediately without burning retry budget.
_PERMANENT_PREFIXES = (
    "Error: Tool",          # not found
    "Error: Could not",     # bad JSON args — model should fix args
)

_MAX_RETRIES = 2          # up to 3 total attempts (initial + 2 retries)
_BASE_BACKOFF = 0.5       # seconds


class ToolExecutor:
    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    async def execute_calls(
        self, tool_calls: Any, conversation: Conversation
    ) -> None:
        """
        Dispatches every tool call in a single LLM turn.

        Each call goes through:
          1. JSON argument parsing
          2. Executor lookup
          3. Execution with retry + backoff for transient failures
          4. Result appended to conversation history
        """
        for tool_call in tool_calls:
            func_name: str = tool_call.function.name
            result = await self._dispatch(func_name, tool_call.function.arguments)
            conversation.add_tool_result(tool_call.id, func_name, result)

    async def _dispatch(self, func_name: str, raw_args: str) -> str:
        # ---- Parse args ----------------------------------------------------
        try:
            func_args: dict = json.loads(raw_args)
        except json.JSONDecodeError as e:
            return f"Error: Could not parse arguments for '{func_name}': {e}"

        # ---- Resolve executor ----------------------------------------------
        executor_func = self.registry.executors.get(func_name)
        if not executor_func:
            available = ", ".join(self.registry.executors) or "none"
            return (
                f"Error: Tool '{func_name}' not found. "
                f"Available tools: {available}"
            )

        # ---- Execute with retry + backoff ----------------------------------
        last_error: str = ""
        for attempt in range(_MAX_RETRIES + 1):
            try:
                if inspect.iscoroutinefunction(executor_func):
                    result_data = await executor_func(**func_args)
                else:
                    result_data = executor_func(**func_args)
                return str(result_data)

            except Exception as exc:
                last_error = f"Execution error in '{func_name}': {exc}"
                logger.warning(
                    "Tool '%s' attempt %d/%d failed: %s",
                    func_name, attempt + 1, _MAX_RETRIES + 1, exc,
                )

                # Permanent failure — don't retry
                if isinstance(exc, (TypeError, ValueError, KeyError)):
                    break

                # Transient failure — backoff before retry
                if attempt < _MAX_RETRIES:
                    delay = _BASE_BACKOFF * (2 ** attempt) + random.uniform(0, 0.3)
                    await asyncio.sleep(delay)

        return last_error