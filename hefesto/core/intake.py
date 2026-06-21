"""Intake classification and headroom checking."""

from hefesto.schemas.core import Objective

_ORACLE_KEYWORDS = (
    "compile", "run", "exact", "regex", "schema",
    "valid json", "cite", "citation", "fact",
)


def classify_objective(objective: Objective, has_user_metrics: bool) -> str:
    """Classify objective signal tier.

    Returns "real" if has_user_metrics, "verifiable" if goal contains oracle keyword,
    else "judge".
    """
    if has_user_metrics:
        return "real"
    goal = objective.goal.lower()
    if any(k in goal for k in _ORACLE_KEYWORDS):
        return "verifiable"
    return "judge"


def no_headroom(champion_score: float, target: float | None, headroom_min: float) -> bool:
    """Check if champion has no headroom against target or ceiling.

    Returns True if (target is not None and champion_score >= target - headroom_min)
    OR champion_score >= 1.0 - headroom_min.
    """
    if target is not None and champion_score >= target - headroom_min:
        return True
    return champion_score >= 1.0 - headroom_min
