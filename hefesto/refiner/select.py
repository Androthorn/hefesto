from hefesto.schemas.core import ScoredResult


def select_contrast(results: list[ScoredResult], k: int) -> list[ScoredResult]:
    ranked = sorted(results, key=lambda r: r.composite, reverse=True)
    best = ranked[:k]
    worst = ranked[-k:] if k < len(ranked) else ranked
    ordered: list[ScoredResult] = []
    seen: set[int] = set()
    for r in best + list(reversed(worst)):
        if id(r) not in seen:
            seen.add(id(r))
            ordered.append(r)
    return ordered
