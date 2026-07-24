"""Anthropic provider — config + reasoning strategies."""

from agent_builder.native_api.providers.provider import make_config
from agent_builder.native_api.providers.providers._shared import replay_omit
from agent_builder.native_api.providers.providers._shared.effort import reasoning_anthropic_compat

AnthropicProviderConfig = make_config(
	name="anthropic",
	base_url="https://api.anthropic.com/v1",
	reasoning_strategy=reasoning_anthropic_compat,
	reasoning_replay=replay_omit,
	supports_parallel_tool_calls=False,
)
