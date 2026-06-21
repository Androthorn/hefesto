import json
import re
from hefesto.llm.base import LLMProvider, LLMMessage
from hefesto.schemas.core import Objective, TestCase
from hefesto.dataset.base import DatasetSplit
from hefesto.dataset.split import split_cases

_FENCE = re.compile(r"^```[a-zA-Z]*\n|\n```$", re.MULTILINE)


def parse_cases(text: str) -> list[TestCase]:
    cleaned = _FENCE.sub("", text).strip()
    data = json.loads(cleaned)
    return [TestCase(input=str(item)) for item in data]


class GeneratedDataset:
    def __init__(self, provider: LLMProvider, objective: Objective,
                 count: int, test_fraction: float) -> None:
        self.provider = provider
        self.objective = objective
        self.count = count
        self.test_fraction = test_fraction

    def provide(self) -> DatasetSplit:
        prompt = (
            f"Generate {self.count} diverse, realistic test inputs for a prompt "
            f"whose objective is: {self.objective.goal}\n"
            "Return ONLY a JSON array of input strings."
        )
        resp = self.provider.complete([LLMMessage(role="user", content=prompt)])
        cases = parse_cases(resp.content)
        if len(cases) < 2:
            raise ValueError("dataset generation produced fewer than 2 cases")
        return split_cases(cases, self.test_fraction)
