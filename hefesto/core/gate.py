"""Gate de promocao nao-pareado com margem (opcao B do ESTADO §4e).

Promove sse o limite inferior do IC unilateral de (media_cand - media_champ)
supera delta_min. Substitui o criterio `delta > epsilon * sigma`, que parava
em dois pontos: pareava replicas por zip (elas nao compartilham fonte de
variacao) e nao continha o `n` (rodar mais replicas nao comprava confianca).

Welch, nao Student: os dois bracos podem ter variancias diferentes -- e
justamente a hipotese de um candidato que muda a estabilidade.

Sem scipy no ambiente, a t inversa vem de `_t_ppf` (beta incompleta regularizada
por fracao continuada + bisseccao), validada contra tabela em tests/core/.
"""
import math
import statistics


def _betacf(a: float, b: float, x: float) -> float:
    """Fracao continuada da beta incompleta (Lentz)."""
    tiny = 1e-30
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, 200):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 3e-16:
            break
    return h


def _betai(a: float, b: float, x: float) -> float:
    """Beta incompleta regularizada I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    front = math.exp(lbeta + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def _t_cdf(t: float, df: float) -> float:
    """P(T <= t) para T ~ Student-t com df graus de liberdade."""
    tail = 0.5 * _betai(0.5 * df, 0.5, df / (df + t * t))
    return 1.0 - tail if t >= 0.0 else tail


def _t_ppf(p: float, df: float) -> float:
    """Inversa da CDF da t, por bisseccao."""
    lo, hi = -1000.0, 1000.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if _t_cdf(mid, df) < p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def welch_lower_bound(cand: list[float], champ: list[float],
                      alpha: float = 0.05) -> float:
    """Limite inferior do IC unilateral (1-alpha) de (media_cand - media_champ).

    Nao-pareado e invariante a ordem: consome os dois bracos como amostras
    independentes, nunca casando replica-i com replica-i.
    """
    nc, np_ = len(cand), len(champ)
    if nc < 2 or np_ < 2:
        raise ValueError("cada braco precisa de ao menos 2 replicas para estimar variancia")

    diff = statistics.fmean(cand) - statistics.fmean(champ)
    vc = statistics.variance(cand) / nc
    vp = statistics.variance(champ) / np_
    se = math.sqrt(vc + vp)
    if se == 0.0:
        return diff

    df = (vc + vp) ** 2 / (vc**2 / (nc - 1) + vp**2 / (np_ - 1))
    return diff - _t_ppf(1.0 - alpha, df) * se


def should_promote(cand: list[float], champ: list[float],
                   delta_min: float, alpha: float = 0.05) -> bool:
    """Promove sse o ganho e confiavelmente maior que delta_min."""
    return welch_lower_bound(cand, champ, alpha) > delta_min
