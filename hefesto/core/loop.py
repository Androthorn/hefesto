import statistics
from pydantic import BaseModel
from hefesto.schemas.core import ScoredResult, Objective
from hefesto.dataset.base import DatasetSplit
from hefesto.schemas.config import LoopConfig
from hefesto.score.aggregate import composite_score
from hefesto.refiner.select import select_contrast
from hefesto.refiner.invariants import check_invariants
from hefesto.core.intake import no_headroom


class LoopResult(BaseModel):
    champion: str
    champion_score: float
    history: list[dict]


def evaluate(prompt, cases, runner, grader, objective, weights) -> list[ScoredResult]:
    results = []
    for case in cases:
        output = runner.run(prompt, case)
        metrics = grader.grade(case, output, objective)
        results.append(ScoredResult(
            case=case, output=output, metrics=metrics,
            composite=composite_score(metrics, weights),
        ))
    return results


def paired_mean(cand: list[ScoredResult], champ: list[ScoredResult]) -> float:
    deltas = [c.composite - p.composite for c, p in zip(cand, champ)]
    return sum(deltas) / len(deltas) if deltas else 0.0


def pooled_std(cand: list[ScoredResult], champ: list[ScoredResult]) -> float:
    deltas = [c.composite - p.composite for c, p in zip(cand, champ)]
    return statistics.pstdev(deltas) if len(deltas) >= 2 else 0.0


def _mean_composite(results: list[ScoredResult]) -> float:
    return sum(r.composite for r in results) / len(results) if results else 0.0


class RefineLoop:
    def __init__(self, runner, grader, refiner, objective: Objective,
                 weights: dict[str, float], config: LoopConfig,
                 repo=None, judge_agreement=None) -> None:
        self.runner = runner
        self.grader = grader
        self.refiner = refiner
        self.objective = objective
        self.weights = weights
        self.config = config
        self.repo = repo
        self.judge_agreement = judge_agreement

    def _eval(self, prompt, cases):
        return evaluate(prompt, cases, self.runner, self.grader,
                        self.objective, self.weights)

    def run(self, seed_prompt: str, split: DatasetSplit) -> LoopResult:
        champion = seed_prompt
        champ_dev = self._eval(champion, split.dev)
        champ_test = self._eval(champion, split.test)
        champ_score = _mean_composite(champ_test)
        history: list[dict] = []

        if no_headroom(champ_score, self.config.target, self.config.headroom_min):
            return LoopResult(champion=champion, champion_score=champ_score, history=history)

        fails = 0
        version = 1
        for _ in range(self.config.max_iter):
            selected = select_contrast(champ_dev, self.config.k)
            candidate = self.refiner.propose(champion, selected, self.objective)
            version += 1
            cand_version = f"v{version}"

            if not check_invariants(candidate, self.objective.invariants):
                self._log(history, cand_version, False, 0.0, "invariant_violation")
                fails += 1
            else:
                cand_test = self._eval(candidate, split.test)
                delta = paired_mean(cand_test, champ_test)
                if delta > self.config.epsilon_k * pooled_std(cand_test, champ_test):
                    champion = candidate
                    champ_dev = self._eval(candidate, split.dev)
                    champ_test = cand_test
                    champ_score = _mean_composite(champ_test)
                    self._log(history, cand_version, True, delta, "promoted")
                    fails = 0
                else:
                    self._log(history, cand_version, False, delta, "no_improvement")
                    fails += 1

            if fails >= self.config.patience:
                break
            if self.config.target is not None and champ_score >= self.config.target:
                break

        return LoopResult(champion=champion, champion_score=champ_score, history=history)

    def _log(self, history, cand_version, promoted, delta, reason):
        entry = {"candidate_version": cand_version, "promoted": promoted,
                 "delta": delta, "reason": reason}
        history.append(entry)
        if self.repo is not None:
            self.repo.save_refinement(
                parent_version="champion", candidate_version=cand_version,
                promoted=promoted, delta=delta, reason=reason,
            )
