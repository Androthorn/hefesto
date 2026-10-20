import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path("/home/andre/projetos")

pytestmark = pytest.mark.skipif(
    not (ROOT / "cert_compare.py").exists(),
    reason=f"external module {ROOT / 'cert_compare.py'} not available (author's machine only)",
)


def _mod():
    sys.path.insert(0, str(ROOT))
    return importlib.import_module("cert_compare")


def test_overlapping_distributions_are_plausible():
    cc = _mod()
    full = [0.60, 0.65, 0.70, 0.55, 0.68, 0.62, 0.71, 0.58, 0.66, 0.63]
    light = [0.61, 0.64, 0.69, 0.59]
    r = cc.compare(full, light)
    assert r["plausible"] is True
    assert abs(r["mean_shift"]) <= 0.5 * r["full_std"]


def test_systematic_shift_is_flagged():
    cc = _mod()
    full = [0.60, 0.65, 0.70, 0.55, 0.68, 0.62, 0.71, 0.58, 0.66, 0.63]
    light = [0.30, 0.28, 0.33, 0.31]  # clearly shifted down
    r = cc.compare(full, light)
    assert r["plausible"] is False


def test_missing_csv_returns_clean_error(monkeypatch, capsys):
    cc = _mod()
    monkeypatch.setattr("sys.argv", ["cert_compare.py", "/nonexistent/full.csv", "/nonexistent/light.csv"])
    rc = cc.main()
    assert rc != 0
    err = capsys.readouterr().err
    assert "CSV" in err  # mensagem clara, não um traceback cru
