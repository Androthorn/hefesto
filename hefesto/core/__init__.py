"""Core components for ADRS - analyzer, generator, differ, evaluator, selector."""

# Note: Old ADRS modules (analyzer, generator, differ, evaluator, selector) have stale imports
# and will be removed in Task 17. For now, we only expose intake.
from hefesto.core.intake import classify_objective, no_headroom

__all__ = [
    "classify_objective",
    "no_headroom",
]
