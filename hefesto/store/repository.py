"""Repository for ADRS storage operations."""

from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from hefesto.schemas.input import AgentPrompt, ExperimentRun, PromptTemplate
from hefesto.schemas.evaluation import EvaluationResult, ScoringResult
from hefesto.schemas.output import RefinementResult
from hefesto.storage.models import Base, EvaluationRecord, PromptRecord, RefinementRecord, RunRecord


class Repository:
    """
    Repository for persisting and querying ADRS data.
    
    Provides CRUD operations for prompts, runs, and refinements.
    """

    def __init__(self, db_path: str | Path = "./adrs_history.db"):
        """
        Initialize the repository.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.engine = create_engine(f"sqlite:///{self.db_path}")
        self.SessionLocal = sessionmaker(bind=self.engine)

    def initialize(self) -> None:
        """Create database tables if they don't exist."""
        Base.metadata.create_all(self.engine)

    def _get_session(self) -> Session:
        """Get a new database session."""
        return self.SessionLocal()

    # =========================================================================
    # Prompt Operations
    # =========================================================================

    def save_prompt(self, prompt: AgentPrompt) -> PromptRecord:
        """
        Save a prompt to the database.
        
        Args:
            prompt: AgentPrompt to save
            
        Returns:
            Created PromptRecord
        """
        with self._get_session() as session:
            record = PromptRecord(
                agent_name=prompt.agent_name,
                version=prompt.version,
                system_prompt=prompt.template.system,
                user_prompt=prompt.template.user,
                variables=prompt.template.variables,
                constraints=prompt.constraints,
                metadata_json=prompt.metadata,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def get_prompt(self, agent_name: str, version: str) -> AgentPrompt | None:
        """
        Get a prompt by agent name and version.
        
        Args:
            agent_name: Name of the agent
            version: Prompt version
            
        Returns:
            AgentPrompt or None if not found
        """
        with self._get_session() as session:
            stmt = select(PromptRecord).where(
                PromptRecord.agent_name == agent_name,
                PromptRecord.version == version,
            )
            record = session.execute(stmt).scalar_one_or_none()
            
            if not record:
                return None
            
            return AgentPrompt(
                agent_name=record.agent_name,
                version=record.version,
                template=PromptTemplate(
                    system=record.system_prompt,
                    user=record.user_prompt,
                    variables=record.variables,
                ),
                constraints=record.constraints,
                metadata=record.metadata_json,
            )

    def get_prompt_versions(self, agent_name: str) -> list[str]:
        """
        Get all versions of a prompt for an agent.
        
        Args:
            agent_name: Name of the agent
            
        Returns:
            List of version strings, ordered by creation time
        """
        with self._get_session() as session:
            stmt = (
                select(PromptRecord.version)
                .where(PromptRecord.agent_name == agent_name)
                .order_by(PromptRecord.created_at)
            )
            results = session.execute(stmt).scalars().all()
            return list(results)

    def get_latest_prompt(self, agent_name: str) -> AgentPrompt | None:
        """
        Get the latest prompt version for an agent.
        
        Args:
            agent_name: Name of the agent
            
        Returns:
            Latest AgentPrompt or None if no prompts exist
        """
        with self._get_session() as session:
            stmt = (
                select(PromptRecord)
                .where(PromptRecord.agent_name == agent_name)
                .order_by(PromptRecord.created_at.desc())
                .limit(1)
            )
            record = session.execute(stmt).scalar_one_or_none()
            
            if not record:
                return None
            
            return AgentPrompt(
                agent_name=record.agent_name,
                version=record.version,
                template=PromptTemplate(
                    system=record.system_prompt,
                    user=record.user_prompt,
                    variables=record.variables,
                ),
                constraints=record.constraints,
                metadata=record.metadata_json,
            )

    # =========================================================================
    # Run Operations
    # =========================================================================

    def save_run(self, run: ExperimentRun) -> RunRecord:
        """
        Save an experiment run to the database.
        
        Args:
            run: ExperimentRun to save
            
        Returns:
            Created RunRecord
        """
        with self._get_session() as session:
            # Convert metrics to serializable format
            metrics_dict = {
                name: stats.model_dump()
                for name, stats in run.metrics.items()
            }
            
            # Convert logs to serializable format
            logs_list = [log.model_dump() for log in run.logs]
            
            record = RunRecord(
                run_id=run.run_id,
                agent_name=run.agent_name,
                timestamp=run.timestamp,
                prompt_version=run.prompt_version,
                metrics=metrics_dict,
                logs=logs_list,
                metadata_json=run.metadata,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def get_runs_by_agent(
        self,
        agent_name: str,
        limit: int | None = None,
    ) -> list[ExperimentRun]:
        """
        Get runs for an agent.
        
        Args:
            agent_name: Name of the agent
            limit: Maximum number of runs to return
            
        Returns:
            List of ExperimentRun objects
        """
        from hefesto.schemas.input import LogEntry, MetricStats
        
        with self._get_session() as session:
            stmt = (
                select(RunRecord)
                .where(RunRecord.agent_name == agent_name)
                .order_by(RunRecord.timestamp.desc())
            )
            if limit:
                stmt = stmt.limit(limit)
            
            records = session.execute(stmt).scalars().all()
            
            runs = []
            for record in records:
                # Convert metrics back to MetricStats
                metrics = {
                    name: MetricStats(**stats)
                    for name, stats in record.metrics.items()
                }
                
                # Convert logs back to LogEntry
                logs = [LogEntry(**log) for log in record.logs]
                
                runs.append(ExperimentRun(
                    run_id=record.run_id,
                    agent_name=record.agent_name,
                    timestamp=record.timestamp,
                    prompt_version=record.prompt_version,
                    metrics=metrics,
                    logs=logs,
                    metadata=record.metadata_json,
                ))
            
            return runs

    # =========================================================================
    # Refinement Operations
    # =========================================================================

    def save_refinement(
        self,
        result: RefinementResult,
        objective_goal: str,
        analyzed_run_ids: list[str],
    ) -> RefinementRecord:
        """
        Save a refinement result to the database.
        
        Args:
            result: RefinementResult to save
            objective_goal: The goal that guided refinement
            analyzed_run_ids: IDs of runs that were analyzed
            
        Returns:
            Created RefinementRecord
        """
        with self._get_session() as session:
            record = RefinementRecord(
                agent_name=result.agent_name,
                timestamp=result.timestamp,
                original_version=result.original_version,
                refined_version=result.refined_version,
                objective_goal=objective_goal,
                reasoning=result.reasoning,
                suggestions=result.suggestions,
                analysis_summary=result.analysis_summary,
                diff_json=result.diff.model_dump(),
                analyzed_run_ids=analyzed_run_ids,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def get_refinement_history(
        self,
        agent_name: str,
        limit: int | None = None,
    ) -> list[dict]:
        """
        Get refinement history for an agent.
        
        Args:
            agent_name: Name of the agent
            limit: Maximum number of records to return
            
        Returns:
            List of refinement records as dictionaries
        """
        with self._get_session() as session:
            stmt = (
                select(RefinementRecord)
                .where(RefinementRecord.agent_name == agent_name)
                .order_by(RefinementRecord.timestamp.desc())
            )
            if limit:
                stmt = stmt.limit(limit)
            
            records = session.execute(stmt).scalars().all()
            
            return [
                {
                    "id": record.id,
                    "agent_name": record.agent_name,
                    "timestamp": record.timestamp.isoformat(),
                    "original_version": record.original_version,
                    "refined_version": record.refined_version,
                    "objective_goal": record.objective_goal,
                    "reasoning": record.reasoning,
                    "suggestions": record.suggestions,
                }
                for record in records
            ]

    # =========================================================================
    # Evaluation Operations
    # =========================================================================

    def save_evaluation(self, evaluation: EvaluationResult) -> EvaluationRecord:
        """Save an evaluation result to the database.

        Args:
            evaluation: EvaluationResult to persist.

        Returns:
            Created EvaluationRecord.
        """
        with self._get_session() as session:
            # Serialize metrics
            metrics_dict = {
                name: stats.model_dump()
                for name, stats in evaluation.metrics.items()
            }

            record = EvaluationRecord(
                agent_name=evaluation.agent_name,
                iteration=evaluation.iteration,
                timestamp=evaluation.timestamp,
                prompt_version=evaluation.prompt_version,
                prompt_text=evaluation.prompt_text,
                composite_score=evaluation.scoring.composite_score,
                metrics_json=metrics_dict,
                scoring_json=evaluation.scoring.model_dump(),
                reasoning=evaluation.reasoning,
                suggestions=evaluation.suggestions,
                analyzer_output_dir=evaluation.analyzer_output_dir,
                metadata_json=evaluation.metadata,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def get_top_evaluations(
        self,
        agent_name: str,
        limit: int = 3,
    ) -> list[dict]:
        """Get the top-scoring evaluations for an agent.

        Args:
            agent_name: Name of the agent.
            limit: Maximum number of records to return.

        Returns:
            List of evaluation records as dicts, sorted by score descending.
        """
        with self._get_session() as session:
            stmt = (
                select(EvaluationRecord)
                .where(EvaluationRecord.agent_name == agent_name)
                .order_by(EvaluationRecord.composite_score.desc())
                .limit(limit)
            )
            records = session.execute(stmt).scalars().all()
            return [self._eval_record_to_dict(r) for r in records]

    def get_recent_evaluations(
        self,
        agent_name: str,
        limit: int = 3,
    ) -> list[dict]:
        """Get the most recent evaluations for an agent.

        Args:
            agent_name: Name of the agent.
            limit: Maximum number of records to return.

        Returns:
            List of evaluation records as dicts, sorted by timestamp descending.
        """
        with self._get_session() as session:
            stmt = (
                select(EvaluationRecord)
                .where(EvaluationRecord.agent_name == agent_name)
                .order_by(EvaluationRecord.timestamp.desc())
                .limit(limit)
            )
            records = session.execute(stmt).scalars().all()
            return [self._eval_record_to_dict(r) for r in records]

    def get_iteration_count(self, agent_name: str) -> int:
        """Get the current iteration count for an agent.

        Args:
            agent_name: Name of the agent.

        Returns:
            Number of evaluations stored for this agent.
        """
        from sqlalchemy import func

        with self._get_session() as session:
            stmt = (
                select(func.count())
                .select_from(EvaluationRecord)
                .where(EvaluationRecord.agent_name == agent_name)
            )
            return session.execute(stmt).scalar() or 0

    @staticmethod
    def _eval_record_to_dict(record: EvaluationRecord) -> dict:
        """Convert an EvaluationRecord to a dictionary."""
        # Build a human-readable metrics summary
        metrics_summary_parts = []
        for name, stats in record.metrics_json.items():
            if isinstance(stats, dict) and "mean" in stats:
                metrics_summary_parts.append(
                    f"{name}: mean={stats['mean']:.4f}"
                )
        metrics_summary = ", ".join(metrics_summary_parts)

        return {
            "id": record.id,
            "agent_name": record.agent_name,
            "iteration": record.iteration,
            "timestamp": record.timestamp.isoformat(),
            "prompt_version": record.prompt_version,
            "prompt_text": record.prompt_text,
            "composite_score": record.composite_score,
            "metrics_json": record.metrics_json,
            "scoring_json": record.scoring_json,
            "metrics_summary": metrics_summary,
            "reasoning": record.reasoning,
            "suggestions": record.suggestions,
        }
