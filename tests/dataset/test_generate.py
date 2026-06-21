import pytest
from hefesto.schemas.core import Objective
from hefesto.llm.fake import FakeLLMProvider
from hefesto.dataset.generate import GeneratedDataset, parse_cases


def test_parse_cases_strips_fences():
    text = '```json\n["what is 2+2?", "capital of France?"]\n```'
    cases = parse_cases(text)
    assert [c.input for c in cases] == ["what is 2+2?", "capital of France?"]


def test_generate_provides_split():
    fake = FakeLLMProvider(responses=['["a","b","c","d"]'])
    ds = GeneratedDataset(
        provider=fake, objective=Objective(goal="g"), count=4, test_fraction=0.5,
    )
    split = ds.provide()
    assert len(split.dev) == 2 and len(split.test) == 2


def test_generate_rejects_too_few():
    fake = FakeLLMProvider(responses=['["only one"]'])
    ds = GeneratedDataset(
        provider=fake, objective=Objective(goal="g"), count=4, test_fraction=0.5,
    )
    with pytest.raises(ValueError):
        ds.provide()
