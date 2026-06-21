"""Input schemas for ADRS - defines structure for metrics, logs, prompts, and objectives."""

from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


class MetricStats(BaseModel):
    """Statistical summary for a single metric."""
    
    mean: float = Field(..., description="Mean value across runs")
    min: float = Field(..., description="Minimum observed value")
    max: float = Field(..., description="Maximum observed value")
    std: float = Field(..., description="Standard deviation")
    median: float = Field(..., description="Median value")


class LogEntry(BaseModel):
    """A single log entry from an experiment run."""
    
    level: str = Field(..., description="Log level (INFO, WARN, ERROR, etc.)")
    message: str = Field(..., description="Log message content")
    timestamp: datetime | None = Field(None, description="When the log was generated")
    metadata: dict[str, Any] | None = Field(None, description="Additional structured data")


class ExperimentRun(BaseModel):
    """
    A single experiment run linking metrics and logs to a specific prompt version.
    
    This is the core input unit - each run represents one execution of an agent
    with a specific prompt, capturing the resulting metrics and logs.
    """
    
    run_id: str = Field(..., description="Unique identifier for this run")
    timestamp: datetime = Field(..., description="When the run was executed")
    prompt_version: str = Field(..., description="Version of the prompt used in this run")
    agent_name: str = Field(..., description="Name of the agent that was run")
    metrics: dict[str, MetricStats] = Field(
        ..., 
        description="Metrics collected during the run, keyed by metric name"
    )
    logs: list[LogEntry] = Field(
        default_factory=list,
        description="Log entries from the run"
    )
    metadata: dict[str, Any] | None = Field(
        None, 
        description="Additional run metadata (config, environment, etc.)"
    )


class PromptTemplate(BaseModel):
    """
    Structured prompt template with system/user sections and variables.
    
    This structure is preserved during refinement to maintain compatibility
    with the agent's prompt processing.
    """
    
    system: str = Field(..., description="System prompt content")
    user: str = Field(..., description="User prompt template (may contain {{variables}})")
    variables: list[str] = Field(
        default_factory=list,
        description="List of variable names that can be interpolated in the user prompt"
    )


class AgentPrompt(BaseModel):
    """
    Complete prompt configuration for an agent.
    
    Includes the prompt template, version info, and constraints that must be
    preserved during refinement.
    """
    
    agent_name: str = Field(..., description="Name of the agent this prompt is for")
    version: str = Field(..., description="Version string for this prompt")
    template: PromptTemplate = Field(..., description="The prompt template")
    constraints: list[str] = Field(
        default_factory=list,
        description="Constraints that must be preserved (e.g., 'Must output valid JSON')"
    )
    metadata: dict[str, Any] | None = Field(
        None,
        description="Additional metadata about the prompt"
    )


class SuccessCriterion(BaseModel):
    """A single success criterion for the optimization objective."""
    
    metric: str = Field(..., description="Name of the metric to evaluate")
    operator: str = Field(..., description="Comparison operator (<, >, <=, >=, ==)")
    threshold: float = Field(..., description="Target threshold value")
    
    def to_string(self) -> str:
        """Convert to human-readable string."""
        return f"{self.metric} {self.operator} {self.threshold}"


class Objective(BaseModel):
    """
    Defines what the user wants to achieve through prompt refinement.
    
    The objective guides the LLM in understanding what aspects of the prompts
    need to be improved.
    """
    
    goal: str = Field(
        ..., 
        description="High-level description of the optimization goal"
    )
    success_criteria: list[SuccessCriterion] = Field(
        default_factory=list,
        description="Measurable criteria for success"
    )
    priority_metrics: list[str] = Field(
        default_factory=list,
        description="Metrics to prioritize in analysis (e.g., ['pending_pods', 'number_of_migrations'])"
    )
    focus_areas: list[str] = Field(
        default_factory=list,
        description="Aspects to focus on (e.g., ['consistency', 'performance', 'cost'])"
    )
