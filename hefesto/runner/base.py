from typing import Protocol
from hefesto.schemas.core import TestCase, Output


def fill_placeholders(prompt: str, case: TestCase) -> str:
    return (
        prompt
        .replace("{{input}}", case.input)
        .replace("{{context}}", str(case.metadata.get("context", "")))
    )


class Runner(Protocol):
    def run(self, prompt: str, case: TestCase) -> Output: ...
