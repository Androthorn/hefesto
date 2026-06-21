"""Factory function for creating LLM providers."""

from hefesto.llm.base import LLMProvider
from hefesto.llm.openrouter import OpenRouterProvider
from hefesto.llm.direct import DirectProvider
from hefesto.schemas.config import LLMConfig


def create_provider(config: LLMConfig) -> LLMProvider:
    """
    Create an LLM provider based on configuration.
    
    Args:
        config: LLM configuration specifying provider and model
        
    Returns:
        Configured LLMProvider instance
        
    Raises:
        ValueError: If provider type is not supported
    """
    if config.provider == "openrouter":
        return OpenRouterProvider(
            model=config.model,
            api_key_env=config.api_key_env,
        )
    elif config.provider in ("openai", "anthropic", "google", "litellm"):
        return DirectProvider(
            model=config.model,
            api_key_env=config.api_key_env,
        )
    else:
        raise ValueError(f"Unsupported LLM provider: {config.provider}")
