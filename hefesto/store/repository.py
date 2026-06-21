from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from hefesto.store.models import (
    Base, PromptRecord, EvaluationRecord, RefinementRecord,
)


class Repository:
    def __init__(self, db_path: str) -> None:
        self.engine = create_engine(f"sqlite:///{db_path}")

    def init_db(self) -> None:
        Base.metadata.create_all(self.engine)

    def save_prompt(self, name, version, prompt_text, parent_version=None) -> int:
        with Session(self.engine) as s:
            rec = PromptRecord(name=name, version=version,
                               prompt_text=prompt_text, parent_version=parent_version)
            s.add(rec)
            s.commit()
            return rec.id

    def save_evaluation(self, prompt_version, composite_score, metrics,
                        judge_agreement=None) -> None:
        with Session(self.engine) as s:
            s.add(EvaluationRecord(
                prompt_version=prompt_version, composite_score=composite_score,
                metrics_json=metrics, judge_agreement=judge_agreement,
            ))
            s.commit()

    def save_refinement(self, parent_version, candidate_version, promoted,
                        delta, reason, reasoning="", diff="") -> None:
        with Session(self.engine) as s:
            s.add(RefinementRecord(
                parent_version=parent_version, candidate_version=candidate_version,
                promoted=promoted, delta=delta, reason=reason,
                reasoning=reasoning, diff=diff,
            ))
            s.commit()

    def get_refinements(self) -> list[RefinementRecord]:
        with Session(self.engine) as s:
            return list(s.scalars(select(RefinementRecord)))

    def get_evaluations(self) -> list[EvaluationRecord]:
        with Session(self.engine) as s:
            return list(s.scalars(select(EvaluationRecord)))
