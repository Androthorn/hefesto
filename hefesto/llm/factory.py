"""Create an LLMProvider from a ProviderConfig. No baked-in defaults."""
from hefesto.llm.base import LLMProvider
from hefesto.llm.openrouter import OpenRouterProvider
from hefesto.llm.direct import DirectProvider
from hefesto.schemas.config import ProviderConfig


def create_provider(cfg: ProviderConfig) -> LLMProvider:
    if cfg.provider == "openrouter":
        return OpenRouterProvider(model=cfg.model, api_key_env=cfg.api_key_env)
    if cfg.provider in ("openai", "anthropic", "google", "litellm"):
        return DirectProvider(model=cfg.model, api_key_env=cfg.api_key_env)
    raise ValueError(f"Unsupported LLM provider: {cfg.provider}")
