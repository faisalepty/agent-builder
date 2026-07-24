"""Provider implementations package.

Each submodule defines one `<Name>ProviderConfig` instance. They are re-exported
here and assembled into the registry's PROVIDERS table.
"""

from .anthropic import AnthropicProviderConfig
from .cerebras import CerebrasProviderConfig
from .dashscope import DashScopeProviderConfig
from .deepinfra import DeepInfraProviderConfig
from .deepseek import DeepSeekProviderConfig
from .fireworks import FireworksProviderConfig
from .google import GoogleProviderConfig
from .groq import GroqProviderConfig
from .huggingface import HuggingFaceProviderConfig
from .mistral import MistralProviderConfig
from .nebius import NebiusProviderConfig
from .nvidia import NVIDIAProviderConfig
from .openai import OpenAIProviderConfig
from .openrouter import OpenRouterProviderConfig
from .perplexity import PerplexityProviderConfig
from .together import TogetherProviderConfig
from .vllm import VLLMProviderConfig
from .xai import XAIProviderConfig

__all__ = [n for n in dir() if n.endswith("ProviderConfig")]
