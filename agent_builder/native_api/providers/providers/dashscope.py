"""DashScope / Alibaba Model Studio — config + reasoning strategies."""

from agent_builder.native_api.providers.provider import make_config
from agent_builder.native_api.providers.providers._shared import replay_omit
from agent_builder.native_api.providers.providers._shared.effort import reasoning_openai_style

DashScopeProviderConfig = make_config(
	name="dashscope",
	base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
	reasoning_strategy=reasoning_openai_style,
	reasoning_replay=replay_omit,
)
