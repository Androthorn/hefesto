"""WASPRunner — roda 1 réplica de sim WASP comprimida por chamada.

Escreve o prompt candidato em prompts/workshop/ (nunca toca p0/p4), aponta via
config, delega ao run_one_replica.sh e devolve o path do summary_metrics CSV.
"""
import hashlib
import json
import os
import subprocess
from pathlib import Path

from hefesto.schemas.core import TestCase, Output


class RunnerError(RuntimeError):
    pass


class WASPRunner:
    def __init__(self, simulatormeu_root, config_path, runs_dir,
                 reset_mode="full", runner_cmd=subprocess.run):
        self.root = Path(simulatormeu_root)
        self.config_path = Path(config_path)
        self.runs_dir = Path(runs_dir)
        self.reset_mode = reset_mode
        self.runner_cmd = runner_cmd
        self.workshop_dir = self.root / "ai-engine" / "prompts" / "workshop"
        self.replica_script = self.root / "run_one_replica.sh"

    def run(self, prompt: str, case: TestCase) -> Output:
        sha8 = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:8]
        self.workshop_dir.mkdir(parents=True, exist_ok=True)
        cand = self.workshop_dir / f"cand_{sha8}.txt"
        cand.write_text(prompt, encoding="utf-8")
        assert cand.read_text(encoding="utf-8"), "prompt candidato vazio — abortando (acidente de fevereiro)"

        replica = case.metadata.get("replica", 0)
        dest = self.runs_dir / f"{case.input or 'r'}_{sha8}_{replica}"
        dest.mkdir(parents=True, exist_ok=True)

        env = dict(os.environ)
        env["RESET_MODE"] = self.reset_mode
        prompt_name = f"workshop/cand_{sha8}"  # nome SEM .txt, relativo a prompts/
        self.runner_cmd(
            ["bash", str(self.replica_script), prompt_name, str(self.config_path), str(dest)],
            env=env,
        )

        csvs = sorted((dest / "analyzer" / "summary").glob("summary_metrics_*.csv"))
        if not csvs:
            raise RunnerError(f"réplica sem summary_metrics em {dest}")
        csv_path = csvs[-1]

        model = None
        prov = dest / "provenance.json"
        if prov.exists():
            model = json.loads(prov.read_text()).get("model")

        return Output(
            text=str(csv_path), model=model,
            metadata={"csv": str(csv_path), "run_dir": str(dest), "provenance": str(prov)},
        )
