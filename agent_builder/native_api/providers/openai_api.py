# omnis_hermes/providers/openai.py
#
# Thin async wrapper around any OpenAI-compatible chat completions endpoint.
# Defaults to OpenRouter so any model string works (gpt-4o, claude-*, etc.)
#
# Production concerns addressed:
#   - Exponential backoff + jitter on transient provider errors (429, 5xx)
#   - Hard stop on permanent errors (401, 403, 400)
#   - finish_reason guard: stops if the model hits max_tokens mid-thought
#   - parallel_tool_calls disabled — required when strict: true is set
#   - Token streaming: reassembles delta chunks (content + tool_calls) into
#     the same (message_dict, tool_calls) shape generate() already returns,
#     so callers don't need two code paths.
#
import asyncio
import logging
import os
import random
import frappe
from typing import Any, Callable, Dict, List, Optional, Tuple

from openai import AsyncOpenAI, APIStatusError, APIConnectionError

from agent_builder.native_api.agent_types.messages import Message, MessageList

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BASE_BACKOFF = 1.0  # seconds

# HTTP status codes that are permanent — never retry
_PERMANENT_STATUS = {400, 401, 403, 404, 422}

# Called with each raw text delta as it streams in. Sync or async both fine.
TokenCallback = Optional[Callable[[str], Any]]



class OpenAIProvider:
    def __init__(self, model: str = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning") -> None:
        agent_setup = frappe.get_doc("Agent Setup")
        self.model = model
        self.client = AsyncOpenAI(
            api_key=agent_setup.get_password("api_key"),
            base_url="https://openrouter.ai/api/v1",
            # api_key=os.environ["NVIDIA_API_KEY"],
            # base_url="https://integrate.api.nvidia.com/v1",
        )

    async def generate(
        self,
        messages: MessageList,
        tools: Optional[List[Dict[str, Any]]] = None,
        on_token: TokenCallback = None,
    ) -> Tuple[Message, Any]:
        """
        Sends a chat completion request and returns:
          (message_dict, tool_calls)

        message_dict is a plain dict safe to append to conversation history.
        tool_calls is None when the model is done.

        If on_token is provided, the request is streamed and on_token(delta)
        is invoked for every text fragment as it arrives. The final return
        value is identical either way — streaming is purely a side channel
        for live UI updates, callers don't need to branch on it.

        Retries on transient errors (429, 5xx, network) with exponential
        backoff + jitter. Raises immediately on permanent errors. Note:
        once a stream has emitted partial tokens to on_token, a retry of
        that attempt will re-emit tokens from the start — callers doing UI
        streaming should treat each attempt's tokens as belonging to a
        single in-progress bubble, not append-only across retries.
        """
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
            # Required when strict: true is set on any tool schema
            kwargs["parallel_tool_calls"] = False

        last_exc: Optional[Exception] = None

        for attempt in range(_MAX_RETRIES):
            try:
                if on_token is not None:
                    return await self._generate_streaming(kwargs, on_token)
                return await self._generate_once(kwargs)

            except APIStatusError as exc:
                if exc.status_code in _PERMANENT_STATUS:
                    logger.error(
                        "Permanent provider error %d — not retrying: %s",
                        exc.status_code, exc.message,
                    )
                    raise

                last_exc = exc
                logger.warning(
                    "Transient provider error %d (attempt %d/%d): %s",
                    exc.status_code, attempt + 1, _MAX_RETRIES, exc.message,
                )

            except APIConnectionError as exc:
                last_exc = exc
                logger.warning(
                    "Provider connection error (attempt %d/%d): %s",
                    attempt + 1, _MAX_RETRIES, exc,
                )

            if attempt < _MAX_RETRIES - 1:
                delay = _BASE_BACKOFF * (2 ** attempt) + random.uniform(0, 0.5)
                await asyncio.sleep(delay)

        raise RuntimeError(
            f"Provider failed after {_MAX_RETRIES} attempts."
        ) from last_exc

    # ── Non-streaming path (unchanged behaviour) ──────────────────────

    async def _generate_once(self, kwargs: Dict[str, Any]) -> Tuple[Message, Any]:
        response = await self.client.chat.completions.create(**kwargs)
        choice = response.choices[0]

        if choice.finish_reason == "length":
            raise RuntimeError(
                "Provider returned finish_reason='length' — "
                "the model hit max_tokens before completing its response. "
                "Increase max_tokens or shorten the context."
            )

        message = choice.message
        message_dict: Message = message.model_dump(exclude_none=True)
        return message_dict, getattr(message, "tool_calls", None)

    # ── Streaming path ─────────────────────────────────────────────────

    async def _generate_streaming(
        self, kwargs: Dict[str, Any], on_token: Callable[[str], Any]
    ) -> Tuple[Message, Any]:
        stream = await self.client.chat.completions.create(**kwargs, stream=True)

        content_parts: List[str] = []
        # tool_calls arrive as index-addressed fragments that must be
        # reassembled: {0: {"id": ..., "name": ..., "arguments": "..."}}
        tool_call_frags: Dict[int, Dict[str, Any]] = {}
        finish_reason: Optional[str] = None
        role = "assistant"

        async for chunk in stream:
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            delta = choice.delta

            if choice.finish_reason:
                finish_reason = choice.finish_reason

            if delta is None:
                continue

            if getattr(delta, "role", None):
                role = delta.role

            if delta.content:
                content_parts.append(delta.content)
                result = on_token(delta.content)
                if asyncio.iscoroutine(result):
                    await result

            if getattr(delta, "tool_calls", None):
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    frag = tool_call_frags.setdefault(idx, {
                        "id": None,
                        "type": "function",
                        "function": {"name": "", "arguments": ""},
                    })
                    if tc_delta.id:
                        frag["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            frag["function"]["name"] += tc_delta.function.name
                        if tc_delta.function.arguments:
                            frag["function"]["arguments"] += tc_delta.function.arguments

        if finish_reason == "length":
            raise RuntimeError(
                "Provider returned finish_reason='length' — "
                "the model hit max_tokens before completing its response. "
                "Increase max_tokens or shorten the context."
            )

        content = "".join(content_parts)
        tool_calls = None
        if tool_call_frags:
            ordered = [tool_call_frags[i] for i in sorted(tool_call_frags)]
            tool_calls = [_DeltaToolCall(t) for t in ordered]

        message_dict: Message = {"role": role, "content": content or None}
        if tool_call_frags:
            message_dict["tool_calls"] = [tc.copy() for tc in
                                           [tool_call_frags[i] for i in sorted(tool_call_frags)]]
        message_dict = {k: v for k, v in message_dict.items() if v is not None}

        return message_dict, tool_calls


class _DeltaToolCall:
    """Lightweight shim so reassembled streamed tool calls expose the same
    .id / .function.name / .function.arguments attribute access that
    Agent.run() already uses for non-streamed tool_calls (OpenAI SDK objects),
    without pulling in the SDK's full pydantic model."""

    class _Function:
        def __init__(self, d: Dict[str, Any]):
            self.name = d.get("name", "")
            self.arguments = d.get("arguments", "")

    def __init__(self, d: Dict[str, Any]):
        self.id = d.get("id")
        self.type = d.get("type", "function")
        self.function = self._Function(d.get("function", {}))