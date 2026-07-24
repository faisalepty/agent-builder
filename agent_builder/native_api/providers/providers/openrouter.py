"""OpenRouter provider — config + reasoning strategies."""

from __future__ import annotations

from typing import Any, Dict, Optional

from agent_builder.native_api.providers.provider import make_config
from agent_builder.native_api.providers.providers._shared.effort import reasoning_openrouter


def replay_openrouter(
	meta: dict[str, Any] | None,
	had_tool_calls: bool,
	msg: dict[str, Any],
	model: str,
) -> None:
	"""Replay the reasoning_details array verbatim — treat every entry
	as an opaque blob (Gemini's thought signatures live here).
	Only needed once tool calls are involved."""
	if had_tool_calls and meta and meta.get("reasoning_details"):
		msg["reasoning_details"] = meta["reasoning_details"]


OpenRouterProviderConfig = make_config(
	name="openrouter",
	base_url="https://openrouter.ai/api/v1",
	reasoning_strategy=reasoning_openrouter,
	reasoning_replay=replay_openrouter,
	supports_stream_options=True,
	supports_parallel_tool_calls=True,
)
