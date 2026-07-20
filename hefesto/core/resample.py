"""Taxa de falsa promocao por resampling -- analise primaria do workshop.

Dado um conjunto de replicas NULAS (todas do mesmo prompt), divide-as
repetidamente em dois bracos e aplica cada regra de promocao. Os dois bracos
vem do mesmo prompt, entao toda promocao e falsa por construcao.

Tres regras, porque sao tres coisas diferentes:
  naive   -- promove se a media do candidato e maior. E a regra do ADRS que o
             paper critica, e sob a nula da ~50% por construcao.
  legacy  -- `delta > epsilon * sigma` do hefesto. Em n=1 degenera para naive
             (pstdev de um delta unico e zero); em n maior fica conservadora.
             O defeito nao e ser permissiva, e nao ter alvo: a taxa e funcao
             de k, nunca de um alpha declarado.
  gate    -- o gate da opcao B (LB > delta_min). Sob alpha declarado.

Nao-parametrico de proposito: usa a distribuicao empirica das replicas, entao
a mistura bimodal (plato + thrash) nao invalida nada -- ela e parte do que
engana as duas primeiras regras.
"""
import random
import statistics

from hefesto.core.gate import legacy_epsilon_sigma_rule, should_promote

RULES = ("naive", "legacy", "gate")


def split_arms(scores: list[float], k: int,
               rng: random.Random) -> tuple[list[float], list[float]]:
    """Particiona `scores` em dois bracos disjuntos de tamanho k, sem reposicao."""
    if 2 * k > len(scores):
        raise ValueError(f"2 * k = {2 * k} excede as {len(scores)} replicas disponiveis")
    picked = rng.sample(scores, 2 * k)
    return picked[:k], picked[k:]


def _verdicts(cand: list[float], champ: list[float],
              delta_min: float, alpha: float, epsilon: float) -> dict[str, bool]:
    return {
        "naive": statistics.fmean(cand) > statistics.fmean(champ),
        "legacy": legacy_epsilon_sigma_rule(cand, champ, epsilon),
        "gate": should_promote(cand, champ, delta_min=delta_min, alpha=alpha),
    }


def false_promotion_rates(scores: list[float], k: int, n_splits: int,
                          delta_min: float, alpha: float, epsilon: float,
                          seed: int) -> dict[str, float]:
    """Fracao de divisoes em que cada regra promove. Tudo aqui e falso positivo."""
    rng = random.Random(seed)
    counts = dict.fromkeys(RULES, 0)
    for _ in range(n_splits):
        cand, champ = split_arms(scores, k, rng)
        for rule, promoted in _verdicts(cand, champ, delta_min, alpha, epsilon).items():
            counts[rule] += promoted
    return {rule: counts[rule] / n_splits for rule in RULES}


def bootstrap_rate_ci(scores: list[float], k: int, n_splits: int, n_boot: int,
                      delta_min: float, alpha: float, epsilon: float, seed: int,
                      ci: float = 0.95) -> dict[str, tuple[float, float]]:
    """IC percentil da taxa, reamostrando as REPLICAS.

    A incerteza que importa vem de so existirem `len(scores)` runs reais, nao
    do numero de divisoes: divisoes se sobrepoem e nao sao evidencia
    independente. Por isso o bootstrap e sobre as replicas, e o n a reportar
    e o de runs, nunca o de divisoes.
    """
    rng = random.Random(seed)
    draws: dict[str, list[float]] = {rule: [] for rule in RULES}
    for i in range(n_boot):
        resampled = [rng.choice(scores) for _ in range(len(scores))]
        rates = false_promotion_rates(resampled, k, n_splits, delta_min, alpha,
                                      epsilon, seed=rng.randrange(2**31))
        for rule in RULES:
            draws[rule].append(rates[rule])

    lo_q, hi_q = (1 - ci) / 2, 1 - (1 - ci) / 2
    out = {}
    for rule in RULES:
        ordered = sorted(draws[rule])
        lo = ordered[max(0, int(lo_q * n_boot) - 1)]
        hi = ordered[min(n_boot - 1, int(hi_q * n_boot))]
        out[rule] = (lo, hi)
    return out
