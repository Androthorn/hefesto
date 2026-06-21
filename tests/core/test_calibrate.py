from hefesto.schemas.core import TestCase, Output, Objective, Rubric, RubricDimension
from hefesto.llm.fake import FakeLLMProvider
from hefesto.grader.llm_judge import LLMJudge
from hefesto.core.calibrate import calibrate_judge, ReferenceExample


def _judge(scripted):
    rubric = Rubric(dimensions=[RubricDimension(name="q", description="d", weight=1.0)])
    return LLMJudge(provider=FakeLLMProvider(responses=scripted), rubric=rubric)


def test_perfect_agreement():
    # good example judged 10 -> 1.0 (agrees); bad judged 1 -> 0.0 (agrees)
    judge = _judge(['{"q": 10}', '{"q": 1}'])
    ref = [
        ReferenceExample(case=TestCase(input="a"), output=Output(text="good"), label="good"),
        ReferenceExample(case=TestCase(input="b"), output=Output(text="bad"), label="bad"),
    ]
    agree = calibrate_judge(judge, Objective(goal="g"), {"q": 1.0}, ref)
    assert agree == 1.0


def test_half_agreement():
    # good judged 1 -> 0.0 (disagrees); bad judged 1 -> 0.0 (agrees)
    judge = _judge(['{"q": 1}', '{"q": 1}'])
    ref = [
        ReferenceExample(case=TestCase(input="a"), output=Output(text="g"), label="good"),
        ReferenceExample(case=TestCase(input="b"), output=Output(text="b"), label="bad"),
    ]
    assert calibrate_judge(judge, Objective(goal="g"), {"q": 1.0}, ref) == 0.5


def test_empty_reference_is_zero():
    judge = _judge(['{"q": 5}'])
    assert calibrate_judge(judge, Objective(goal="g"), {"q": 1.0}, []) == 0.0
