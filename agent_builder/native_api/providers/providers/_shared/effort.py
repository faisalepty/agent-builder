"""Shared reasoning-effort strategies reused by multiple providers."""

from __future__ import annotations

from typing import Any, Dict


def reasoning_openai_style(effort: str, kwargs: dict[str, Any], model: str) -> None:
	"""OpenAI, Gemini-via-OpenAI-compat, xAI Grok, Nebius, HuggingFace, and
	others accept a top-level `reasoning_effort` string directly.

	Verified effort vocabularies differ per provider but all accept a plain
	string, so we forward it unchanged and let the endpoint validate:
	  - OpenAI:  none/minimal/low/medium/high/xhigh/max
	  - xAI:     none/low/medium/high
	  - Google:  none/minimal/low/medium/high
	  - Nebius:  none/minimal/low/medium/high/xhigh/max
	  - HF:      none/minimal/low/medium/high/xhigh
	"""
	kwargs["reasoning_effort"] = effort


def reasoning_openrouter(effort: str, kwargs: dict[str, Any], model: str) -> None:
	"""OpenRouter normalizes thinking across all upstream providers behind a
	single `reasoning` object. Send via extra_body, never as a top-level
	`reasoning_effort` (the gateway rejects the pair together).

	Verified values: none/minimal/low/medium/high/xhigh/max.
	Ref: https://openrouter.ai/docs/guides/best-practices/reasoning-tokens
	"""
	extra_body = kwargs.setdefault("extra_body", {})
	extra_body["reasoning"] = {"effort": effort}


def reasoning_chat_template_toggle(effort: str, kwargs: dict[str, Any], model: str) -> None:
	"""NVIDIA NIM / vLLM / DeepSeek-style deployments: no graded effort levels,
	just an on/off switch via `chat_template_kwargs.enable_thinking`.

	Ref: https://docs.nvidia.com/nim/large-language-models/latest/reasoning-model.html
	"""
	extra_body = kwargs.setdefault("extra_body", {})
	extra_body.setdefault("chat_template_kwargs", {})["enable_thinking"] = effort != "none"


def reasoning_anthropic_compat(effort: str, kwargs: dict[str, Any], model: str) -> None:
	"""Anthropic's OpenAI-compat layer uses a token *budget*, not an effort string.

	IMPORTANT (verified 2026-07): on Claude Opus 4.7 `budget_tokens` is rejected
	(400) and only adaptive thinking is supported; for 4.6 and earlier the
	budget_tokens shape is still the documented compat behaviour. We keep the
	budget mapping for the compat layer but map "none" to a no-op (thinking off).
	"""
	if effort == "none":
		return
	extra_body = kwargs.setdefault("extra_body", {})
	extra_body["thinking"] = {
		"type": "enabled",
		"budget_tokens": {"low": 1024, "medium": 4096, "high": 16000}.get(effort, 4096),
	}
