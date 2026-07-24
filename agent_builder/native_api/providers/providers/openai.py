"""OpenAI provider — config + reasoning strategies."""

from __future__ import annotations

from agent_builder.native_api.providers.provider import make_config
from agent_builder.native_api.providers.providers._shared import replay_omit
from agent_builder.native_api.providers.providers._shared.effort import reasoning_openai_style

OpenAIProviderConfig = make_config(
	name="openai",
	base_url="https://api.openai.com/v1",
	reasoning_strategy=reasoning_openai_style,
	reasoning_replay=replay_omit,
	supports_stream_options=True,
	supports_parallel_tool_calls=True,
	max_tokens_param="max_completion_tokens",
	supports_sampling_params=False,
	disables_parallel_for_minimal_reasoning=True,
)
