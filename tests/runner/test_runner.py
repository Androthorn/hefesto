from hefesto.schemas.core import TestCase
from hefesto.llm.fake import FakeLLMProvider
from hefesto.runner.base import fill_placeholders
from hefesto.runner.echo_runner import EchoRunner
from hefesto.runner.llm_runner import LLMRunner


def test_fill_placeholders_input_and_context():
    case = TestCase(input="42", metadata={"context": "ctx"})
    out = fill_placeholders("Q: {{input}} / {{context}}", case)
    assert out == "Q: 42 / ctx"


def test_echo_runner_returns_filled_prompt():
    out = EchoRunner().run("echo {{input}}", TestCase(input="hi"))
    assert out.text == "echo hi"


def test_llm_runner_sends_filled_prompt():
    fake = FakeLLMProvider(handler=lambda msgs: f"ANSWER<{msgs[-1].content}>")
    out = LLMRunner(provider=fake).run("solve {{input}}", TestCase(input="2+2"))
    assert out.text == "ANSWER<solve 2+2>"
    assert out.model == "fake-model"
