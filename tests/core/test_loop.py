# tests/core/test_loop.py
from hefesto.schemas.core import Objective
from hefesto.dataset.base import DatasetSplit
from hefesto.schemas.core import TestCase
from hefesto.schemas.config import LoopConfig
from hefesto.runner.echo_runner import EchoRunner
from hefesto.core.loop import RefineLoop


class ScriptedGrader:
    """Scores an output by a fixed table keyed on substring of the prompt echo."""
    def __init__(self, table):
        self.table = table

    def grade(self, case, output, objective):
        from hefesto.schemas.core import Metrics
        for key, score in self.table.items():
            if key in output.text:
                return Metrics(scores={"q": score})
        return Metrics(scores={"q": 0.0})


class ScriptedRefiner:
    """Emits a fixed sequence of candidate prompts."""
    def __init__(self, candidates):
        self._candidates = iter(candidates)

    def propose(self, champion_prompt, selected_cases, objective):
        return next(self._candidates)


def _split():
    cases = [TestCase(input="1"), TestCase(input="2"),
             TestCase(input="3"), TestCase(input="4")]
    return DatasetSplit(dev=cases[:2], test=cases[2:])


def test_worse_candidate_is_never_promoted():
    # Echo runner makes output text == prompt with {{input}} filled.
    # Seed prompt "GOOD {{input}}" -> grader sees "GOOD" -> 0.8
    # Candidate "BAD {{input}}"   -> grader sees "BAD"  -> 0.2 (worse, rejected)
    grader = ScriptedGrader({"GOOD": 0.8, "BAD": 0.2})
    refiner = ScriptedRefiner(["BAD {{input}}", "BAD {{input}}"])
    cfg = LoopConfig(max_iter=2, patience=5, epsilon_k=0.0, target=None, headroom_min=0.0)
    loop = RefineLoop(
        runner=EchoRunner(), grader=grader, refiner=refiner,
        objective=Objective(goal="g"), weights={"q": 1.0}, config=cfg,
    )
    result = loop.run("GOOD {{input}}", _split())
    assert result.champion == "GOOD {{input}}"        # never replaced
    assert all(h["promoted"] is False for h in result.history)
    assert len(result.history) == 2                    # both attempts logged


def test_better_candidate_is_promoted():
    grader = ScriptedGrader({"BEST": 1.0, "OKAY": 0.5})
    refiner = ScriptedRefiner(["BEST {{input}}"])
    cfg = LoopConfig(max_iter=1, patience=5, epsilon_k=0.0, target=None, headroom_min=0.0)
    loop = RefineLoop(
        runner=EchoRunner(), grader=grader, refiner=refiner,
        objective=Objective(goal="g"), weights={"q": 1.0}, config=cfg,
    )
    result = loop.run("OKAY {{input}}", _split())
    assert result.champion == "BEST {{input}}"
    assert result.history[-1]["promoted"] is True


def test_lineage_parent_version_tracks_real_champion():
    # Iteration 1: "BETTER" is promoted (score 0.8 > seed 0.5)
    # Iteration 2: "WORSE" is rejected (score 0.2 < champion 0.8)
    # Expected lineage:
    #   history[0]: parent_version="v1", candidate_version="v2", promoted=True
    #   history[1]: parent_version="v2", candidate_version="v3", promoted=False
    grader = ScriptedGrader({"SEED": 0.5, "BETTER": 0.8, "WORSE": 0.2})
    refiner = ScriptedRefiner(["BETTER {{input}}", "WORSE {{input}}"])
    cfg = LoopConfig(max_iter=2, patience=5, epsilon_k=0.0, target=None, headroom_min=0.0)
    loop = RefineLoop(
        runner=EchoRunner(), grader=grader, refiner=refiner,
        objective=Objective(goal="g"), weights={"q": 1.0}, config=cfg,
    )
    result = loop.run("SEED {{input}}", _split())

    assert result.champion == "BETTER {{input}}"
    assert len(result.history) == 2

    promoted_entry = result.history[0]
    assert promoted_entry["promoted"] is True
    assert promoted_entry["parent_version"] == "v1"
    assert promoted_entry["candidate_version"] == "v2"

    rejected_entry = result.history[1]
    assert rejected_entry["promoted"] is False
    assert rejected_entry["parent_version"] == "v2"
    assert rejected_entry["candidate_version"] == "v3"
