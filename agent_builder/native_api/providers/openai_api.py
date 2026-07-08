# omnis_hermes/providers/openai.py
#
# Thin async wrapper around any OpenAI-compatible chat completions endpoint.
# Defaults to OpenRouter so any model string works (gpt-4o, claude-*, etc.)
#
# Production concerns addressed:
#   - Exponential backoff + jitter on transient provider errors (429, 5xx)
#   - Hard stop on permanent errors (401, 403, 400)
#   - finish_reason guard: stops if the model hits max_tokens mid-thought
#   - Parallel tool calling support: models can return multiple tool calls
#     per turn, and they are executed concurrently
#   - Token streaming: reassembles delta chunks (content + tool_calls) into
#     the same (message_dict, tool_calls) shape generate() already returns,
#     so callers don't need two code paths.
#
import asyncio
import logging
import os
from agent_builder.agent_builder.doctype.agent_setup import agent_setup
import frappe
import random
from typing import Any, Callable, Dict, List, Optional, Tuple

from openai import AsyncOpenAI, APIStatusError, APIConnectionError

from agent_builder.native_api.agent_types.messages import Message, MessageList

from dataclasses import dataclass, field
from .registry import get_provider

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BASE_BACKOFF = 1.0  # seconds

# HTTP status codes that are permanent — never retry
_PERMANENT_STATUS = {400, 401, 403, 404, 422}

# ── Provider capability table ───────────────────────────────────────
#
# Everything that varies per provider on an otherwise-identical Chat
# Completions request lives here — reasoning, parallel_tool_calls,
# max_tokens naming, unsupported sampling params — so generate() itself
# never branches on provider name. Add a provider by adding one entry.
#
# Findings behind each field (each provider does this differently):
#   - parallel_tool_calls: OpenAI/OpenRouter/Gemini support it fully.
#     vLLM silently ignores it (documented no-op, harmless either way).
#     Anthropic's OpenAI-compat layer has partial support but can be
#     unreliable, so we don't force it there.
#   - max_tokens naming: OpenAI's actual reasoning models (o-series,
#     gpt-5.x) require max_completion_tokens and 400 on max_tokens.
#     Everyone else still takes max_tokens.
#   - supports_sampling_params: OpenAI's reasoning models reject
#     temperature/top_p/presence_penalty/frequency_penalty/logit_bias/
#     logprobs outright when reasoning is active.
#   - reasoning: see _REASONING_STRATEGIES below; None means "don't
#     configure it, let the model default apply."

@dataclass
class ProviderCapabilities:
    supports_parallel_tool_calls: bool = True
    max_tokens_param: str = "max_tokens"          # or "max_completion_tokens"
    supports_sampling_params: bool = True          # temperature/top_p/etc.
    reasoning_strategy: Optional[Callable[[str, Dict[str, Any], str], None]] = None
    # Called as reasoning_replay(meta, had_tool_calls, msg, model) when
    # rebuilding a past assistant turn for the *next* outgoing request.
    # See the big comment block below — this is a genuinely different
    # problem from reasoning_strategy above: that one asks for reasoning,
    # this one hands the model's own prior reasoning back to it.
    reasoning_replay: Optional[Callable[[Optional[Dict[str, Any]], bool, Dict[str, Any], str], None]] = None


