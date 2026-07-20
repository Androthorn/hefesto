# tests/core/test_schedule.py
"""Escalonamento dos bracos do experimento controlado.

Duas propriedades sustentam o desenho e sao testadas aqui porque errar
qualquer uma destroi o experimento em silencio:

  intercalacao -- os bracos rodam alternados, nao em blocos, para que
    qualquer deriva temporal do cluster (memoria, disco, temperatura da
    maquina) atinja os tres igualmente em vez de virar diferenca entre eles.

  balanco de reset -- cada braco recebe a MESMA mistura full/light. Com o
    modo global antigo (replica 1 full, resto light), so o primeiro run do
    conjunto seria full e um braco teria 1 full contra 0 dos outros. Como a
    certificacao `light == full` nunca foi feita, isso seria confound.
"""
import pytest

from hefesto.core.schedule import arm_schedule

ARMS = ("p0", "p0_prime", "p1")


def test_arms_are_interleaved_not_blocked():
    order = [arm for arm, _, _ in arm_schedule(ARMS, k=3)]

    assert order == ["p0", "p0_prime", "p1",
                     "p0", "p0_prime", "p1",
                     "p0", "p0_prime", "p1"]


def test_each_arm_gets_exactly_k_replicas():
    schedule = arm_schedule(ARMS, k=12)

    for arm in ARMS:
        assert sum(1 for a, _, _ in schedule if a == arm) == 12
    assert len(schedule) == 36


def test_within_arm_index_counts_from_one():
    schedule = arm_schedule(ARMS, k=4)

    for arm in ARMS:
        indices = [i for a, i, _ in schedule if a == arm]
        assert indices == [1, 2, 3, 4]


def test_every_arm_gets_the_same_reset_mix():
    # A propriedade que importa: nenhum braco pode ter mistura diferente.
    schedule = arm_schedule(ARMS, k=12)

    mixes = {arm: sorted(m for a, _, m in schedule if a == arm) for arm in ARMS}
    assert len({tuple(mix) for mix in mixes.values()}) == 1, mixes
    assert mixes["p0"].count("full") == 1
    assert mixes["p0"].count("light") == 11


def test_the_full_reset_is_the_first_replica_of_each_arm():
    schedule = arm_schedule(ARMS, k=5)

    for arm, index, mode in schedule:
        assert mode == ("full" if index == 1 else "light"), (arm, index, mode)


def test_single_arm_degenerates_to_the_old_behaviour():
    # Compatibilidade: um braco so deve reproduzir "replica 1 full, resto light".
    schedule = arm_schedule(("p0",), k=3)

    assert schedule == [("p0", 1, "full"), ("p0", 2, "light"), ("p0", 3, "light")]


@pytest.mark.parametrize("arms,k", [((), 3), (("p0",), 0), (("p0", "p0"), 3)])
def test_rejects_degenerate_input(arms, k):
    with pytest.raises(ValueError):
        arm_schedule(arms, k)


def test_arm_run_dirs_do_not_collide_for_identical_prompts():
    # p0 e p0' sao o MESMO prompt -- mesmo sha8. Se o diretorio de destino
    # derivasse so do hash, os dois bracos escreveriam no mesmo lugar e o
    # controle nulo seria destruido em silencio.
    from pathlib import Path

    from hefesto.core.schedule import arm_run_dir

    base = Path("/tmp/batch")
    sha = "8840d32d"

    d0 = arm_run_dir(base, "p0", sha, 1)
    d0_prime = arm_run_dir(base, "p0_prime", sha, 1)

    assert d0 != d0_prime
    assert d0.name == d0_prime.name          # mesmo nome de replica
    assert d0.parent.name == "p0"            # separados pelo braco
    assert d0_prime.parent.name == "p0_prime"
