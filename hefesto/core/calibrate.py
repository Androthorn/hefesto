from typing import Literal
from pydantic import BaseModel
from hefesto.schemas.core import TestCase, Output, Objective
from hefesto.grader.base import Grader
from hefesto.score.aggregate import composite_score


class ReferenceExample(BaseModel):
    case: TestCase
    output: Output
    label: Literal["good", "bad"]


def calibrate_judge(
    grader: Grader,
    objective: Objective,
    weights: dict[str, float],
    reference: list[ReferenceExample],
    *,
    good_threshold: float = 0.6,
    bad_threshold: float = 0.4,
) -> float:
    if not reference:
        return 0.0
    agree = 0
    for ex in reference:
        metrics = grader.grade(ex.case, ex.output, objective)
        score = composite_score(metrics, weights)
        if ex.label == "good" and score >= good_threshold:
            agree += 1
        elif ex.label == "bad" and score <= bad_threshold:
            agree += 1
    return agree / len(reference)
