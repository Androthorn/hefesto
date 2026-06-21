"""Output schemas for ADRS - refined prompts, diffs, and reasoning."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from hefesto.schemas.input import PromptTemplate


class DiffEntry(BaseModel):
    """A single diff entry showing what changed in a prompt section."""

    type: Literal["add", "remove", "modify"] = Field(
        ..., description="Type of change"
    )
    original: str | None = Field(None, description="Original content (for remove/modify)")
    replacement: str | None = Field(None, description="New content (for add/modify)")
    reason: str | None = Field(None, description="Why this change was made")


class PromptDiff(BaseModel):
    """
    Diff showing changes between original and refined prompt.
    
    Each section (system, user) has a list of changes.
    """

    system: list[DiffEntry] = Field(
        default_factory=list,
        description="Changes to the system prompt",
    )
    user: list[DiffEntry] = Field(
        default_factory=list,
        description="Changes to the user prompt template",
    )
    constraints: list[DiffEntry] = Field(
        default_factory=list,
        description="Changes to constraints",
    )


class RefinementResult(BaseModel):
    """
    Complete result of a prompt refinement operation.
    
    Contains the refined prompt, diff, reasoning, and suggestions for next steps.
    """

    agent_name: str = Field(..., description="Name of the agent whose prompt was refined")
    original_version: str = Field(..., description="Version of the original prompt")
    refined_version: str = Field(..., description="Version assigned to the refined prompt")
    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="When the refinement was performed",
    )
    
    # The refined prompt
    refined_template: PromptTemplate = Field(
        ..., description="The refined prompt template"
    )
    refined_constraints: list[str] = Field(
        default_factory=list,
        description="Updated constraints (if any)",
    )
    
    # Diff and reasoning
    diff: PromptDiff = Field(..., description="Detailed diff of changes")
    reasoning: str = Field(
        ..., 
        description="Explanation of why these changes were made",
    )
    
    # Suggestions for next steps
    suggestions: list[str] = Field(
        default_factory=list,
        description="Suggestions for what to monitor or try next",
    )
    
    # Analysis summary
    analysis_summary: str | None = Field(
        None,
        description="Summary of the analysis that led to these changes",
    )


class RefinementBatch(BaseModel):
    """
    Result of refining multiple prompts in a single operation.
    """

    objective_goal: str = Field(..., description="The goal that was being optimized for")
    timestamp: datetime = Field(default_factory=datetime.now)
    results: list[RefinementResult] = Field(
        default_factory=list,
        description="Refinement results for each agent prompt",
    )
    overall_suggestions: list[str] = Field(
        default_factory=list,
        description="Suggestions that apply to the system as a whole",
    )
