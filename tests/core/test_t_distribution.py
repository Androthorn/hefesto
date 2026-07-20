# tests/core/test_t_distribution.py
"""Valida a t inversa caseira (sem scipy no ambiente) contra tabela publicada.

Se estes valores derivarem, todo limite inferior do gate esta errado em silencio.
"""
import pytest

from hefesto.core.gate import _t_ppf

# Percentil 95 da Student-t (unilateral alpha=0.05), tabela padrao.
T_95 = {1: 6.314, 2: 2.920, 5: 2.015, 10: 1.812,
        20: 1.725, 30: 1.697, 100: 1.660}

# Percentil 97.5 (bilateral alpha=0.05).
T_975 = {1: 12.706, 5: 2.571, 10: 2.228, 20: 2.086, 30: 2.042}


@pytest.mark.parametrize("df,expected", sorted(T_95.items()))
def test_t_ppf_matches_table_at_95(df, expected):
    assert _t_ppf(0.95, df) == pytest.approx(expected, abs=0.001)


@pytest.mark.parametrize("df,expected", sorted(T_975.items()))
def test_t_ppf_matches_table_at_975(df, expected):
    assert _t_ppf(0.975, df) == pytest.approx(expected, abs=0.001)


def test_t_approaches_normal_for_large_df():
    assert _t_ppf(0.95, 100000) == pytest.approx(1.6449, abs=0.001)
