"""Direct LLM provider implementation using LiteLLM."""

import os

import litellm

from hefesto.llm.base import LLMProvider, LLMMessage, LLMResponse


class DirectProvider(LLMProvider):
    """
    LLM provider using LiteLLM for direct API calls.
    
    LiteLLM provides a unified interface for OpenAI, Anthropic, Google, and more.
    """

    def __init__(
        self,
        model: str = "gpt-4",
        api_key: str | None = None,
        api_key_env: str | None = None,
    ):
        """
        Initialize the direct provider.
        
        Args:
            model: Model identifier (e.g., "gpt-4", "claude-3-sonnet-20240229")
            api_key: API key (if not provided, LiteLLM will use standard env vars)
            api_key_env: Custom environment variable name for API key
        """
        self.model = model
        
        # Set API key if provided
        if api_key:
            self._set_api_key(model, api_key)
        elif api_key_env:
            key = os.environ.get(api_key_env)
            if key:
                self._set_api_key(model, key)

    def _set_api_key(self, model: str, api_key: str) -> None:
        """Set the API key for the appropriate provider based on model."""
        model_lower = model.lower()
        
        if "gpt" in model_lower or "openai" in model_lower:
            os.environ["OPENAI_API_KEY"] = api_key
        elif "claude" in model_lower or "anthropic" in model_lower:
            os.environ["ANTHROPIC_API_KEY"] = api_key
        elif "gemini" in model_lower or "google" in model_lower:
            os.environ["GOOGLE_API_KEY"] = api_key
        else:
            # Default to OpenAI
            os.environ["OPENAI_API_KEY"] = api_key

    def complete(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Generate a completion using LiteLLM."""
        # Convert messages to dict format
        message_dicts = [msg.model_dump() for msg in messages]

        # Call LiteLLM
        response = litellm.completion(
            model=self.model,
            messages=message_dicts,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        # Parse response
        content = response.choices[0].message.content
        
        usage = None
        if hasattr(response, "usage") and response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        return LLMResponse(
            content=content,
            model=response.model or self.model,
            usage=usage,
        )

    def get_model_name(self) -> str:
        """Return the model identifier."""
        return self.model
