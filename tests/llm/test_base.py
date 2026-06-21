from hefesto.llm.base import LLMMessage, LLMResponse, LLMProvider


def test_llm_message_roundtrips():
    m = LLMMessage(role="user", content="hi")
    assert m.role == "user" and m.content == "hi"


def test_llm_provider_is_abstract():
    import pytest
    with pytest.raises(TypeError):
        LLMProvider()  # abstract, cannot instantiate