# ── Reasoning REPLAY strategies ─────────────────────────────────────
#
# Separate problem from reasoning_strategy above. That configures the
# *request* ("please think"). This configures how a *previously returned*
# reasoning payload gets reattached to that assistant turn when it's
# replayed as history in a later request — and providers disagree hard
# here, to the point of contradicting each other:
#
#   - OpenAI direct (chat completions): never returns reasoning content
#     over this endpoint at all, so there is nothing to replay. No-op.
#   - Legacy DeepSeek (`deepseek-reasoner`): replaying reasoning_content
#     is FORBIDDEN — including it causes a 400. Must omit.
#   - DeepSeek V4 (`deepseek-v4-pro`/`deepseek-v4-flash`): the OPPOSITE
#     rule — on any turn where a tool call happened, reasoning_content
#     MUST be echoed back verbatim as its own field or the next request
#     400s. On non-tool turns it's optional/ignored. Same provider family,
#     opposite requirement depending on model generation — this is model-
#     name-aware, not just provider-aware.
#   - OpenRouter (reasoning-capable underlying model + tools): must replay
#     the `reasoning_details` array it returned, largely unmodified, once
#     tool calls are involved, or the underlying provider (esp. Gemini/
#     Anthropic) can 400 or silently drop assistant content on the next
#     turn. Gemini's entries in that array carry an opaque encrypted
#     "thought signature" — treat as an opaque blob, never inspect/mutate.
#   - Anthropic's own OpenAI-compat layer: does not expose the actual
#     thinking content back through the compat response shape, so there
#     is nothing to capture or replay via this code path.
#   - NVIDIA NIM / vLLM / DeepSeek-distilled open-weight deployments:
#     generally just want *some* text back, not a specific field or
#     structure — the old inline 123 merge remains a safe default here.
#
# Every one of these is a real, cited failure mode (400s reported by
# multiple independent tools against DeepSeek V4, OpenRouter+Gemini, and
# OpenRouter+Anthropic specifically once tool calls entered the picture).

_STANDARD_MESSAGE_KEYS = {"role", "content", "tool_calls", "refusal", "function_call", "audio", "name"}


