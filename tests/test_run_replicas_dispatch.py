import importlib
import sys
from pathlib import Path

ROOT = Path("/home/andre/projetos")


def test_replica_one_full_rest_light(monkeypatch, tmp_path):
    sys.path.insert(0, str(ROOT))
    rr = importlib.import_module("run_replicas")

    calls = []

    class FakeRunner:
        def __init__(self, *a, **k):
            pass

        def run(self, prompt, case):
            calls.append((case.metadata["replica"], case.metadata["reset_mode"]))
            raise rr.__dict__.get("_StopForTest", KeyboardInterrupt)()

    # Force every replica to be "todo" and stub the heavy bits.
    monkeypatch.setattr(rr, "_is_complete", lambda dest: False)
    monkeypatch.setattr(rr, "preflight", lambda: [])
    monkeypatch.setattr(rr, "WASPRunner", FakeRunner, raising=False)
    # Point the batch at a temp dir so nothing real is touched.
    monkeypatch.setattr(rr, "RUNS", tmp_path, raising=False)

    modes = rr.dispatch_modes(k=4)
    assert modes == ["full", "light", "light", "light"]
