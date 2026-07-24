"""Shared reasoning-replay helpers used across multiple providers."""

from __future__ import annotations

from typing import Any, Dict, Optional


def replay_omit(
	meta: dict[str, Any] | None,
	had_tool_calls: bool,
	msg: dict[str, Any],
	model: str,
) -> None:
	"""Nothing to replay — endpoint never returned reasoning content,
	or the provider forbids sending it back."""
	return
