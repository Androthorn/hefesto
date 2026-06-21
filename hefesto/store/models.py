"""SQLAlchemy models for ADRS storage."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class PromptRecord(Base):
    """
    Stores prompt versions.
    
    Each record represents a specific version of an agent's prompt.
    """

    __tablename__ = "prompts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    agent_name: Mapped[str] = mapped_column(String(255), index=True)
    version: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )
    
    # Prompt content (stored as JSON)
    system_prompt: Mapped[str] = mapped_column(Text)
    user_prompt: Mapped[str] = mapped_column(Text)
    variables: Mapped[list[str]] = mapped_column(JSON, default=list)
    constraints: Mapped[list[str]] = mapped_column(JSON, default=list)
    
    # Optional metadata
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    
    # Relationships
    runs: Mapped[list["RunRecord"]] = relationship(back_populates="prompt")
    refinements_from: Mapped[list["RefinementRecord"]] = relationship(
        back_populates="original_prompt",
        foreign_keys="RefinementRecord.original_prompt_id",
    )
    refinements_to: Mapped[list["RefinementRecord"]] = relationship(
        back_populates="refined_prompt",
        foreign_keys="RefinementRecord.refined_prompt_id",
    )


class RunRecord(Base):
    """
    Stores experiment run data.
    
    Each record links to the prompt used and contains metrics/logs.
    """

    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    agent_name: Mapped[str] = mapped_column(String(255), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Link to prompt used
    prompt_id: Mapped[int | None] = mapped_column(
        ForeignKey("prompts.id"), nullable=True
    )
    prompt_version: Mapped[str] = mapped_column(String(50))
    
    # Metrics and logs (stored as JSON)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    logs: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    
    # Optional metadata
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    
    # Relationships
    prompt: Mapped[PromptRecord | None] = relationship(back_populates="runs")


class RefinementRecord(Base):
    """
    Stores refinement history.
    
    Each record captures a refinement operation with before/after prompts,
    the reasoning, and analysis that led to the refinement.
    """

    __tablename__ = "refinements"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    agent_name: Mapped[str] = mapped_column(String(255), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Links to prompts
    original_prompt_id: Mapped[int | None] = mapped_column(
        ForeignKey("prompts.id"), nullable=True
    )
    refined_prompt_id: Mapped[int | None] = mapped_column(
        ForeignKey("prompts.id"), nullable=True
    )
    
    # Version strings
    original_version: Mapped[str] = mapped_column(String(50))
    refined_version: Mapped[str] = mapped_column(String(50))
    
    # Objective that guided the refinement
    objective_goal: Mapped[str] = mapped_column(Text)
    
    # Reasoning and suggestions
    reasoning: Mapped[str] = mapped_column(Text)
    suggestions: Mapped[list[str]] = mapped_column(JSON, default=list)
    
    # Analysis summary
    analysis_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Diff (stored as JSON)
    diff_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    
    # Run IDs that were analyzed
    analyzed_run_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    
    # Relationships
    original_prompt: Mapped[PromptRecord | None] = relationship(
        back_populates="refinements_from",
        foreign_keys=[original_prompt_id],
    )
    refined_prompt: Mapped[PromptRecord | None] = relationship(
        back_populates="refinements_to",
        foreign_keys=[refined_prompt_id],
    )


class EvaluationRecord(Base):
    """Stores evaluation results from simulation runs.

    Each record captures one iteration of the ADRS evaluate-and-refine cycle,
    including the metrics, composite score, prompt text, and feedback.
    """

    __tablename__ = "evaluations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    agent_name: Mapped[str] = mapped_column(String(255), index=True)
    iteration: Mapped[int] = mapped_column(Integer, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Prompt that was evaluated
    prompt_version: Mapped[str] = mapped_column(String(50))
    prompt_text: Mapped[str] = mapped_column(Text)

    # Scoring
    composite_score: Mapped[float] = mapped_column(Float)
    metrics_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    scoring_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    # Feedback
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggestions: Mapped[list[str]] = mapped_column(JSON, default=list)

    # Source metadata
    analyzer_output_dir: Mapped[str | None] = mapped_column(
        String(1024), nullable=True
    )
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )

