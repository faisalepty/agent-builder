from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    base_url: str


PROVIDERS = {
    "openai": ProviderConfig(
        name="openai",
        base_url="https://api.openai.com/v1",
    ),

    "openrouter": ProviderConfig(
        name="openrouter",
        base_url="https://openrouter.ai/api/v1",
    ),

    "nvidia": ProviderConfig(
        name="nvidia",
        base_url="https://integrate.api.nvidia.com/v1",
    ),

    "groq": ProviderConfig(
        name="groq",
        base_url="https://api.groq.com/openai/v1",
    ),

    "together": ProviderConfig(
        name="together",
        base_url="https://api.together.xyz/v1",
    ),

    "fireworks": ProviderConfig(
        name="fireworks",
        base_url="https://api.fireworks.ai/inference/v1",
    ),

    "cerebras": ProviderConfig(
        name="cerebras",
        base_url="https://api.cerebras.ai/v1",
    ),

    "deepinfra": ProviderConfig(
        name="deepinfra",
        base_url="https://api.deepinfra.com/v1/openai",
    ),

    "deepseek": ProviderConfig(
        name="deepseek",
        base_url="https://api.deepseek.com/v1",
    ),

    "mistral": ProviderConfig(
        name="mistral",
        base_url="https://api.mistral.ai/v1",
    ),

    "nebius": ProviderConfig(
        name="nebius",
        base_url="https://api.studio.nebius.ai/v1",
    ),

    "huggingface": ProviderConfig(
        name="huggingface",
        base_url="https://router.huggingface.co/v1",
    ),

    "dashscope": ProviderConfig(
        name="dashscope",
        base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    ),

    "perplexity": ProviderConfig(
        name="perplexity",
        base_url="https://api.perplexity.ai",
    ),
}


def get_provider(name: str) -> ProviderConfig:
    return PROVIDERS.get(name.lower(), PROVIDERS["openrouter"])