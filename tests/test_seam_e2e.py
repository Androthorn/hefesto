# tests/test_seam_e2e.py
from hefesto.schemas.core import Objective, TestCase
from hefesto.dataset.base import DatasetSplit
from hefesto.schemas.config import LoopConfig
from hefesto.runner.echo_runner import EchoRunner
from hefesto.core.loop import RefineLoop


class LengthGrader:
    """Non-LLM grader: shorter echoed output scores higher (cap at 20 chars)."""
    def grade(self, case, output, objective):
        from hefesto.schemas.core import Metrics
        score = max(0.0, 1.0 - len(output.text) / 20.0)
        return Metrics(scores={"brevity": score})


class TrimRefiner:
    """Non-LLM refiner: proposes a shorter prompt each call."""
    def __init__(self):
        self._n = 0

    def propose(self, champion_prompt, selected_cases, objective):
        self._n += 1
        return "{{input}}"  # minimal prompt -> shortest echo


def test_full_loop_runs_without_any_llm():
    cases = [TestCase(input="ab"), TestCase(input="cd"),
             TestCase(input="ef"), TestCase(input="gh")]
    split = DatasetSplit(dev=cases[:2], test=cases[2:])
    cfg = LoopConfig(max_iter=2, patience=5, epsilon_k=0.0, target=None, headroom_min=0.0)
    loop = RefineLoop(
        runner=EchoRunner(), grader=LengthGrader(), refiner=TrimRefiner(),
        objective=Objective(goal="be brief"), weights={"brevity": 1.0}, config=cfg,
    )
    result = loop.run("VERBOSE PROMPT PREFIX {{input}}", split)
    assert result.champion == "{{input}}"  # the shorter prompt won
    assert result.history[0]["promoted"] is True
