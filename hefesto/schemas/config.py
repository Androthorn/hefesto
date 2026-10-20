"""Configuration schema — provider-agnostic, fail-fast, per-role."""
from typing import Literal
import yaml
from pydantic import BaseModel, Field


class ConfigError(Exception):
    """Raised when a required provider role is unresolved."""


class ProviderConfig(BaseModel):
    provider: str
    model: str
    temperature: float = 0.7
    api_key_env: str | None = None


class JudgeConfig(BaseModel):
    mode: Literal["pairwise", "absolute"] = "pairwise"
    require_different_model: bool = True
    calibration_reference: str | None = None
    min_agreement: float = 0.7


class DatasetConfig(BaseModel):
    source: Literal["generate", "load"] = "generate"
    count: int = 20
    path: str | None = None
    freeze: bool = True
    test_fraction: float = 0.4


class LoopConfig(BaseModel):
    max_iter: int = 5
    patience: int = 2
    k: int = 3
    epsilon_k: float = 1.0  # unused by the promotion gate; kept for backward compatibility with old configs
    delta_min: float = 0.05
    alpha: float = 0.05
    judge_samples: int = 1
    target: float | None = None
    headroom_min: float = 0.05


class HefestoConfig(BaseModel):
    providers: dict[str, ProviderConfig]
    objective: str
    prompt: str
    dataset: DatasetConfig = Field(default_factory=DatasetConfig)
    grader: str = "llm_judge"
    judge: JudgeConfig = Field(default_factory=JudgeConfig)
    loop: LoopConfig = Field(default_factory=LoopConfig)
    store_path: str = "hefesto.db"

    def provider_for(self, role: str) -> ProviderConfig:
        if role in self.providers:
            return self.providers[role]
        if "default" in self.providers:
            return self.providers["default"]
        raise ConfigError(f"no provider configured for role '{role}' (and no 'default')")

    @classmethod
    def from_yaml(cls, path: str) -> "HefestoConfig":
        with open(path) as f:
            return cls.model_validate(yaml.safe_load(f))
