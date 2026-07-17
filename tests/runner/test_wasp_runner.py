from pathlib import Path

import pytest

from hefesto.schemas.core import TestCase
from hefesto.runner.wasp_runner import WASPRunner, RunnerError


def _make_env(tmp_path):
    root = tmp_path / "simulatormeu"
    (root / "ai-engine" / "prompts").mkdir(parents=True)
    (root / "ai-engine" / "prompts" / "consolidator_agent_p0.txt").write_text("P0-ORIG")
    (root / "ai-engine" / "prompts" / "consolidator_agent_p4.txt").write_text("P4-ORIG")
    runs = tmp_path / "runs-workshop"
    cfg = root / "config_compressed.yaml"
    cfg.write_text("dummy: true\n")
    return root, runs, cfg


def _fake_cmd_factory(runs_dir):
    def fake(cmd, **kwargs):
        dest = Path(cmd[4])  # bash run_one_replica.sh <prompt> <config> <dest>
        (dest / "analyzer" / "summary").mkdir(parents=True, exist_ok=True)
        (dest / "analyzer" / "summary" / "summary_metrics_x.csv").write_text(
            ",mean,min,max,std,median\ncost,0.04,0,0,0,0\n")
        (dest / "provenance.json").write_text('{"model":"google/gemini-2.5-flash"}')
        class R: returncode = 0
        return R()
    return fake


def test_writes_candidate_and_leaves_p0_p4_untouched(tmp_path):
    root, runs, cfg = _make_env(tmp_path)
    runner = WASPRunner(root, cfg, runs, runner_cmd=_fake_cmd_factory(runs))
    runner.run("CANDIDATE PROMPT", TestCase(input="", metadata={"replica": 1}))
    workshop = root / "ai-engine" / "prompts" / "workshop"
    written = list(workshop.glob("cand_*.txt"))
    assert len(written) == 1
    assert written[0].read_text() == "CANDIDATE PROMPT"
    assert (root / "ai-engine" / "prompts" / "consolidator_agent_p0.txt").read_text() == "P0-ORIG"
    assert (root / "ai-engine" / "prompts" / "consolidator_agent_p4.txt").read_text() == "P4-ORIG"


def test_output_points_to_csv_and_model(tmp_path):
    root, runs, cfg = _make_env(tmp_path)
    runner = WASPRunner(root, cfg, runs, runner_cmd=_fake_cmd_factory(runs))
    out = runner.run("X", TestCase(input="", metadata={"replica": 2}))
    assert out.metadata["csv"].endswith("summary_metrics_x.csv")
    assert Path(out.metadata["csv"]).exists()
    assert out.model == "google/gemini-2.5-flash"
    assert out.text == out.metadata["csv"]


def test_reset_mode_passed_in_env(tmp_path):
    root, runs, cfg = _make_env(tmp_path)
    seen = {}
    def spy(cmd, **kwargs):
        seen["env"] = kwargs.get("env", {})
        return _fake_cmd_factory(runs)(cmd, **kwargs)
    WASPRunner(root, cfg, runs, reset_mode="full", runner_cmd=spy).run(
        "X", TestCase(input="", metadata={"replica": 3}))
    assert seen["env"].get("RESET_MODE") == "full"


def test_missing_csv_raises(tmp_path):
    root, runs, cfg = _make_env(tmp_path)
    def cmd_no_csv(cmd, **kwargs):
        class R: returncode = 0
        return R()
    runner = WASPRunner(root, cfg, runs, runner_cmd=cmd_no_csv)
    with pytest.raises(RunnerError):
        runner.run("X", TestCase(input="", metadata={"replica": 4}))
