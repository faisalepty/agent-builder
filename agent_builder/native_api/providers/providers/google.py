"""Google (Gemini) provider — config + reasoning strategies."""

from __future__ import annotations

from typing import Any, Dict, Optional

from agent_builder.native_api.providers.provider import make_config
from agent_builder.native_api.providers.providers._shared.effort import reasoning_openai_style


def replay_gemini_signature(
	meta: dict[str, Any] | None,
	had_tool_calls: bool,
	msg: dict[str, Any],
	model: str,
) -> None:
	"""Gemini 3.x emits a `thought_signature` that MUST be replayed on the
	assistant turn (always for tool-call turns, and in stateless mode for all
	turns) to preserve reasoning continuity. Echo it verbatim."""
	sig = (meta or {}).get("thought_signature")
	if not sig:
		return
	if had_tool_calls:
		msg["thought_signature"] = sig


GoogleProviderConfig = make_config(
	name="google",
	base_url="https://generativelanguage.googleapis.com/v1beta/openai",
	reasoning_strategy=reasoning_openai_style,
	reasoning_replay=replay_gemini_signature,
	supports_parallel_tool_calls=True,
)
