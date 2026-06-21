from hefesto.schemas.core import Objective
from hefesto.core.intake import classify_objective, no_headroom


def test_real_when_user_metrics():
    assert classify_objective(Objective(goal="be nice"), has_user_metrics=True) == "real"


def test_verifiable_on_oracle_keyword():
    assert classify_objective(Objective(goal="must be valid json"), False) == "verifiable"


def test_judge_default():
    assert classify_objective(Objective(goal="be more persuasive"), False) == "judge"


def test_no_headroom_against_target():
    assert no_headroom(0.97, target=1.0, headroom_min=0.05) is True
    assert no_headroom(0.90, target=1.0, headroom_min=0.05) is False


def test_no_headroom_against_ceiling():
    assert no_headroom(0.98, target=None, headroom_min=0.05) is True
