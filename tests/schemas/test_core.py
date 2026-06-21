import pytest
from pydantic import ValidationError
from hefesto.schemas.core import (
    TestCase, Output, Metrics, ScoredResult,
    Rubric, RubricDimension, Objective,
)


def test_testcase_minimal():
    c = TestCase(input="2+2?")
    assert c.input == "2+2?" and c.expected is None and c.metadata == {}


def test_metrics_rejects_out_of_range_score():
    with pytest.raises(ValidationError):
        Metrics(scores={"clarity": 1.5})


def test_scored_result_composes():
    c = TestCase(input="x")
    o = Output(text="y")
    m = Metrics(scores={"clarity": 0.8})
    r = ScoredResult(case=c, output=o, metrics=m, composite=0.8)
    assert r.composite == 0.8 and r.metrics.scores["clarity"] == 0.8


def test_objective_defaults():
    obj = Objective(goal="be concise")
    assert obj.weights == {} and obj.invariants == []


def test_rubric_dimension_weight():
    rub = Rubric(dimensions=[RubricDimension(name="clarity", description="d", weight=1.0)])
    assert rub.dimensions[0].weight == 1.0
