from hefesto.schemas.core import Metrics
from hefesto.score.aggregate import composite_score


def test_weighted_average_renormalizes():
    m = Metrics(scores={"a": 1.0, "b": 0.0})
    assert composite_score(m, {"a": 3.0, "b": 1.0}) == 0.75  # (3*1+1*0)/4


def test_missing_weighted_key_scores_zero():
    m = Metrics(scores={"a": 1.0})
    assert composite_score(m, {"a": 1.0, "b": 1.0}) == 0.5  # b missing -> 0


def test_unweighted_metric_ignored():
    m = Metrics(scores={"a": 1.0, "junk": 0.0})
    assert composite_score(m, {"a": 1.0}) == 1.0


def test_no_weights_is_mean():
    m = Metrics(scores={"a": 0.4, "b": 0.6})
    assert composite_score(m, {}) == 0.5


def test_empty_everything_is_zero():
    assert composite_score(Metrics(scores={}), {}) == 0.0
