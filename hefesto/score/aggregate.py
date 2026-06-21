from hefesto.schemas.core import Metrics


def composite_score(metrics: Metrics, weights: dict[str, float]) -> float:
    if not weights:
        scores = list(metrics.scores.values())
        return sum(scores) / len(scores) if scores else 0.0
    total_w = sum(weights.values())
    if total_w == 0:
        return 0.0
    acc = sum(w * metrics.scores.get(k, 0.0) for k, w in weights.items())
    return acc / total_w
