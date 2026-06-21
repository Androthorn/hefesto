import json
import re
from hefesto.llm.base import LLMProvider, LLMMessage
from hefesto.schemas.core import TestCase, Output, Objective, Metrics, Rubric

_FENCE = re.compile(r"^```[a-zA-Z]*\n|\n```$", re.MULTILINE)


def normalize_absolute(raw: float) -> float:
    return max(0.0, min(1.0, (raw - 1) / 9))


class LLMJudge:
    def __init__(self, provider: LLMProvider, rubric: Rubric) -> None:
        self.provider = provider
        self.rubric = rubric

    def grade(self, case: TestCase, output: Output, objective: Objective) -> Metrics:
        dims = ", ".join(d.name for d in self.rubric.dimensions)
        prompt = (
            f"Objective: {objective.goal}\n"
            f"Input: {case.input}\nOutput: {output.text}\n"
            f"Score each dimension ({dims}) from 1-10. "
            "Return ONLY a JSON object keyed by dimension name."
        )
        resp = self.provider.complete([LLMMessage(role="user", content=prompt)])
        raw = json.loads(_FENCE.sub("", resp.content).strip())
        scores = {
            d.name: normalize_absolute(float(raw.get(d.name, 1)))
            for d in self.rubric.dimensions
        }
        return Metrics(scores=scores)
