from hefesto.schemas.core import TestCase
from hefesto.dataset.base import DatasetSplit


def split_cases(cases: list[TestCase], test_fraction: float) -> DatasetSplit:
    n = len(cases)
    if n < 2:
        raise ValueError("need at least 2 cases to form a dev/test split")
    n_test = round(n * test_fraction)
    n_test = max(1, min(n_test, n - 1))  # at least 1 in each split
    return DatasetSplit(dev=cases[: n - n_test], test=cases[n - n_test :])
