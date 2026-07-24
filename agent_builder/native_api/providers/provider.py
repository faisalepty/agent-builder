"""Provider dataclass — shared shape for every provider configuration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Dict, Optional


def make_config(
	name: str,
	base_url: str,
	reasoning_strategy: Callable | None = None,
	reasoning_replay: Callable | None = None,
	*,
	supports_stream_options: bool = False,
	supports_parallel_tool_calls: bool = True,
	max_tokens_param: str = "max_tokens",
	supports_sampling_params: bool = True,
	disables_parallel_for_minimal_reasoning: bool = False,
) -> Provider:
	"""Convenience constructor for provider config modules.

	Keeps per-provider config files to a single declarative call instead of
	repeating the `Provider(...)` import + field boilerplate 18 times.
	"""
	return Provider(
		name=name,
		base_url=base_url,
		supports_stream_options=supports_stream_options,
		supports_parallel_tool_calls=supports_parallel_tool_calls,
		max_tokens_param=max_tokens_param,
		supports_sampling_params=supports_sampling_params,
		disables_parallel_for_minimal_reasoning=disables_parallel_for_minimal_reasoning,
		reasoning_strategy=reasoning_strategy,
		reasoning_replay=reasoning_replay,
	)


@dataclass(frozen=True)
class Provider:
	"""Everything about a provider in one place.

	Fields are grouped by concern:
	  - Identity:     name, base_url
	  - Protocol:     supports_stream_options
	  - Inference:    supports_parallel_tool_calls, max_tokens_param,
	                  supports_sampling_params, disables_parallel_for_minimal_reasoning
	  - Reasoning:    reasoning_strategy, reasoning_replay
	"""

	# ── Identity ────────────────────────────────────────────────────
	name: str
	base_url: str

	# ── Protocol ────────────────────────────────────────────────────
	# Whether the provider accepts stream_options={"include_usage": True}.
	# Many OpenAI-compat endpoints (e.g. Mistral) reject it with 422.
	supports_stream_options: bool = False

	# ── Inference ───────────────────────────────────────────────────
	supports_parallel_tool_calls: bool = True
	# "max_tokens" (everyone else) or "max_completion_tokens" (OpenAI
	# reasoning models — they 400 on max_tokens).
	max_tokens_param: str = "max_tokens"
	# Whether sampling params (temperature, top_p, presence/frequency
	# penalty, logit_bias, logprobs) are accepted. OpenAI's reasoning
	# models reject all of these outright when reasoning is active.
	supports_sampling_params: bool = True
	# OpenAI-specific: minimal reasoning effort disables parallel tool calls.
	disables_parallel_for_minimal_reasoning: bool = False

	# ── Reasoning ───────────────────────────────────────────────────
	# Configures the outgoing request. Signature:
	#   (effort: str, kwargs: Dict, model: str) -> None
	reasoning_strategy: Callable | None = None
	# Reattaches previously returned reasoning metadata to an assistant
	# turn when replayed as history. Signature:
	#   (meta: Optional[Dict], had_tool_calls: bool, msg: Dict, model: str) -> None
	reasoning_replay: Callable | None = None
