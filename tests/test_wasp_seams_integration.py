from pathlib import Path

from hefesto.schemas.core import TestCase, Objective
from hefesto.runner.wasp_runner import WASPRunner
from hefesto.grader.stability_grader import StabilityGrader
from hefesto.core.loop import evaluate

FIXT = Path(__file__).resolve().parent / "fixtures" / "summary_metrics_run01.csv"


def test_evaluate_runs_two_replicas_and_scores(tmp_path):
    root = tmp_path / "simulatormeu"
    (root / "ai-engine" / "prompts").mkdir(parents=True)
    runs = tmp_path / "runs-workshop"
    cfg = root / "config_compressed.yaml"; cfg.write_text("x: 1\n")

    def fake_cmd(cmd, **kwargs):
        dest = Path(cmd[4])
        (dest / "analyzer" / "summary").mkdir(parents=True, exist_ok=True)
        (dest / "analyzer" / "summary" / "summary_metrics_x.csv").write_text(FIXT.read_text())
        (dest / "provenance.json").write_text('{"model":"m"}')
        class R: returncode = 0
        return R()

    runner = WASPRunner(root, cfg, runs, runner_cmd=fake_cmd)
    grader = StabilityGrader()
    cases = [TestCase(input="", metadata={"replica": i}) for i in range(2)]
    results = evaluate("PROMPT", cases, runner, grader,
                       Objective(goal="stability"), {"stability": 1.0})
    assert len(results) == 2
    for r in results:
        assert r.composite == r.metrics.scores["stability"]
        assert 0.5 < r.composite < 0.6  # S da fixture run01 ≈ 0.5619
