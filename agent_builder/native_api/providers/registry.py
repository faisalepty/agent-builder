# native_api/providers/registry.py

"""Provider registry — single source of truth for every provider.

Adding a new provider means adding ONE entry to PROVIDERS below.
Each entry bundles connection config (name, base_url) with behavioural
capabilities (reasoning, parallel tool calls, sampling, etc.) so the
client never needs to branch on provider name.

Base URLs verified against official docs as of 2025-07:
  - OpenAI:          https://platform.openai.com/docs/api-reference
  - OpenRouter:      https://openrouter.ai/docs/api/reference/overview
  - Anthropic:       https://docs.anthropic.com/en/api/messages
  - Mistral:         https://docs.mistral.ai/api/endpoint/chat
  - Google Gemini:   https://ai.google.dev/gemini-api/docs/openai
  - xAI Grok:        https://docs.x.ai/docs/api-reference
  - DeepSeek:        https://api-docs.deepseek.com (base WITHOUT /v1)
  - Groq:            https://console.groq.com/docs/openai
  - Cerebras:        https://inference-docs.cerebras.ai/resources/openai
  - Perplexity:      https://docs.perplexity.ai/docs/sonar/openai-compatibility
  - NVIDIA NIM:      https://docs.nvidia.com/nim/large-language-models
  - Fireworks:       https://docs.fireworks.ai/tools-sdks/openai-compatibility
  - Together:        https://docs.together.ai/docs/inference/openai-compatibility
  - DeepInfra:       https://docs.deepinfra.com/chat/overview
  - HuggingFace:     https://huggingface.co/docs/inference-providers
  - DashScope:       https://www.alibabacloud.com/help/en/model-studio/compatibility-of-openai-with-dashscope
  - Nebius:          https://docs.tokenfactory.nebius.com/quickstart
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Dict, Optional

from .provider import Provider
from .providers import (
	AnthropicProviderConfig,
	CerebrasProviderConfig,
	DashScopeProviderConfig,
	DeepInfraProviderConfig,
	DeepSeekProviderConfig,
	FireworksProviderConfig,
	GoogleProviderConfig,
	GroqProviderConfig,
	HuggingFaceProviderConfig,
	MistralProviderConfig,
	NebiusProviderConfig,
	NVIDIAProviderConfig,
	OpenAIProviderConfig,
	OpenRouterProviderConfig,
	PerplexityProviderConfig,
	TogetherProviderConfig,
	VLLMProviderConfig,
	XAIProviderConfig,
)

# ── The provider table ─────────────────────────────────────────────
# One entry per provider. Add a provider by adding one line here.

PROVIDERS: dict[str, Provider] = {
	# ── First-party ────────────────────────────────────────────────
	"openai": OpenAIProviderConfig,
	"anthropic": AnthropicProviderConfig,
	"google": GoogleProviderConfig,
	"mistral": MistralProviderConfig,
	"xai": XAIProviderConfig,
	"deepseek": DeepSeekProviderConfig,
	# ── Gateways / routers ─────────────────────────────────────────
	"openrouter": OpenRouterProviderConfig,
	# ── Fast inference ─────────────────────────────────────────────
	"groq": GroqProviderConfig,
	"cerebras": CerebrasProviderConfig,
	"fireworks": FireworksProviderConfig,
	"together": TogetherProviderConfig,
	"deepinfra": DeepInfraProviderConfig,
	# ── Enterprise / regional ──────────────────────────────────────
	"nvidia": NVIDIAProviderConfig,
	"huggingface": HuggingFaceProviderConfig,
	"dashscope": DashScopeProviderConfig,
	"nebius": NebiusProviderConfig,
	# ── Self-hosted / inference engines ────────────────────────────
	"vllm": VLLMProviderConfig,
	# ── Search-augmented ───────────────────────────────────────────
	"perplexity": PerplexityProviderConfig,
}

_DEFAULT_PROVIDER_NAME = "openrouter"


def get_provider(name: str) -> Provider:
	"""Look up a provider by name, defaulting to OpenRouter."""
	return PROVIDERS.get(
		(name or "").strip().lower(),
		PROVIDERS[_DEFAULT_PROVIDER_NAME],
	)
