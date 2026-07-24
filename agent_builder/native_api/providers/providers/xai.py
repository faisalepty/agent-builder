"""xAI Grok provider — config + reasoning strategies."""

from __future__ import annotations

from typing import Any, Dict, Optional

from agent_builder.native_api.providers.provider import make_config
from agent_builder.native_api.providers.providers._shared.effort import reasoning_openai_style


def replay_grok_encrypted(
	meta: dict[str, Any] | None,
	had_tool_calls: bool,
	msg: dict[str, Any],
	model: str,
) -> None:
	"""Grok returns encrypted thinking that must be replayed verbatim on
	tool-call turns to continue the reasoning session. Echo the raw
	`reasoning` (encrypted) payload back if present."""
	reasoning = (meta or {}).get("reasoning")
	if reasoning and had_tool_calls:
		msg["reasoning"] = reasoning


XAIProviderConfig = make_config(
	name="xai",
	base_url="https://api.x.ai/v1",
	reasoning_strategy=reasoning_openai_style,
	reasoning_replay=replay_grok_encrypted,
	supports_parallel_tool_calls=True,
)
