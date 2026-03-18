"""Evaluation schemas for ADRS — scoring results and evaluation records."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from adrs.schemas.input import MetricStats


class ScoringWeights(BaseModel):
    """Configurable weights for the composite scoring function.

    Each weight controls the relative importance of a metric in the final score.
    Weights are normalized to sum to 1.0 during scoring.
    """

    pending_pods: float = Field(
        default=0.35, description="Weight for pending_pods metric"
    )
    time_with_pending: float = Field(
        default=0.25, description="Weight for time_with_pending metric"
    )
    cost: float = Field(
        default=0.25, description="Weight for cost metric"
    )
    number_of_migrations: float = Field(
        default=0.15, description="Weight for number_of_migrations metric"
    )
    overload_penalty: float = Field(
        default=0.0,
        description="Score penalty when cluster load exceeds 80% capacity. "
        "Disabled by default (0.0) because the current experiment scenario "
        "allocates all workloads to member1, so the penalty always triggers "
        "and acts as a constant bias rather than a meaningful differentiator.",
    )

    def to_dict(self) -> dict[str, float]:
        """Return metric weights as a dict (excluding overload_penalty)."""
        return {
            "pending_pods": self.pending_pods,
            "time_with_pending": self.time_with_pending,
            "cost": self.cost,
            "number_of_migrations": self.number_of_migrations,
        }

    def total(self) -> float:
        """Sum of metric weights (for normalization)."""
        return sum(self.to_dict().values())


class MetricScore(BaseModel):
    """Score for a single metric after normalization."""

    metric_name: str = Field(..., description="Name of the metric")
    raw_value: float = Field(..., description="Observed value (mean)")
    baseline_value: float = Field(
        ..., description="Baseline/worst-acceptable value"
    )
    normalized_score: float = Field(
        ..., description="Normalized score in [0, 1]"
    )
    weight: float = Field(..., description="Weight applied to this metric")
    weighted_score: float = Field(
        ..., description="normalized_score * weight"
    )


class ScoringResult(BaseModel):
    """Complete result of scoring a simulation run.

    Uses a target-based normalization:
        s_i = max(0, 1 - v_i / b_i)

    Where v_i is the observed value and b_i is the baseline.
    The composite score is a weighted average of individual scores,
    with an optional penalty for cluster overload (>80% capacity).
    """

    metric_scores: list[MetricScore] = Field(
        default_factory=list,
        description="Individual metric scores"
    )
    composite_score: float = Field(
        ..., description="Weighted composite score in [0, 1]"
    )
    overload_detected: bool = Field(
        default=False,
        description="Whether cluster load exceeded 80% capacity"
    )
    overload_penalty_applied: float = Field(
        default=0.0,
        description="Penalty subtracted from composite score for overload"
    )
    weights_used: ScoringWeights = Field(
        default_factory=ScoringWeights,
        description="Weights configuration used for this scoring"
    )


class EvaluationResult(BaseModel):
    """Full evaluation result for one simulation run.

    Combines the scoring result with raw metrics, feedback, and metadata.
    """

    iteration: int = Field(..., description="Iteration number in the ADRS loop")
    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="When the evaluation was performed"
    )
    agent_name: str = Field(
        default="consolidator_agent",
        description="Name of the agent whose prompt was evaluated"
    )
    prompt_version: str = Field(..., description="Version of the prompt that was evaluated")
    prompt_text: str = Field(..., description="Full text of the prompt that was evaluated")

    # Metrics from the simulation
    metrics: dict[str, MetricStats] = Field(
        ..., description="Raw metrics collected from the analyzer"
    )

    # Scoring
    scoring: ScoringResult = Field(
        ..., description="Detailed scoring breakdown"
    )

    # Feedback
    reasoning: str | None = Field(
        None,
        description="LLM-generated reasoning about this evaluation"
    )
    suggestions: list[str] = Field(
        default_factory=list,
        description="Suggestions for the next iteration"
    )

    # Source metadata
    analyzer_output_dir: str | None = Field(
        None, description="Path to the analyzer output directory used"
    )
    metadata: dict[str, Any] | None = Field(
        None, description="Additional metadata"
    )
