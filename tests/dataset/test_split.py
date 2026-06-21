import pytest
from hefesto.schemas.core import TestCase
from hefesto.dataset.split import split_cases


def _cases(n):
    return [TestCase(input=str(i)) for i in range(n)]


def test_split_fraction_sizes():
    s = split_cases(_cases(10), test_fraction=0.4)
    assert len(s.test) == 4 and len(s.dev) == 6


def test_split_is_deterministic_tail_is_test():
    s = split_cases(_cases(5), test_fraction=0.4)  # round(2.0)=2
    assert [c.input for c in s.test] == ["3", "4"]
    assert [c.input for c in s.dev] == ["0", "1", "2"]


def test_split_guarantees_one_each_for_small_sets():
    s = split_cases(_cases(2), test_fraction=0.9)
    assert len(s.dev) == 1 and len(s.test) == 1


def test_split_rejects_single_case():
    with pytest.raises(ValueError):
        split_cases(_cases(1), test_fraction=0.4)
