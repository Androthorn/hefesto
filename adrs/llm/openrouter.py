"""OpenRouter LLM provider implementation."""

import os
from typing import Any

import httpx

from adrs.llm.base import LLMProvider, LLMMessage, LLMResponse


class OpenRouterProvider(LLMProvider):
    """
    LLM provider using OpenRouter API.
    
    OpenRouter provides access to multiple models through a single API.
    """

    BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(
        self,
        model: str = "anthropic/claude-sonnet-4-20250514",
        api_key: str | None = None,
        api_key_env: str = "OPENROUTER_API_KEY",
    ):
        """
        Initialize the OpenRouter provider.
        
        Args:
            model: Model identifier (e.g., "anthropic/claude-sonnet-4-20250514")
            api_key: API key (if not provided, reads from environment)
            api_key_env: Environment variable name for API key
        """
        self.model = model
        self.api_key = api_key or os.environ.get(api_key_env)
        
        if not self.api_key:
            raise ValueError(
                f"OpenRouter API key not found. Set {api_key_env} environment variable "
                "or pass api_key directly."
            )

    def complete(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Generate a completion using OpenRouter API."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/adrs",  # Required by OpenRouter
        }

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [msg.model_dump() for msg in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        with httpx.Client(timeout=120.0) as client:
            response = client.post(
                f"{self.BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        # Parse response
        choice = data["choices"][0]
        content = choice["message"]["content"]
        
        usage = None
        if "usage" in data:
            usage = {
                "prompt_tokens": data["usage"].get("prompt_tokens", 0),
                "completion_tokens": data["usage"].get("completion_tokens", 0),
                "total_tokens": data["usage"].get("total_tokens", 0),
            }

        return LLMResponse(
            content=content,
            model=data.get("model", self.model),
            usage=usage,
        )

    def get_model_name(self) -> str:
        """Return the model identifier."""
        return self.model
