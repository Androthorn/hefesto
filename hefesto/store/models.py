from datetime import datetime, timezone
from typing import Any
from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class PromptRecord(Base):
    __tablename__ = "prompts"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    version: Mapped[str] = mapped_column(String(50))
    parent_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    prompt_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class EvaluationRecord(Base):
    __tablename__ = "evaluations"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    prompt_version: Mapped[str] = mapped_column(String(50), index=True)
    composite_score: Mapped[float] = mapped_column(Float)
    metrics_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    judge_agreement: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class RefinementRecord(Base):
    __tablename__ = "refinements"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    parent_version: Mapped[str] = mapped_column(String(50), index=True)
    candidate_version: Mapped[str] = mapped_column(String(50))
    promoted: Mapped[bool] = mapped_column(Boolean)
    delta: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(String(64))
    reasoning: Mapped[str] = mapped_column(Text, default="")
    diff: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class RunRecord(Base):
    __tablename__ = "runs"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    prompt_version: Mapped[str] = mapped_column(String(50), index=True)
    case_input: Mapped[str] = mapped_column(Text)
    output_text: Mapped[str] = mapped_column(Text)
    metrics_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
