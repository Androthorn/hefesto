from typing import Protocol
from hefesto.schemas.core import TestCase, Output, Objective, Metrics


class Grader(Protocol):
    def grade(self, case: TestCase, output: Output, objective: Objective) -> Metrics: ...
