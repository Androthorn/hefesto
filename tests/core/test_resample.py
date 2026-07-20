# tests/core/test_resample.py
"""Resampling da taxa de falsa promocao -- a analise primaria do workshop.

Divide repetidamente um conjunto de replicas NULAS (todas do mesmo prompt)
em dois bracos e aplica cada regra de promocao. Como os dois bracos vem do
mesmo prompt, toda promocao e falsa por construcao.

Nao-parametrico de proposito: usa a distribuicao empirica, entao a mistura
bimodal (platO + thrash) nao e problema -- ela e parte do que engana as
regras ingenuas.
"""
import pytest

from hefesto.core.resample import (bootstrap_rate_ci, false_promotion_rates,
                                   split_arms)


def _null_scores(n, seed=0):
    import random
    rng = random.Random(seed)
    return [rng.gauss(0.7521, 0.0216) for _ in range(n)]


def test_split_arms_are_disjoint_and_sized_k():
    import random
    scores = list(range(24))

    a, b = split_arms(scores, k=12, rng=random.Random(0))

    assert len(a) == len(b) == 12
    assert sorted(a + b) == scores  # particao exata, sem reposicao


def test_split_arms_rejects_k_larger_than_half():
    import random

    with pytest.raises(ValueError, match="2 \\* k"):
        split_arms(list(range(10)), k=6, rng=random.Random(0))


def test_naive_rule_promotes_noise_about_half_the_time():
    # A regra do ADRS (promove se a media do candidato e maior). Sob a nula
    # e cara-ou-coroa por construcao -- e o ~50% que o paper documenta.
    rates = false_promotion_rates(_null_scores(24), k=12, n_splits=4000,
                                  delta_min=0.05, alpha=0.05, epsilon=1.0, seed=1)

    assert 0.42 < rates["naive"] < 0.58


def test_new_gate_holds_far_below_alpha_under_the_null():
    rates = false_promotion_rates(_null_scores(24), k=12, n_splits=4000,
                                  delta_min=0.05, alpha=0.05, epsilon=1.0, seed=1)

    assert rates["gate"] <= 0.05


def test_legacy_rule_sits_between_the_two():
    # eps*sigma nao e cara-ou-coroa em k=12, mas tambem nao tem alvo:
    # a taxa e uma funcao de k, nao de um alpha declarado.
    rates = false_promotion_rates(_null_scores(24), k=12, n_splits=4000,
                                  delta_min=0.05, alpha=0.05, epsilon=1.0, seed=1)

    assert rates["gate"] <= rates["legacy"] < rates["naive"]


def test_rates_are_deterministic_given_a_seed():
    scores = _null_scores(24)
    kw = dict(k=12, n_splits=500, delta_min=0.05, alpha=0.05, epsilon=1.0, seed=42)

    assert false_promotion_rates(scores, **kw) == false_promotion_rates(scores, **kw)


def test_bootstrap_ci_brackets_the_point_estimate():
    # O IC vem de reamostrar as REPLICAS (a fonte real de incerteza), nao de
    # contar divisoes -- elas se sobrepoem e nao sao evidencia independente.
    scores = _null_scores(24)
    point = false_promotion_rates(scores, k=12, n_splits=1000, delta_min=0.05,
                                  alpha=0.05, epsilon=1.0, seed=3)
    ci = bootstrap_rate_ci(scores, k=12, n_splits=200, n_boot=200,
                           delta_min=0.05, alpha=0.05, epsilon=1.0, seed=3)

    for rule in ("naive", "legacy", "gate"):
        lo, hi = ci[rule]
        assert lo <= point[rule] <= hi, f"{rule}: {point[rule]} fora de [{lo}, {hi}]"
