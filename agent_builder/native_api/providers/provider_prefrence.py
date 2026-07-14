# native_api/providers/provider_prefrence.py

"""Reasoning-effort and reasoning-replay strategies.

Every provider that supports "thinking" wants it configured differently
over the wire, even though most converge on the same *concept*: a
canonical effort level of "none" | "low" | "medium" | "high".

REPLAY is a separate concern from EFFORT:
  - Effort strategies configure the *outgoing request* ("please think").
  - Replay strategies configure how a *previously returned* reasoning
    payload gets reattached to an assistant turn when it's replayed as
    history in a later request.

Providers disagree hard on replay — to the point of contradicting each
other:
  - OpenAI direct: never returns reasoning over chat completions → no-op.
  - Legacy DeepSeek (deepseek-reasoner): replaying reasoning_content is
    FORBIDDEN — including it causes a 400.
  - DeepSeek V4: the OPPOSITE — reasoning_content MUST be echoed back
    verbatim on tool-call turns or the next request 400s.
  - OpenRouter: must replay reasoning_details array (contains Gemini's
    opaque encrypted "thought signature") once tool calls are involved.
  - Anthropic compat: doesn't expose thinking content back through the
    compat response shape → nothing to replay.
  - NVIDIA NIM / vLLM / open-weight: just want *some* text back, no
    specific field required.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

# ── Reasoning-effort strategies ────────────────────────────────────
# Each receives (effort: str, kwargs: Dict, model: str) and mutates
# kwargs in-place to add the provider-specific reasoning configuration.

ReasoningEffortStrategy = Callable[[str, Dict[str, Any], str], None]
ReasoningReplayStrategy = Callable[
    [Optional[Dict[str, Any]], bool, Dict[str, Any], str], None
]


def reasoning_openai_style(
    effort: str, kwargs: Dict[str, Any], model: str
) -> None:
    """OpenAI, Gemini-via-OpenAI-compat, and xAI Grok all accept a
    top-level reasoning_effort string directly."""
    kwargs["reasoning_effort"] = effort


def reasoning_openrouter(
    effort: str, kwargs: Dict[str, Any], model: str
) -> None:
    extra_body = kwargs.setdefault("extra_body", {})
    extra_body["reasoning"] = {"effort": effort}


def reasoning_chat_template_toggle(
    effort: str, kwargs: Dict[str, Any], model: str
) -> None:
    """NVIDIA NIM / vLLM / DeepSeek-style deployments: no effort levels,
    just an on/off switch via chat_template_kwargs.enable_thinking."""
    extra_body = kwargs.setdefault("extra_body", {})
    extra_body.setdefault("chat_template_kwargs", {})[
        "enable_thinking"
    ] = effort != "none"


_EFFORT_TO_ANTHROPIC_BUDGET = {"low": 1024, "medium": 4096, "high": 16000}


def reasoning_anthropic_compat(
    effort: str, kwargs: Dict[str, Any], model: str
) -> None:
    """Anthropic's OpenAI-compat layer uses a token budget, not a word.
    "none" has no equivalent — thinking is either on with a budget or
    not requested at all. Does NOT return thought content back through
    the OpenAI-shaped response."""
    if effort == "none":
        return
    extra_body = kwargs.setdefault("extra_body", {})
    extra_body["thinking"] = {
        "type": "enabled",
        "budget_tokens": _EFFORT_TO_ANTHROPIC_BUDGET.get(effort, 4096),
    }


# ── Reasoning-replay strategies ────────────────────────────────────
# Each receives (meta, had_tool_calls, msg, model) and mutates msg
# in-place to attach the provider-specific reasoning payload.

def replay_omit(
    meta: Optional[Dict[str, Any]],
    had_tool_calls: bool,
    msg: Dict[str, Any],
    model: str,
) -> None:
    """Nothing to replay — endpoint never returned reasoning content,
    or the provider forbids sending it back."""
    return


def replay_deepseek(
    meta: Optional[Dict[str, Any]],
    had_tool_calls: bool,
    msg: Dict[str, Any],
    model: str,
) -> None:
    """Model-generation-aware, not just provider-aware:
      - Legacy deepseek-reasoner: sending reasoning_content back → 400.
      - DeepSeek V4: on tool-call turns, reasoning_content MUST be
        echoed back verbatim or the next request 400s.
        On non-tool turns it's optional/ignored."""
    is_v4 = "v4" in (model or "").lower()
    if not is_v4:
        return
    if had_tool_calls and meta and meta.get("reasoning_content"):
        msg["reasoning_content"] = meta["reasoning_content"]


def replay_openrouter(
    meta: Optional[Dict[str, Any]],
    had_tool_calls: bool,
    msg: Dict[str, Any],
    model: str,
) -> None:
    """Replay the reasoning_details array verbatim — treat every entry
    as an opaque blob (Gemini's thought signatures live here).
    Only needed once tool calls are involved; omitting on plain turns
    is safe."""
    if had_tool_calls and meta and meta.get("reasoning_details"):
        msg["reasoning_details"] = meta["reasoning_details"]


def replay_inline_think_text(
    meta: Optional[Dict[str, Any]],
    had_tool_calls: bool,
    msg: Dict[str, Any],
    model: str,
) -> None:
    """Safe fallback for open-weight deployments (vLLM / NVIDIA NIM)
    that just want some text back, not a specific field or structure."""
    text = (meta or {}).get("reasoning") or (meta or {}).get("reasoning_content")
    if not text:
        return
    existing = msg.get("content") or ""
    msg["content"] = f"{text}\n\n{existing}" if existing else text