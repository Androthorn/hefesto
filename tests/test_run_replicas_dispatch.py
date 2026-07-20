import importlib
import sys
from pathlib import Path

# Os runners foram versionados dentro de simulatormeu/ (antes viviam soltos na raiz
# de projetos/, que nao e repositorio e portanto nao dava proveniencia a eles).
ROOT = Path("/home/andre/projetos/simulatormeu")


def _mod():
    sys.path.insert(0, str(ROOT))
    return importlib.import_module("run_replicas")


def test_replica_one_full_rest_light():
    rr = _mod()
    modes = rr.dispatch_modes(k=4)
    assert modes == ["full", "light", "light", "light"]


def test_refuses_light_replicas_into_frozen_p0_batch(monkeypatch, capsys):
    rr = _mod()
    monkeypatch.setattr(rr, "_is_complete", lambda dest: False)  # força todas como "a rodar"
    monkeypatch.setattr("sys.argv", ["run_replicas.py", "-k", "3"])  # default --batch p0_batch
    rc = rr.main()
    assert rc != 0
    assert "p0_batch" in capsys.readouterr().err


def test_does_not_refuse_non_default_batch(monkeypatch, capsys):
    rr = _mod()
    monkeypatch.setattr(rr, "_is_complete", lambda dest: False)  # força todas como "a rodar"
    monkeypatch.setattr(
        "sys.argv", ["run_replicas.py", "-k", "3", "--batch", "p0_light_cert"]
    )
    rc = rr.main()
    assert rc == 0
    assert capsys.readouterr().err == ""
