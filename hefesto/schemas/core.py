"""Shared I/O types for the Hefesto refinement pipeline."""
from typing import Any
from pydantic import BaseModel, Field, field_validator


class TestCase(BaseModel):
    input: str
    expected: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Output(BaseModel):
    text: str
    model: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Metrics(BaseModel):
    scores: dict[str, float] = Field(default_factory=dict)
    notes: dict[str, str] = Field(default_factory=dict)

    @field_validator("scores")
    @classmethod
    def _in_unit_range(cls, v: dict[str, float]) -> dict[str, float]:
        for k, s in v.items():
            if not (0.0 <= s <= 1.0):
                raise ValueError(f"score {k}={s} outside [0,1]")
        return v


class ScoredResult(BaseModel):
    case: TestCase
    output: Output
    metrics: Metrics
    composite: float


class RubricDimension(BaseModel):
    name: str
    description: str
    weight: float


class Rubric(BaseModel):
    dimensions: list[RubricDimension] = Field(default_factory=list)


class Objective(BaseModel):
    goal: str
    weights: dict[str, float] = Field(default_factory=dict)
    success_criteria: list[str] = Field(default_factory=list)
    invariants: list[str] = Field(default_factory=list)
