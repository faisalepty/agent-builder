"""NVIDIA NIM provider — config + reasoning strategies."""

from __future__ import annotations

from typing import Any, Dict, Optional

from agent_builder.native_api.providers.provider import make_config
from agent_builder.native_api.providers.providers._shared.effort import reasoning_chat_template_toggle


def replay_inline_think_text(
	meta: dict[str, Any] | None,
	had_tool_calls: bool,
	msg: dict[str, Any],
	model: str,
) -> None:
	"""Safe fallback for open-weight deployments (Nemotron, etc.) that
	just want some thinking text back — inline the `<think:6124c78e>`
	text into content."""
	text = (meta or {}).get("reasoning") or (meta or {}).get("reasoning_content")
	if not text:
		return
	existing = msg.get("content") or ""
	msg["content"] = f"{text}\n\n{existing}" if existing else text


NVIDIAProviderConfig = make_config(
	name="nvidia",
	base_url="https://integrate.api.nvidia.com/v1",
	reasoning_strategy=reasoning_chat_template_toggle,
	reasoning_replay=replay_inline_think_text,
	supports_parallel_tool_calls=True,
)
