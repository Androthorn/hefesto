from hefesto.schemas.core import TestCase, Output, Metrics, ScoredResult, Objective
from hefesto.llm.fake import FakeLLMProvider
from hefesto.refiner.refiner import Refiner, rule_density, REFINEMENT_SYSTEM_PROMPT


def test_rule_density_counts_nested_markers():
    assert rule_density("1.a do this 2.b do that") == 2
    assert rule_density("plain guidance, no nesting") == 0


def test_propose_returns_candidate_and_uses_system_prompt():
    captured = {}

    def handler(msgs):
        captured["system"] = msgs[0].content
        captured["user"] = msgs[-1].content
        return "REFINED PROMPT"

    fake = FakeLLMProvider(handler=handler)
    cases = [ScoredResult(
        case=TestCase(input="2+2"), output=Output(text="5"),
        metrics=Metrics(scores={"q": 0.0}), composite=0.0,
    )]
    out = Refiner(provider=fake).propose("OLD PROMPT", cases, Objective(goal="be correct"))
    assert out == "REFINED PROMPT"
    assert captured["system"] == REFINEMENT_SYSTEM_PROMPT
    assert "2+2" in captured["user"] and "OLD PROMPT" in captured["user"]
