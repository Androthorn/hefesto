"""Configuration schemas for ADRS."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class LLMConfig(BaseModel):
    """Configuration for the LLM provider."""

    provider: Literal["openrouter", "openai", "anthropic", "google", "litellm"] = Field(
        default="openrouter",
        description="LLM provider to use",
    )
    model: str = Field(
        default="anthropic/claude-sonnet-4-20250514",
        description="Model identifier (format depends on provider)",
    )
    api_key_env: str = Field(
        default="OPENROUTER_API_KEY",
        description="Name of environment variable containing the API key",
    )
    temperature: float = Field(
        default=0.7,
        description="Sampling temperature for the LLM",
    )
    max_tokens: int = Field(
        default=4096,
        description="Maximum tokens in the response",
    )


class StorageConfig(BaseModel):
    """Configuration for the storage backend."""

    type: Literal["sqlite"] = Field(
        default="sqlite",
        description="Storage backend type",
    )
    path: str = Field(
        default="./adrs_history.db",
        description="Path to the SQLite database file",
    )


class AnalyzerConfig(BaseModel):
    """Configuration for the analyzer component."""

    priority_metrics: list[str] = Field(
        default_factory=lambda: ["pending_pods", "number_of_migrations"],
        description="Metrics to prioritize in analysis",
    )
    variance_threshold: float = Field(
        default=0.1,
        description="Threshold for flagging high-variance metrics (coefficient of variation)",
    )


class ADRSConfig(BaseModel):
    """
    Main configuration for ADRS.
    
    Can be loaded from a YAML file or constructed programmatically.
    """

    llm: LLMConfig = Field(default_factory=LLMConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    analyzer: AnalyzerConfig = Field(default_factory=AnalyzerConfig)
    
    # Output settings
    output_dir: str = Field(
        default="./refined_prompts",
        description="Default directory for refined prompt output",
    )
    include_reasoning: bool = Field(
        default=True,
        description="Include reasoning in output",
    )
    include_diff: bool = Field(
        default=True,
        description="Include diff in output",
    )

    @classmethod
    def from_yaml(cls, path: str | Path) -> "ADRSConfig":
        """Load configuration from a YAML file."""
        import yaml

        with open(path) as f:
            data = yaml.safe_load(f)
        return cls.model_validate(data)

    def to_yaml(self, path: str | Path) -> None:
        """Save configuration to a YAML file."""
        import yaml

        with open(path, "w") as f:
            yaml.dump(self.model_dump(), f, default_flow_style=False)
