"""StabilityGrader — pontua uma réplica WASP com o S auditado. Zero fórmula aqui."""
import csv
from hefesto.schemas.core import TestCase, Output, Objective, Metrics
from hefesto.scoring.ucc_scoring import stability_score, METRICS


def _means_from_csv(csv_path: str) -> dict:
    means: dict[str, float] = {}
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        name_col = reader.fieldnames[0]  # coluna-índice sem cabeçalho
        for row in reader:
            means[row[name_col]] = row["mean"]
    out = {}
    for m in METRICS:
        if m not in means:
            raise KeyError(f"métrica ausente no CSV: {m}")
        out[m] = float(means[m])
    return out


class StabilityGrader:
    def grade(self, case: TestCase, output: Output, objective: Objective) -> Metrics:
        csv_path = output.metadata["csv"]
        S = stability_score(_means_from_csv(csv_path))
        return Metrics(scores={"stability": S})
