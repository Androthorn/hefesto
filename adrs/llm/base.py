"""Abstract base class for LLM providers."""

from abc import ABC, abstractmethod
from typing import Literal

from pydantic import BaseModel, Field


class LLMMessage(BaseModel):
    """A single message in a conversation."""

    role: Literal["system", "user", "assistant"] = Field(
        ..., description="Role of the message sender"
    )
    content: str = Field(..., description="Message content")


class LLMResponse(BaseModel):
    """Response from an LLM completion."""

    content: str = Field(..., description="Generated content")
    model: str = Field(..., description="Model that generated the response")
    usage: dict[str, int] | None = Field(
        None, description="Token usage information"
    )


class LLMProvider(ABC):
    """
    Abstract base class for LLM providers.
    
    Implementations should handle API calls to specific providers
    (OpenRouter, OpenAI, Anthropic, etc.)
    """

    @abstractmethod
    def complete(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """
        Generate a completion for the given messages.
        
        Args:
            messages: List of messages forming the conversation
            temperature: Sampling temperature (0.0 to 1.0)
            max_tokens: Maximum tokens in the response
            
        Returns:
            LLMResponse with generated content
        """
        pass

    @abstractmethod
    def get_model_name(self) -> str:
        """Return the model identifier being used."""
        pass
