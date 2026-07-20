# tests/core/test_promotion_gate.py
"""Gate de promocao nao-pareado com margem (opcao B do ESTADO §4e).

Promove sse o limite inferior do IC unilateral de (media_cand - media_champ)
supera delta_min. Cobre as duas falhas registradas no §4e:
  Falha 1 - pareamento por zip (resultado dependia da ordem das replicas).
  Falha 2 - criterio ignorava o n (rodar mais replicas nao comprava confianca).
"""
import random

import pytest

from hefesto.core.gate import welch_lower_bound, should_promote
from hefesto.core.loop import RefineLoop
from hefesto.dataset.base import DatasetSplit
from hefesto.runner.echo_runner import EchoRunner
from hefesto.schemas.config import LoopConfig
from hefesto.schemas.core import Metrics, Objective, TestCase


def test_identical_arms_are_not_promoted():
    # Mesmo prompt nos dois bracos: a diferenca real e zero.
    champ = [0.75, 0.76, 0.74, 0.75, 0.77, 0.73]
    cand = [0.74, 0.77, 0.75, 0.76, 0.74, 0.76]

    assert not should_promote(cand, champ, delta_min=0.10, alpha=0.05)


def test_clear_gain_above_margin_is_promoted():
    champ = [0.50, 0.51, 0.49, 0.50, 0.52, 0.48]
    cand = [0.80, 0.81, 0.79, 0.80, 0.82, 0.78]  # +0.30, muito acima de 0.10

    assert should_promote(cand, champ, delta_min=0.10, alpha=0.05)


def test_gain_below_margin_is_not_promoted():
    # Ganho de +0.04 real e consistente: significativo, mas abaixo da margem.
    # E o caso que separa a opcao B (margem) da opcao A (significancia pura).
    champ = [0.700, 0.701, 0.699, 0.700, 0.702, 0.698]
    cand = [0.740, 0.741, 0.739, 0.740, 0.742, 0.738]

    assert not should_promote(cand, champ, delta_min=0.10, alpha=0.05)


def test_lower_bound_tightens_with_more_replicas():
    # Falha 2: com a regra antiga (epsilon * sigma) o criterio nao mudava com n.
    # Com erro-padrao, mais replicas apertam o limite inferior.
    champ_unit = [0.70, 0.72, 0.68, 0.71, 0.69]
    cand_unit = [0.85, 0.87, 0.83, 0.86, 0.84]

    lb_small = welch_lower_bound(cand_unit, champ_unit, alpha=0.05)
    lb_large = welch_lower_bound(cand_unit * 4, champ_unit * 4, alpha=0.05)

    assert lb_large > lb_small


def test_result_is_invariant_to_replica_order():
    # Falha 1: o pareamento por zip mudava o resultado ao embaralhar as replicas.
    champ = [0.70, 0.62, 0.81, 0.75, 0.68, 0.77]
    cand = [0.88, 0.79, 0.72, 0.91, 0.85, 0.80]

    baseline = welch_lower_bound(cand, champ, alpha=0.05)

    rng = random.Random(0)
    for _ in range(20):
        shuffled_cand = rng.sample(cand, len(cand))
        shuffled_champ = rng.sample(champ, len(champ))
        assert welch_lower_bound(shuffled_cand, shuffled_champ, alpha=0.05) == baseline


# --- nivel-loop: o gate ligado no RefineLoop -------------------------------

class NoisyGrader:
    """Score por (marcador do prompt, caso) -- replicas do mesmo prompt diferem."""

    def __init__(self, table):
        self.table = table

    def grade(self, case, output, objective):
        for marker, per_case in self.table.items():
            if marker in output.text:
                return Metrics(scores={"q": per_case[case.input]})
        raise AssertionError(f"prompt sem marcador conhecido: {output.text!r}")


class ScriptedRefiner:
    def __init__(self, candidates):
        self._candidates = iter(candidates)

    def propose(self, champion_prompt, selected_cases, objective):
        return next(self._candidates)


def _noisy_split():
    cases = [TestCase(input=str(i)) for i in range(1, 9)]
    return DatasetSplit(dev=cases[:2], test=cases[2:])


def _run_loop(table, candidate, seed, delta_min):
    cfg = LoopConfig(max_iter=1, patience=5, target=None, headroom_min=0.0,
                     delta_min=delta_min, alpha=0.05)
    loop = RefineLoop(
        runner=EchoRunner(), grader=NoisyGrader(table), refiner=ScriptedRefiner([candidate]),
        objective=Objective(goal="g"), weights={"q": 1.0}, config=cfg,
    )
    return loop.run(seed, _noisy_split())


# Campeao e candidato sorteiam da mesma distribuicao; o candidato sai +0.02 a
# frente por acaso. E o falso positivo que o paper documenta.
NULL_TABLE = {
    "CHAMP": {"1": 0.74, "2": 0.75, "3": 0.70, "4": 0.76,
              "5": 0.72, "6": 0.78, "7": 0.74, "8": 0.75},
    "NULL": {"1": 0.75, "2": 0.74, "3": 0.73, "4": 0.79,
             "5": 0.71, "6": 0.80, "7": 0.72, "8": 0.78},
}


def test_loop_does_not_promote_a_null_candidate():
    result = _run_loop(NULL_TABLE, "NULL {{input}}", "CHAMP {{input}}", delta_min=0.10)

    assert result.champion == "CHAMP {{input}}"
    assert result.history[-1]["promoted"] is False


def test_loop_promotes_a_gain_clearly_above_the_margin():
    table = dict(NULL_TABLE)
    table["REAL"] = {k: v + 0.20 for k, v in NULL_TABLE["CHAMP"].items()}

    result = _run_loop(table, "REAL {{input}}", "CHAMP {{input}}", delta_min=0.10)

    assert result.champion == "REAL {{input}}"
    assert result.history[-1]["promoted"] is True


def test_loop_rejects_a_real_but_sub_margin_gain():
    # +0.05 consistente: significativo, mas abaixo de delta_min=0.10.
    table = dict(NULL_TABLE)
    table["SMALL"] = {k: v + 0.05 for k, v in NULL_TABLE["CHAMP"].items()}

    result = _run_loop(table, "SMALL {{input}}", "CHAMP {{input}}", delta_min=0.10)

    assert result.champion == "CHAMP {{input}}"
    assert result.history[-1]["promoted"] is False


def test_single_replica_arm_is_rejected_not_silently_promoted():
    # n=1 nao estima variancia. Avaliar com 1 run e a causa raiz do paper --
    # o loop tem que falhar alto, nunca promover.
    cfg = LoopConfig(max_iter=1, patience=5, target=None, headroom_min=0.0,
                     delta_min=0.10, alpha=0.05)
    cases = [TestCase(input="1"), TestCase(input="2")]
    split = DatasetSplit(dev=cases[:1], test=cases[1:])  # test tem 1 caso
    loop = RefineLoop(
        runner=EchoRunner(), grader=NoisyGrader(NULL_TABLE),
        refiner=ScriptedRefiner(["NULL {{input}}"]),
        objective=Objective(goal="g"), weights={"q": 1.0}, config=cfg,
    )

    with pytest.raises(ValueError, match="ao menos 2 replicas"):
        loop.run("CHAMP {{input}}", split)
