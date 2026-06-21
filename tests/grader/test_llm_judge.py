from hefesto.schemas.core import TestCase, Output, Objective, Rubric, RubricDimension
from hefesto.llm.fake import FakeLLMProvider
from hefesto.grader.llm_judge import LLMJudge, normalize_absolute


def test_normalize_absolute():
    assert normalize_absolute(1) == 0.0
    assert normalize_absolute(10) == 1.0
    assert normalize_absolute(100) == 1.0  # clamped


def test_judge_returns_normalized_metrics():
    fake = FakeLLMProvider(responses=['{"clarity": 10, "accuracy": 1}'])
    rubric = Rubric(dimensions=[
        RubricDimension(name="clarity", description="d", weight=1.0),
        RubricDimension(name="accuracy", description="d", weight=1.0),
    ])
    m = LLMJudge(provider=fake, rubric=rubric).grade(
        TestCase(input="x"), Output(text="y"), Objective(goal="g"),
    )
    assert m.scores == {"clarity": 1.0, "accuracy": 0.0}


def test_missing_dimension_defaults_zero():
    fake = FakeLLMProvider(responses=['{"clarity": 10}'])
    rubric = Rubric(dimensions=[
        RubricDimension(name="clarity", description="d", weight=1.0),
        RubricDimension(name="accuracy", description="d", weight=1.0),
    ])
    m = LLMJudge(provider=fake, rubric=rubric).grade(
        TestCase(input="x"), Output(text="y"), Objective(goal="g"),
    )
    assert m.scores["accuracy"] == 0.0
