from hefesto.schemas.core import TestCase, Output
from hefesto.runner.base import fill_placeholders


class EchoRunner:
    def run(self, prompt: str, case: TestCase) -> Output:
        return Output(text=fill_placeholders(prompt, case))
