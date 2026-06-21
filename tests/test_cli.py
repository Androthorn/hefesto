# tests/test_cli.py
from typer.testing import CliRunner
from hefesto.cli import app

runner = CliRunner()


def test_init_scaffolds_files(tmp_path):
    result = runner.invoke(app, ["init", "--path", str(tmp_path)])
    assert result.exit_code == 0
    assert (tmp_path / "hefesto.yaml").exists()
    assert (tmp_path / "objective.yaml").exists()
    assert (tmp_path / "prompt.txt").exists()
    assert "<required>" in (tmp_path / "hefesto.yaml").read_text()


def test_help_lists_core_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ("init", "refine", "calibrate", "eval", "history", "diff"):
        assert cmd in result.output
