# omnis_hermes/tools/executor.py
#
# ToolExecutor — dispatches tool calls from the LLM to their executors.
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

_MAX_RETRIES = 2
_BASE_BACKOFF = 0.5


class ToolExecutor:
    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    async def execute_calls(
        self, tool_calls: Any, conversation: Conversation
    ) -> None:
        for tool_call in tool_calls:
            func_name: str = tool_call.function.name
            result = await self._dispatch(func_name, tool_call.function.arguments)
            conversation.add_tool_result(tool_call.id, func_name, result)

    async def _dispatch(self, func_name: str, raw_args: str) -> str:
        try:
            func_args: dict = json.loads(raw_args)
        except json.JSONDecodeError as e:
            return f"Error: Could not parse arguments for '{func_name}': {e}"

        executor_func = self.registry.executors.get(func_name)
        if not executor_func:
            available = ", ".join(self.registry.executors) or "none"
            return (
                f"Error: Tool '{func_name} not found. "
                f"Available tools: {available}"
            )

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
                return str(result_data)

            except Exception as exc:
                last_error = f"Execution error in '{func_name}': {exc}"
                logger.warning(
                    "Tool '%s' attempt %d/%d failed: %s",
                    func_name, attempt + 1, _MAX_RETRIES + 1, exc,
                )

                if isinstance(exc, (TypeError, ValueError, KeyError)):
                    break

                if attempt < _MAX_RETRIES:
                    delay = _BASE_BACKOFF * (2 ** attempt) + random.uniform(0, 0.3)
                    await asyncio.sleep(delay)

        return last_error