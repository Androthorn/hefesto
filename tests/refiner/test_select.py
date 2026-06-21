from hefesto.schemas.core import TestCase, Output, Metrics, ScoredResult
from hefesto.refiner.select import select_contrast


def _r(name, score):
    return ScoredResult(
        case=TestCase(input=name), output=Output(text=name),
        metrics=Metrics(scores={"q": score}), composite=score,
    )


def test_returns_best_then_worst():
    results = [_r("a", 0.1), _r("b", 0.9), _r("c", 0.5), _r("d", 0.3)]
    out = select_contrast(results, k=1)
    assert [r.case.input for r in out] == ["b", "a"]


def test_dedups_when_overlap():
    results = [_r("a", 0.1), _r("b", 0.9)]
    out = select_contrast(results, k=2)  # best 2 + worst 2 overlap fully
    assert [r.case.input for r in out] == ["b", "a"]  # each once
