"""Deterministic in-memory LLM provider for tests."""
from collections.abc import Callable
from itertools import cycle
from hefesto.llm.base import LLMProvider, LLMMessage, LLMResponse


class FakeLLMProvider(LLMProvider):
    def __init__(
        self,
        responses: list[str] | None = None,
        handler: Callable[[list[LLMMessage]], str] | None = None,
        model: str = "fake-model",
    ) -> None:
        self._cycle = cycle(responses) if responses else None
        self._handler = handler
        self._model = model
        self.calls: list[list[LLMMessage]] = []

    def complete(self, messages, temperature=0.7, max_tokens=4096) -> LLMResponse:
        self.calls.append(list(messages))
        if self._handler is not None:
            content = self._handler(messages)
        elif self._cycle is not None:
            content = next(self._cycle)
        else:
            content = ""
        return LLMResponse(content=content, model=self._model, usage=None)

    def get_model_name(self) -> str:
        return self._model
