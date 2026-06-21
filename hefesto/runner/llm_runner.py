from hefesto.llm.base import LLMProvider, LLMMessage
from hefesto.schemas.core import TestCase, Output
from hefesto.runner.base import fill_placeholders


class LLMRunner:
    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider

    def run(self, prompt: str, case: TestCase) -> Output:
        filled = fill_placeholders(prompt, case)
        resp = self.provider.complete([LLMMessage(role="user", content=filled)])
        return Output(text=resp.content, model=resp.model)
