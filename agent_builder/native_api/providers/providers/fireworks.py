"""Fireworks provider — config + reasoning strategies."""

from agent_builder.native_api.providers.provider import make_config
from agent_builder.native_api.providers.providers._shared import replay_omit
from agent_builder.native_api.providers.providers._shared.effort import reasoning_openai_style

FireworksProviderConfig = make_config(
	name="fireworks",
	base_url="https://api.fireworks.ai/inference/v1",
	reasoning_strategy=reasoning_openai_style,
	reasoning_replay=replay_omit,
)