def _extract_reasoning_meta(raw_message_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Anything beyond the standard OpenAI message shape is provider-
    specific reasoning/thinking metadata (reasoning, reasoning_content,
    reasoning_details, signature, thought_signature, etc.). openai-python's
    models allow extra fields through (extra="allow"), so whatever the
    provider actually sent back survives model_dump() as long as we grab
    it here before anything downstream trims the dict to "known" keys."""
    return {k: v for k, v in raw_message_dict.items() if k not in _STANDARD_MESSAGE_KEYS}


def _replay_omit(meta: Optional[Dict[str, Any]], had_tool_calls: bool,
                  msg: Dict[str, Any], model: str) -> None:
    """Nothing to replay — either the endpoint never returned reasoning
    content in the first place, or the provider forbids sending it back."""
    return


def _replay_deepseek(meta: Optional[Dict[str, Any]], had_tool_calls: bool,
                      msg: Dict[str, Any], model: str) -> None:
    """Model-generation-aware, not just provider-aware: legacy
    deepseek-reasoner forbids replay entirely; DeepSeek V4 requires it,
    but only on turns that had a tool call."""
    is_v4 = "v4" in (model or "").lower()
    if not is_v4:
        return  # legacy deepseek-reasoner: sending this back causes a 400
    if had_tool_calls and meta and meta.get("reasoning_content"):
        msg["reasoning_content"] = meta["reasoning_content"]


def _replay_openrouter(meta: Optional[Dict[str, Any]], had_tool_calls: bool,
                        msg: Dict[str, Any], model: str) -> None:
    """Replay the reasoning_details array verbatim — treat every entry as
    an opaque blob (this is where Gemini's thought signatures live) and
    never construct or edit one by hand. Only needed once tool calls are
    involved; omitting on plain turns is safe."""
    if had_tool_calls and meta and meta.get("reasoning_details"):
        msg["reasoning_details"] = meta["reasoning_details"]


def _replay_inline_think_text(meta: Optional[Dict[str, Any]], had_tool_calls: bool,
                               msg: Dict[str, Any], model: str) -> None:
    """Safe fallback for open-weight deployments (vLLM/NVIDIA NIM) that
    just want some text back, not a specific field or validated structure.
    This was the previous universal behavior — now scoped to providers
    that actually tolerate it."""
    text = (meta or {}).get("reasoning") or (meta or {}).get("reasoning_content")
    if not text:
        return
    existing = msg.get("content") or ""
    msg["content"] = (f"💭\n{text}\n✨\n\n{existing}" if existing
                       else f"💭\n{text}\n✨")


# ── Reasoning-effort strategies ─────────────────────────────────────
#
# Every provider that supports "thinking"/"reasoning" wants it configured
# a different way over the wire, even though most of them now converge on
# the same *concept*: a canonical effort level of "none" | "low" | "medium"
# | "high". Agent Setup stores just that canonical string; these functions
# are the only place that needs to know how to translate it per provider.
#
# Sources checked:
#   - OpenAI direct: top-level `reasoning_effort` on o-series/gpt-5.x.
#   - OpenRouter: unified `extra_body={"reasoning": {"effort": ...}}`.
#   - Gemini via its OpenAI-compat endpoint: also accepts top-level
#     `reasoning_effort` directly (mapped server-side to thinking_level).
#   - NVIDIA NIM / vLLM / DeepSeek-style open-weight deployments: binary
#     on/off via `extra_body={"chat_template_kwargs": {"enable_thinking": bool}}`,
#     no effort levels.
#   - xAI Grok (mini/fast-reasoning variants): top-level `reasoning_effort`.
#   - Anthropic's OpenAI-compat layer: `extra_body={"thinking": {"type":
#     "enabled", "budget_tokens": N}}` — a token budget, not an effort
#     word, and it does NOT return the thought content back through the
#     OpenAI-shaped response (on_reasoning will simply never fire there).

def _reasoning_openai_style(effort: str, kwargs: Dict[str, Any], model: str) -> None:
    """OpenAI, Gemini-via-OpenAI-compat, and xAI Grok all accept a
    top-level reasoning_effort string directly."""
    kwargs["reasoning_effort"] = effort


def _reasoning_openrouter(effort: str, kwargs: Dict[str, Any], model: str) -> None:
    extra_body = kwargs.setdefault("extra_body", {})
    extra_body["reasoning"] = {"effort": effort}


def _reasoning_chat_template_toggle(effort: str, kwargs: Dict[str, Any], model: str) -> None:
    """NVIDIA NIM / vLLM / DeepSeek-style deployments: no effort levels,
    just an on/off switch. Anything other than "none" enables it."""
    extra_body = kwargs.setdefault("extra_body", {})
    extra_body.setdefault("chat_template_kwargs", {})["enable_thinking"] = effort != "none"


_EFFORT_TO_ANTHROPIC_BUDGET = {"low": 1024, "medium": 4096, "high": 16000}


def _reasoning_anthropic_compat(effort: str, kwargs: Dict[str, Any], model: str) -> None:
    """Anthropic's OpenAI-compat layer uses a token budget, not a word,
    and "none" has no equivalent — thinking is either on with a budget or
    simply not requested at all."""
    if effort == "none":
        return
    extra_body = kwargs.setdefault("extra_body", {})
    extra_body["thinking"] = {
        "type": "enabled",
        "budget_tokens": _EFFORT_TO_ANTHROPIC_BUDGET.get(effort, 4096),
    }


# ── The capability table itself ─────────────────────────────────────
# Provider names must match whatever get_provider()/registry.py returns.
#
# supports_parallel_tool_calls now means: "this provider can handle multiple
# tool calls in a single response and execute them correctly". When True,
# we allow the model to make parallel calls (don't restrict it). When False,
# we explicitly set parallel_tool_calls=False to prevent the model from
# attempting parallel calls that the provider can't handle.

_PROVIDER_CAPS: Dict[str, ProviderCapabilities] = {
    "openai": ProviderCapabilities(
        supports_parallel_tool_calls=True,  # Full support for parallel tool calls
        max_tokens_param="max_completion_tokens",
        supports_sampling_params=False,
        reasoning_strategy=_reasoning_openai_style,
        reasoning_replay=_replay_omit,  # chat completions never returns reasoning content
    ),
    "gemini": ProviderCapabilities(
        supports_parallel_tool_calls=True,  # Gemini supports parallel tool calls
        reasoning_strategy=_reasoning_openai_style,
        # NOTE: unverified for the direct OpenAI-compat endpoint (as opposed
        # to Gemini-via-OpenRouter, where thought-signature replay is a hard
        # requirement once tools are involved). Defaulting to omit is the
        # conservative choice — if you see degraded multi-turn tool-calling
        # quality specifically on Gemini direct, check whether its compat
        # layer exposes a signature field and wire a replay fn for it.
        reasoning_replay=_replay_omit,
    ),
    "xai": ProviderCapabilities(
        supports_parallel_tool_calls=True,  # xAI Grok supports parallel calls
        reasoning_strategy=_reasoning_openai_style,
        reasoning_replay=_replay_omit,
    ),
    "openrouter": ProviderCapabilities(
        supports_parallel_tool_calls=True,  # Passes through to underlying provider
        reasoning_strategy=_reasoning_openrouter,
        reasoning_replay=_replay_openrouter,
    ),
    "anthropic": ProviderCapabilities(
        supports_parallel_tool_calls=False,  # Anthropic's compat layer is unreliable with parallel calls
        reasoning_strategy=_reasoning_anthropic_compat,
        reasoning_replay=_replay_omit,  # compat layer doesn't expose thinking content back anyway
    ),
    "nvidia": ProviderCapabilities(
        supports_parallel_tool_calls=True,  # NVIDIA NIM supports parallel calls
        reasoning_strategy=_reasoning_chat_template_toggle,
        reasoning_replay=_replay_inline_think_text,
    ),
    "vllm": ProviderCapabilities(
        supports_parallel_tool_calls=True,  # vLLM supports parallel calls (parameter is no-op but calls work)
        reasoning_strategy=_reasoning_chat_template_toggle,
        reasoning_replay=_replay_inline_think_text,
    ),
    "deepseek": ProviderCapabilities(
        supports_parallel_tool_calls=True,  # DeepSeek supports parallel tool calls
        reasoning_strategy=_reasoning_chat_template_toggle,
        reasoning_replay=_replay_deepseek,
    ),
}
_DEFAULT_CAPS = ProviderCapabilities(
    supports_parallel_tool_calls=True,  # Default to allowing parallel calls
    reasoning_replay=_replay_inline_think_text
)

# Called with each raw text delta as it streams in. Sync or async both fine.
TokenCallback = Optional[Callable[[str], Any]]


class OpenAIProvider:
    def __init__(self) -> None:
        agent_setup = frappe.get_doc("Agent Setup")
        provider = get_provider((agent_setup.provider or "").lower() or "openrouter")
        model = agent_setup.model
        self.provider = provider
        self.model = model
        self.caps = _PROVIDER_CAPS.get(provider, _DEFAULT_CAPS)
        # Canonical effort level: "none" | "low" | "medium" | "high".
        # Translated per-provider via self.caps.reasoning_strategy at
        # request time — add a field on Agent Setup for this if it
        # doesn't exist yet.
        self.reasoning_effort = (getattr(agent_setup, "reasoning_effort", None) or "").lower() or None
        self.client = AsyncOpenAI(
            api_key=agent_setup.get_password("api_key"),
            base_url=provider.base_url,
        )

    def replay_reasoning(self, meta: Optional[Dict[str, Any]], had_tool_calls: bool,
                          msg: Dict[str, Any]) -> None:
        """Bound entry point Conversation.get_messages() calls per assistant
        row when rebuilding history for the next outgoing request. Delegates
        to this provider's registered strategy (see reasoning_replay
        strategies above), already knowing which provider and model it is."""
        if self.caps.reasoning_replay is not None:
            self.caps.reasoning_replay(meta, had_tool_calls, msg, self.model)

    async def generate(
        self,
        messages: MessageList,
        tools: Optional[List[Dict[str, Any]]] = None,
        on_token: TokenCallback = None,
        on_reasoning: TokenCallback = None,
    ) -> Tuple[Message, Any]:
        """
        Sends a chat completion request and returns:
          (message_dict, tool_calls)

        message_dict is a plain dict safe to append to conversation history.
        tool_calls is None when the model is done.

        If on_token and/or on_reasoning is provided, the request is
        streamed. on_token(delta) fires for visible answer text; on_reasoning
        (delta) fires separately for the model's chain-of-thought, on
        providers/models that expose one (OpenRouter's unified `reasoning`
        delta field, or vLLM/DeepSeek-style `reasoning_content`). Models
        that don't support reasoning simply never call on_reasoning — the
        caller doesn't need to know in advance whether the model reasons.

        The final return value is identical across all modes — streaming
        is purely a side channel for live UI updates, callers don't need
        to branch on it. If reasoning text was produced, message_dict also
        carries a "reasoning" key alongside "content".

        Retries on transient errors (429, 5xx, network) with exponential
        backoff + jitter. Raises immediately on permanent errors. Note:
        once a stream has emitted partial tokens to on_token/on_reasoning,
        a retry of that attempt will re-emit from the start — callers doing
        UI streaming should treat each attempt's tokens as belonging to a
        single in-progress bubble, not append-only across retries.
        
        PARALLEL TOOL CALLS: When the provider supports it (see
        supports_parallel_tool_calls), the model may return multiple tool
        calls in a single response. These are returned as a list and the
        caller (Agent) is responsible for executing them concurrently.
        """
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
        }

        # Sampling params some callers may add later (temperature, etc.)
        # go through the same capability gate as everything else — strip
        # them up front if this provider's reasoning models reject them.
        if not self.caps.supports_sampling_params:
            for unsupported in ("temperature", "top_p", "presence_penalty",
                                "frequency_penalty", "logit_bias", "logprobs"):
                kwargs.pop(unsupported, None)

        # max_tokens vs max_completion_tokens naming, if the caller set one.
        if self.caps.max_tokens_param != "max_tokens" and "max_tokens" in kwargs:
            kwargs[self.caps.max_tokens_param] = kwargs.pop("max_tokens")

        # Provider-agnostic reasoning config: look up how *this* provider
        # wants effort expressed and let it mutate kwargs accordingly.
        # No strategy registered, or no effort configured → left alone,
        # the model's own default behavior applies.
        if self.reasoning_effort and self.caps.reasoning_strategy is not None:
            self.caps.reasoning_strategy(self.reasoning_effort, kwargs, self.model)
        elif self.reasoning_effort:
            logger.info(
                "No reasoning strategy registered for provider %r — "
                "reasoning_effort=%r was requested but will not be sent.",
                self.provider, self.reasoning_effort,
            )

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
            
            # Only restrict parallel_tool_calls when the provider explicitly
            # does NOT support it. When supports_parallel_tool_calls is True,
            # we let the model decide whether to make parallel calls (omit
            # the parameter or let it default to True).
            # 
            # Note: For OpenAI with reasoning_effort="minimal", we still
            # need to disable parallel calls as that specific mode rejects it.
            should_disable_parallel = (
                not self.caps.supports_parallel_tool_calls or
                (self.provider == "openai" and kwargs.get("reasoning_effort") == "minimal")
            )
            if should_disable_parallel:
                kwargs["parallel_tool_calls"] = False

        last_exc: Optional[Exception] = None

        for attempt in range(_MAX_RETRIES):
            try:
                if on_token is not None or on_reasoning is not None:
                    return await self._generate_streaming(kwargs, on_token, on_reasoning)
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
        raw_dict = message.model_dump(exclude_none=True)

        # Grab everything provider-specific BEFORE normalizing, so nothing
        # needed for later replay gets lost or renamed away.
        reasoning_meta = _extract_reasoning_meta(raw_dict)

        message_dict: Message = {k: v for k, v in raw_dict.items()
                                  if k in _STANDARD_MESSAGE_KEYS}

        # Token usage + resolved model, for Agent Message telemetry fields.
        # response.model may differ from the requested self.model (provider
        # can resolve aliases/snapshots), so prefer what actually ran.
        message_dict["model"] = getattr(response, "model", None) or self.model
        usage = getattr(response, "usage", None)
        if usage is not None:
            message_dict["usage"] = usage.model_dump(exclude_none=True)
        # Some providers (OpenRouter unified, DeepSeek-style vLLM deployments)
        # put chain-of-thought on a non-standard field; normalize the two
        # known field names into a single "reasoning" key for display/UI
        # purposes (on_reasoning, timeline reconstruction). This is separate
        # from reasoning_meta, which keeps the raw provider shape intact.
        reasoning_text = raw_dict.get("reasoning") or raw_dict.get("reasoning_content")
        if reasoning_text:
            message_dict["reasoning"] = reasoning_text
        if reasoning_meta:
            message_dict["reasoning_meta"] = reasoning_meta
        return message_dict, getattr(message, "tool_calls", None)

    # ── Streaming path ─────────────────────────────────────────────────

    async def _generate_streaming(
        self,
        kwargs: Dict[str, Any],
        on_token: Optional[Callable[[str], Any]],
        on_reasoning: Optional[Callable[[str], Any]] = None,
    ) -> Tuple[Message, Any]:
        stream = await self.client.chat.completions.create(
            **kwargs, stream=True,
            stream_options={"include_usage": True},
        )

        content_parts: List[str] = []
        reasoning_parts: List[str] = []
        usage_dict: Optional[Dict[str, Any]] = None
        resolved_model: Optional[str] = None
        # Best-effort capture of structured reasoning metadata (OpenRouter's
        # reasoning_details array, Gemini-style thought signatures). Unlike
        # plain text deltas, providers don't standardize how these fragment
        # across chunks — some resend the full cumulative array on every
        # chunk near the end rather than incrementally patching it, so we
        # just keep the latest non-empty value seen for each key rather than
        # trying to merge/append them.
        reasoning_meta_parts: Dict[str, Any] = {}
        # tool_calls arrive as index-addressed fragments that must be
        # reassembled: {0: {"id": ..., "name": ..., "arguments": "..."}}
        tool_call_frags: Dict[int, Dict[str, Any]] = {}
        finish_reason: Optional[str] = None
        role = "assistant"

        async for chunk in stream:
            if getattr(chunk, "model", None):
                resolved_model = chunk.model
            chunk_usage = getattr(chunk, "usage", None)
            if chunk_usage is not None:
                # The include_usage final chunk carries usage and typically
                # has an empty choices list — must capture it here, before
                # the choices-empty check below would otherwise skip it.
                usage_dict = chunk_usage.model_dump(exclude_none=True)

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

            # Reasoning/chain-of-thought delta. Different providers use
            # different field names for the same concept:
            #   - OpenRouter's unified field: delta.reasoning
            #   - DeepSeek-R1 / many vLLM deployments: delta.reasoning_content
            # Check both; whichever is present (if any) wins. Models that
            # don't support reasoning simply never set either, so this is a
            # no-op for them.
            reasoning_delta = getattr(delta, "reasoning", None) or getattr(delta, "reasoning_content", None)
            if reasoning_delta:
                reasoning_parts.append(reasoning_delta)
                if on_reasoning is not None:
                    result = on_reasoning(reasoning_delta)
                    if asyncio.iscoroutine(result):
                        await result

            # Structured metadata needed for later replay — see comment
            # above reasoning_meta_parts. Treat as an opaque blob; never
            # inspect or construct these ourselves.
            details = getattr(delta, "reasoning_details", None)
            if details:
                reasoning_meta_parts["reasoning_details"] = details
            signature = getattr(delta, "signature", None) or getattr(delta, "thought_signature", None)
            if signature:
                reasoning_meta_parts["signature"] = signature

            if delta.content:
                content_parts.append(delta.content)
                if on_token is not None:
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
        reasoning = "".join(reasoning_parts)
        tool_calls = None
        if tool_call_frags:
            ordered = [tool_call_frags[i] for i in sorted(tool_call_frags)]
            tool_calls = [_DeltaToolCall(t) for t in ordered]

        message_dict: Message = {"role": role, "content": content or None}
        if reasoning:
            message_dict["reasoning"] = reasoning
        reasoning_meta = dict(reasoning_meta_parts)
        if reasoning and "reasoning_content" not in reasoning_meta:
            # keep a plain-text copy under the raw key too, so
            # DeepSeek-style replay (which reads meta["reasoning_content"])
            # works even when only the plain delta.reasoning_content path
            # fired and no structured details were ever seen.
            reasoning_meta["reasoning_content"] = reasoning
        if reasoning_meta:
            message_dict["reasoning_meta"] = reasoning_meta
        if tool_call_frags:
            message_dict["tool_calls"] = [tc.copy() for tc in
                                           [tool_call_frags[i] for i in sorted(tool_call_frags)]]
        message_dict["model"] = resolved_model or self.model
        if usage_dict is not None:
            message_dict["usage"] = usage_dict
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