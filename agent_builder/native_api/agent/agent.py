# omnis_hermes/agent/agent.py
import asyncio
import json
import logging
import random
import time
from typing import Callable, Optional, Tuple

from agent_builder.native_api.agent.conversation import Conversation
from agent_builder.native_api.tools.executor import ToolExecutor
from agent_builder.native_api.providers.openai_api import OpenAIProvider
from agent_builder.native_api.tools.decorator import ToolRegistry

logger = logging.getLogger(__name__)

class MaxTurnsError(Exception):
    pass

class Agent:
    def __init__(
        self,
        provider: OpenAIProvider,
        registry: ToolRegistry,
        system_prompt: str = "You are an automated Hermes system node.",
        max_turns: int = 20,
        max_retries: int = 2,
        max_context_chars: int = 32000,
    ):
        self.provider = provider
        self.registry = registry
        self.system_prompt = system_prompt
        self.max_turns = max_turns
        self.max_retries = max_retries
        self.max_context_chars = max_context_chars
        self.executor = ToolExecutor(registry)

    async def run(
        self,
        conversation: Conversation,
        on_token: Optional[Callable[[str], None]] = None,
    ) -> str:
        """
        on_token, if given, is called with each raw text delta as the
        model's response streams in for that turn. It fires only for the
        assistant's own text — not tool output — and only for turns where
        the model is actually emitting content (a pure tool-call turn may
        produce no token events at all).
        """
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
                    messages, available_tools, on_token=on_token
                )
                conversation.add_assistant_message(response, streamed=on_token is not None)

                if not tool_calls:
                    return response.get("content", "")

                fp = (tool_calls[0].function.name, tool_calls[0].function.arguments)
                if fp == last_fp:
                    loop_strikes += 1
                    if loop_strikes >= 3:
                        raise MaxTurnsError(f"Stuck calling '{fp[0]}'")
                else:
                    last_fp = fp
                    loop_strikes = 0

                # Execute tools one-by-one to measure time and emit events
                for tc in tool_calls:
                    name = tc.function.name
                    try:
                        args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        args = tc.function.arguments

                    # 1. Tell conversation to emit the 'tool_start' event
                    conversation.emit_tool_start(tc.id, name, args)

                    # 2. Execute tool and measure time (time.monotonic is safe against system clock shifts)
                    t0 = time.monotonic()
                    result = await self.executor._dispatch(name, tc.function.arguments)
                    elapsed_ms = int((time.monotonic() - t0) * 1000)

                    # 3. Tell conversation to save to DB and emit 'tool_done' event
                    conversation.add_tool_result(tc.id, name, result, elapsed_ms=elapsed_ms)

            raise MaxTurnsError(f"Exceeded {self.max_turns}-turn budget.")

        finally:
            conversation.save()

    async def _retry_llm(self, messages, tools, on_token=None):
        last_err = None
        for attempt in range(self.max_retries + 1):
            try:
                return await self.provider.generate(
                    messages=messages, tools=tools or None, on_token=on_token
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