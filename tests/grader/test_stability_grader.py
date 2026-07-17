from pathlib import Path

import pytest

from hefesto.schemas.core import TestCase, Output, Objective
from hefesto.grader.stability_grader import StabilityGrader
from hefesto.scoring.ucc_scoring import stability_score

FIXT = Path(__file__).resolve().parents[1] / "fixtures" / "summary_metrics_run01.csv"


def _out(csv_path):
    return Output(text=str(csv_path), metadata={"csv": str(csv_path)})


def test_grade_matches_direct_stability_score():
    grader = StabilityGrader()
    metrics = grader.grade(TestCase(input=""), _out(FIXT), Objective(goal="x"))
    expected = stability_score({
        "pending_pods": 30.283333333333335,
        "time_with_pending": 0.8666666666666667,
        "cost": 0.04890666666666668,
        "number_of_migrations": 40.0,
    })
    assert metrics.scores["stability"] == pytest.approx(expected, abs=1e-9)


def test_grade_in_expected_band():
    grader = StabilityGrader()
    metrics = grader.grade(TestCase(input=""), _out(FIXT), Objective(goal="x"))
    assert metrics.scores["stability"] == pytest.approx(0.5619, abs=1e-3)


def test_missing_metric_raises(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text(",mean,min,max,std,median\ncost,0.04,0,0,0,0\n")
    with pytest.raises(KeyError):
        StabilityGrader().grade(TestCase(input=""), _out(bad), Objective(goal="x"))
