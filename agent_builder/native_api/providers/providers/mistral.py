"""Mistral provider — config + reasoning strategies."""

from __future__ import annotations

from typing import Any, Dict, Optional

from agent_builder.native_api.providers.provider import make_config
from agent_builder.native_api.providers.providers._shared.effort import reasoning_openai_style


def replay_mistral_thinking_chunk(
	meta: dict[str, Any] | None,
	had_tool_calls: bool,
	msg: dict[str, Any],
	model: str,
) -> None:
	"""Mistral requires the full assistant message (including thinking chunks)
	to be replayed across turns; stripping the reasoning trace degrades
	coherence. Preserve the raw reasoning payload on tool-call turns."""
	reasoning = (meta or {}).get("reasoning") or (meta or {}).get("thinking")
	if reasoning and had_tool_calls:
		if "reasoning" not in msg:
			msg["reasoning"] = reasoning


MistralProviderConfig = make_config(
	name="mistral",
	base_url="https://api.mistral.ai/v1",
	reasoning_strategy=reasoning_openai_style,
	reasoning_replay=replay_mistral_thinking_chunk,
)
