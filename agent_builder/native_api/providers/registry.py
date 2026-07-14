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

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from .provider_prefrence import (
    reasoning_openai_style,
    reasoning_openrouter,
    reasoning_chat_template_toggle,
    reasoning_anthropic_compat,
    replay_omit,
    replay_deepseek,
    replay_openrouter,
    replay_inline_think_text,
)


@dataclass(frozen=True)
class Provider:
    """Everything about a provider in one place.

    Fields are grouped by concern:
      - Identity:     name, base_url
      - Protocol:     supports_stream_options
      - Inference:    supports_parallel_tool_calls, max_tokens_param,
                      supports_sampling_params
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

    # ── Reasoning ───────────────────────────────────────────────────
    # Configures the outgoing request. Signature:
    #   (effort: str, kwargs: Dict, model: str) -> None
    reasoning_strategy: Optional[Callable] = None
    # Reattaches previously returned reasoning metadata to an assistant
    # turn when replayed as history. Signature:
    #   (meta: Optional[Dict], had_tool_calls: bool, msg: Dict, model: str) -> None
    reasoning_replay: Optional[Callable] = None


# ── The provider table ─────────────────────────────────────────────
# One entry per provider. Add a provider by adding one line here.

PROVIDERS: Dict[str, Provider] = {
    # ── First-party ────────────────────────────────────────────────
    "openai": Provider(
        name="openai",
        base_url="https://api.openai.com/v1",
        supports_stream_options=True,
        supports_parallel_tool_calls=True,
        max_tokens_param="max_completion_tokens",
        supports_sampling_params=False,
        reasoning_strategy=reasoning_openai_style,
        reasoning_replay=replay_omit,
    ),
    "anthropic": Provider(
        name="anthropic",
        base_url="https://api.anthropic.com/v1",
        supports_parallel_tool_calls=False,
        reasoning_strategy=reasoning_anthropic_compat,
        reasoning_replay=replay_omit,
    ),
    "google": Provider(
        name="google",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        supports_parallel_tool_calls=True,
        reasoning_strategy=reasoning_openai_style,
        reasoning_replay=replay_omit,
    ),
    "mistral": Provider(
        name="mistral",
        base_url="https://api.mistral.ai/v1",
    ),
    "xai": Provider(
        name="xai",
        base_url="https://api.x.ai/v1",
        supports_parallel_tool_calls=True,
        reasoning_strategy=reasoning_openai_style,
        reasoning_replay=replay_omit,
    ),
    "deepseek": Provider(
        name="deepseek",
        base_url="https://api.deepseek.com",
        supports_parallel_tool_calls=True,
        reasoning_strategy=reasoning_chat_template_toggle,
        reasoning_replay=replay_deepseek,
    ),

    # ── Gateways / routers ─────────────────────────────────────────
    "openrouter": Provider(
        name="openrouter",
        base_url="https://openrouter.ai/api/v1",
        supports_stream_options=True,
        supports_parallel_tool_calls=True,
        reasoning_strategy=reasoning_openrouter,
        reasoning_replay=replay_openrouter,
    ),

    # ── Fast inference ─────────────────────────────────────────────
    "groq": Provider(
        name="groq",
        base_url="https://api.groq.com/openai/v1",
    ),
    "cerebras": Provider(
        name="cerebras",
        base_url="https://api.cerebras.ai/v1",
    ),
    "fireworks": Provider(
        name="fireworks",
        base_url="https://api.fireworks.ai/inference/v1",
    ),
    "together": Provider(
        name="together",
        base_url="https://api.together.ai/v1",
    ),
    "deepinfra": Provider(
        name="deepinfra",
        base_url="https://api.deepinfra.com/v1/openai",
    ),

    # ── Enterprise / regional ──────────────────────────────────────
    "nvidia": Provider(
        name="nvidia",
        base_url="https://integrate.api.nvidia.com/v1",
        supports_parallel_tool_calls=True,
        reasoning_strategy=reasoning_chat_template_toggle,
        reasoning_replay=replay_inline_think_text,
    ),
    "huggingface": Provider(
        name="huggingface",
        base_url="https://router.huggingface.co/v1",
    ),
    "dashscope": Provider(
        name="dashscope",
        base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    ),
    "nebius": Provider(
        name="nebius",
        base_url="https://api.studio.nebius.ai/v1",
    ),

    # ── Self-hosted / inference engines ────────────────────────────
    "vllm": Provider(
        name="vllm",
        base_url="http://localhost:8000/v1",
        supports_parallel_tool_calls=True,
        reasoning_strategy=reasoning_chat_template_toggle,
        reasoning_replay=replay_inline_think_text,
    ),

    # ── Search-augmented ───────────────────────────────────────────
    "perplexity": Provider(
        name="perplexity",
        base_url="https://api.perplexity.ai",
    ),
}

_DEFAULT_PROVIDER_NAME = "openrouter"


def get_provider(name: str) -> Provider:
    """Look up a provider by name, defaulting to OpenRouter."""
    return PROVIDERS.get(
        (name or "").strip().lower(),
        PROVIDERS[_DEFAULT_PROVIDER_NAME],
    )