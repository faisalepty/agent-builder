# agent_builder/native_api/agent/agent.py
import asyncio
import json
import logging
import random
import time
import frappe
from typing import Callable, Optional, Tuple

from agent_builder.native_api.agent.conversation import Conversation
from agent_builder.native_api.agent.setup import get_tool_registry, get_system_prompt
from agent_builder.native_api.tools.executor import ToolExecutor
from agent_builder.native_api.providers.openai_api import OpenAIProvider

logger = logging.getLogger(__name__)


class MaxTurnsError(Exception):
    pass


class Agent:
    """
    Standalone Agent. 
    
    Handles its own tool loading, system prompt generation, and provider setup
    internally via setup.py. The caller only needs to provide the model name.
    """
    def __init__(
        self,
        max_turns: int = 40,
        max_retries: int = 2,
        max_context_chars: int = 32000,
    ):
        # 1. Bootstrap internal dependencies via setup.py
        self.registry = get_tool_registry()
        self.system_prompt = get_system_prompt()
        
        # 2. Initialize provider and executor
        self.provider = OpenAIProvider()
        self.executor = ToolExecutor(self.registry)
        
        # 3. Store config
        self.max_turns = max_turns
        self.max_retries = max_retries
        self.max_context_chars = max_context_chars

    async def run(
        self,
        conversation: Conversation,
        on_token: Optional[Callable[[str], None]] = None,
        on_reasoning: Optional[Callable[[str], None]] = None,
    ) -> str:
        available_tools = self.registry.get_tool_schemas()
        conversation.set_system(self.system_prompt)

        last_fp: Optional[Tuple[str, str]] = None
        loop_strikes = 0
        turns = 0

        try:
            while turns < self.max_turns:
                turns += 1
                messages = self._trim_context(conversation.get_messages())

                response, tool_calls = await self._retry_llm(
                    messages, available_tools, on_token=on_token, on_reasoning=on_reasoning
                )
                conversation.add_assistant_message(
                    response, streamed=on_token is not None or on_reasoning is not None
                )

                if not tool_calls:
                    frappe.log_error(response, "Agent Final Response")
                    return response.get("content", "")

                fp = (tool_calls[0].function.name, tool_calls[0].function.arguments)
                if fp == last_fp:
                    loop_strikes += 1
                    if loop_strikes >= 3:
                        raise MaxTurnsError(f"Stuck calling '{fp[0]}'")
                else:
                    last_fp = fp
                    loop_strikes = 0

                for tc in tool_calls:
                    name = tc.function.name
                    try:
                        args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        args = tc.function.arguments

                    conversation.emit_tool_start(tc.id, name, args)

                    t0 = time.monotonic()
                    result = await self.executor._dispatch(name, tc.function.arguments)
                    elapsed_ms = int((time.monotonic() - t0) * 1000)

                    conversation.add_tool_result(tc.id, name, result, elapsed_ms=elapsed_ms)

            raise MaxTurnsError(f"Exceeded {self.max_turns}-turn budget.")

        finally:
            conversation.save()

    async def _retry_llm(self, messages, tools, on_token=None, on_reasoning=None):
        last_err = None
        for attempt in range(self.max_retries + 1):
            try:
                return await self.provider.generate(
                    messages=messages, tools=tools or None,
                    on_token=on_token, on_reasoning=on_reasoning,
                )
            except Exception as e:
                last_err = e
                if attempt < self.max_retries:
                    await asyncio.sleep(min(2 ** attempt, 8) + random.uniform(0, 1))
        raise last_err

    def _trim_context(self, messages):
        total_chars = sum(len(m.get("content", "")) for m in messages)
        if total_chars <= self.max_context_chars:
            return messages

        has_system = messages and messages[0]["role"] == "system"
        kept = [messages[0]] if has_system else []
        limit = self.max_context_chars

        for msg in reversed(messages[1:] if has_system else messages):
            limit -= len(msg.get("content", ""))
            if limit < 0:
                break
            kept.insert(1 if has_system else 0, msg)

        return kept