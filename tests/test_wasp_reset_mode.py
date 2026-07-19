from pathlib import Path

from hefesto.schemas.core import TestCase
from hefesto.runner.wasp_runner import WASPRunner

FIXT = Path(__file__).resolve().parent / "fixtures" / "summary_metrics_run01.csv"


def _make_runner(tmp_path, captured):
    root = tmp_path / "simulatormeu"
    (root / "ai-engine" / "prompts").mkdir(parents=True)
    cfg = root / "config_compressed.yaml"
    cfg.write_text("x: 1\n")

    def fake_cmd(cmd, **kwargs):
        captured["env"] = kwargs["env"]
        dest = Path(cmd[4])
        (dest / "analyzer" / "summary").mkdir(parents=True, exist_ok=True)
        (dest / "analyzer" / "summary" / "summary_metrics_x.csv").write_text(FIXT.read_text())
        (dest / "provenance.json").write_text('{"model":"m"}')
        class R: returncode = 0
        return R()

    return WASPRunner(root, cfg, tmp_path / "runs", runner_cmd=fake_cmd)


def test_reset_mode_from_metadata_overrides_default(tmp_path):
    captured = {}
    runner = _make_runner(tmp_path, captured)  # default reset_mode="full"
    runner.run("PROMPT", TestCase(input="", metadata={"replica": 2, "reset_mode": "light"}))
    assert captured["env"]["RESET_MODE"] == "light"


def test_reset_mode_defaults_to_constructor(tmp_path):
    captured = {}
    runner = _make_runner(tmp_path, captured)  # default reset_mode="full"
    runner.run("PROMPT", TestCase(input="", metadata={"replica": 1}))
    assert captured["env"]["RESET_MODE"] == "full"
