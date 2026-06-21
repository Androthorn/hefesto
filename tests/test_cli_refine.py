# tests/test_cli_refine.py
# Strategy: monkeypatch create_provider to return FakeLLMProvider instances so
# `hefesto refine` runs with no network. Build a real config + files in tmp_path.
import yaml
from typer.testing import CliRunner
import hefesto.cli as cli
from hefesto.llm.fake import FakeLLMProvider

runner = CliRunner()


def _write_project(tmp_path):
    (tmp_path / "objective.yaml").write_text(
        "goal: be brief\nweights: {brevity: 1.0}\nsuccess_criteria: []\ninvariants: []\n"
    )
    (tmp_path / "prompt.txt").write_text("Answer briefly: {{input}}\n")
    cfg = {
        "providers": {"default": {"provider": "openai", "model": "x"}},
        "objective": str(tmp_path / "objective.yaml"),
        "prompt": str(tmp_path / "prompt.txt"),
        "dataset": {"source": "generate", "count": 4, "test_fraction": 0.5},
        "grader": "llm_judge",
        "loop": {"max_iter": 1, "patience": 1, "k": 1, "epsilon_k": 0.0,
                 "headroom_min": 0.0},
        "store_path": str(tmp_path / "h.db"),
    }
    (tmp_path / "hefesto.yaml").write_text(yaml.safe_dump(cfg))
    return str(tmp_path / "hefesto.yaml")


def test_refine_runs_offline(tmp_path, monkeypatch):
    cfg_path = _write_project(tmp_path)

    def fake_provider(_cfg):
        # dataset gen -> 4 inputs; judge -> score; refiner -> a candidate prompt
        return FakeLLMProvider(handler=lambda msgs: _route(msgs))

    def _route(msgs):
        text = msgs[-1].content
        if "JSON array" in text:
            return '["a","b","c","d"]'
        if "JSON object" in text:
            return '{"brevity": 8}'
        return "Answer: {{input}}"

    monkeypatch.setattr(cli, "create_provider", fake_provider)
    result = runner.invoke(cli.app, ["refine", "--config", cfg_path])
    assert result.exit_code == 0, result.output
    assert "champion" in result.output.lower()
