"""Escalonamento dos bracos de um experimento controlado.

Duas propriedades, ambas fixadas por tests/core/test_schedule.py:

  intercalacao -- os bracos rodam alternados, nao em blocos. Deriva temporal
    do cluster atinge os tres igualmente em vez de virar diferenca entre eles.

  balanco de reset -- o modo depende do indice DENTRO do braco, nao da posicao
    global. Cada braco recebe a mesma mistura (1 full + k-1 light). Com o modo
    global antigo so o primeiro run do conjunto seria full, e um braco teria
    1 full contra 0 dos outros -- confound enquanto a certificacao
    `light == full` nao existir.
"""
from collections.abc import Sequence
from pathlib import Path

Entry = tuple[str, int, str]


def arm_run_dir(batch_dir: Path, arm: str, prompt_sha8: str, index: int) -> Path:
    """Destino de uma replica. O braco entra no CAMINHO, nao so o hash.

    p0 e p0' sao o mesmo prompt e portanto o mesmo sha8. Derivar o diretorio
    so do hash faria os dois bracos escreverem no mesmo lugar e destruiria o
    controle nulo em silencio.
    """
    return batch_dir / arm / f"r_{prompt_sha8}_{index}"


def arm_schedule(arms: Sequence[str], k: int) -> list[Entry]:
    """Ordem de execucao como [(braco, indice_no_braco, modo_de_reset), ...]."""
    if not arms:
        raise ValueError("e preciso ao menos um braco")
    if k < 1:
        raise ValueError(f"k precisa ser >= 1, recebido {k}")
    if len(set(arms)) != len(arms):
        raise ValueError(f"nomes de braco repetidos: {list(arms)}")

    return [(arm, i, "full" if i == 1 else "light")
            for i in range(1, k + 1)
            for arm in arms]
