from hefesto.llm.base import LLMMessage
from hefesto.llm.fake import FakeLLMProvider


def test_returns_scripted_responses_in_order():
    p = FakeLLMProvider(responses=["a", "b"])
    msgs = [LLMMessage(role="user", content="x")]
    assert p.complete(msgs).content == "a"
    assert p.complete(msgs).content == "b"
    assert p.complete(msgs).content == "a"  # cycles


def test_handler_sees_messages_and_records_calls():
    p = FakeLLMProvider(handler=lambda msgs: msgs[-1].content.upper())
    out = p.complete([LLMMessage(role="user", content="hi")])
    assert out.content == "HI"
    assert p.calls[-1][-1].content == "hi"
