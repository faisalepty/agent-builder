"""DeepSeek provider — config + reasoning strategies."""

from __future__ import annotations

from typing import Any, Dict, Optional

from agent_builder.native_api.providers.provider import make_config
from agent_builder.native_api.providers.providers._shared.effort import reasoning_openai_style


def replay_deepseek(
	meta: dict[str, Any] | None,
	had_tool_calls: bool,
	msg: dict[str, Any],
	model: str,
) -> None:
	"""Model-generation-aware, NOT just provider-aware:
	- Legacy deepseek-reasoner: sending reasoning_content back -> 400.
	- DeepSeek V4: on tool-call turns, reasoning_content MUST be
	  echoed back verbatim or the next request 400s.
	  On non-tool turns it's optional/ignored."""
	is_v4 = "v4" in (model or "").lower()
	if not is_v4:
		return
	if had_tool_calls and meta and meta.get("reasoning_content"):
		msg["reasoning_content"] = meta["reasoning_content"]


DeepSeekProviderConfig = make_config(
	name="deepseek",
	base_url="https://api.deepseek.com",
	reasoning_strategy=reasoning_openai_style,
	reasoning_replay=replay_deepseek,
	supports_parallel_tool_calls=True,
)
