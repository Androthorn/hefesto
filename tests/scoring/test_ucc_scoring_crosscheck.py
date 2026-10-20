import importlib.util
from pathlib import Path

import pytest

from hefesto.scoring import ucc_scoring as hef

_ANALYSIS_PATH = Path(__file__).resolve().parents[3] / "analysis" / "ucc_scoring.py"  # .../projetos

pytestmark = pytest.mark.skipif(
    not _ANALYSIS_PATH.exists(),
    reason=f"external file {_ANALYSIS_PATH} not available (author's machine only)",
)


def _load_analysis_module():
    spec = importlib.util.spec_from_file_location("analysis_ucc_scoring", _ANALYSIS_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SAMPLES = [
    {"pending_pods": 30.28, "time_with_pending": 0.867, "cost": 0.0489, "number_of_migrations": 40.0},
    {"pending_pods": 0.0, "time_with_pending": 0.0, "cost": 0.0224, "number_of_migrations": 0.0},
    {"pending_pods": 100.0, "time_with_pending": 1.0, "cost": 0.1, "number_of_migrations": 200.0},
    {"pending_pods": 55.5, "time_with_pending": 0.5, "cost": 0.06, "number_of_migrations": 123.0},
]


def test_hefesto_copy_matches_analysis_source():
    ana = _load_analysis_module()
    for m in SAMPLES:
        assert abs(hef.stability_score(m) - ana.stability_score(m)) < 1e-12


def test_weights_and_fixed_cost_match():
    ana = _load_analysis_module()
    assert hef.WEIGHTS == ana.WEIGHTS
    assert hef.FIXED_COST == ana.FIXED_COST
