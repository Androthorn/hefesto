"""Evaluator component for ADRS.

Parses analyzer output from simulator runs, scores solutions against
an objective, and deploys refined prompts back to the simulator.
"""

import csv
import glob
import shutil
from pathlib import Path

from hefesto.schemas.evaluation import (
    EvaluationResult,
    MetricScore,
    ScoringResult,
    ScoringWeights,
)
from hefesto.schemas.input import MetricStats, Objective


# Metrics that the evaluator knows how to score.
SCORABLE_METRICS = [
    "pending_pods",
    "time_with_pending",
    "cost",
    "number_of_migrations",
]

# Fixed cost of the always-on private cluster (10 nodes × t4g.2xlarge,
# $0.2688/hr per node, 30-second intervals): (0.2688 * 10 * 30) / 3600
FIXED_COST = 0.0224

# Default baselines used when no baseline is provided.
# These represent "bad" values — a score of 0 means the metric equals the baseline.
DEFAULT_BASELINES: dict[str, float] = {
    "pending_pods": 100.0,
    "time_with_pending": 1.0,
    "cost": 0.1 - FIXED_COST,
    "number_of_migrations": 200.0,
}

# Cluster load threshold (fraction, not percentage)
CLUSTER_LOAD_THRESHOLD = 0.80


class Evaluator:
    """Evaluates simulation runs by collecting metrics and scoring them.

    The evaluator implements a target-based normalization scoring model:

        s_i = max(0, 1 - v_i / b_i)

    where v_i is the observed value (using the mean statistic) and b_i is
    a baseline (worst-acceptable) value. The composite score is a weighted
    average of individual metric scores, with a penalty applied when
    cluster CPU or memory load exceeds the 80% capacity threshold.
    """

    def __init__(
        self,
        weights: ScoringWeights | None = None,
        baselines: dict[str, float] | None = None,
    ) -> None:
        """Initialize the evaluator.

        Args:
            weights: Scoring weights configuration. Uses defaults if not provided.
            baselines: Baseline values for each metric. Uses defaults if not provided.
        """
        self.weights = weights or ScoringWeights()
        self.baselines = baselines or DEFAULT_BASELINES.copy()

    def collect_metrics(self, analyzer_output_dir: Path) -> dict[str, MetricStats]:
        """Parse the analyzer's summary CSV to extract metrics.

        The analyzer produces CSV files named `summary_metrics_*.csv` with rows
        for each metric and columns for mean, min, max, std, median.

        Args:
            analyzer_output_dir: Path to the analyzer output directory for a run.

        Returns:
            Dictionary mapping metric names to MetricStats objects.

        Raises:
            FileNotFoundError: If no summary CSV is found in the directory.
            ValueError: If the CSV cannot be parsed.
        """
        csv_files = sorted(glob.glob(
            str(analyzer_output_dir / "summary_metrics_*.csv")
        ))

        if not csv_files:
            raise FileNotFoundError(
                f"No summary_metrics_*.csv found in {analyzer_output_dir}"
            )

        # Use the most recent summary file
        csv_path = csv_files[-1]
        return self._parse_summary_csv(Path(csv_path))

    def _parse_summary_csv(self, csv_path: Path) -> dict[str, MetricStats]:
        """Parse a single summary CSV file into MetricStats objects.

        The CSV has the format:
            ,mean,min,max,std,median
            cost,0.061,0.044,0.071,0.009,0.064
            cpu_usage,1.23,0.87,1.78,0.23,1.34
            ...

        Args:
            csv_path: Path to the CSV file.

        Returns:
            Dictionary mapping metric names to MetricStats objects.
        """
        metrics: dict[str, MetricStats] = {}

        with open(csv_path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # The first column (unnamed or empty key) is the metric name
                metric_name = row.get("") or row.get("Unnamed: 0", "")
                if not metric_name:
                    # Try the first value in the row
                    first_key = next(iter(row))
                    metric_name = row[first_key]

                try:
                    metrics[metric_name] = MetricStats(
                        mean=float(row["mean"]),
                        min=float(row["min"]),
                        max=float(row["max"]),
                        std=float(row["std"]),
                        median=float(row["median"]),
                    )
                except (KeyError, ValueError) as e:
                    # Skip rows that don't have the expected format
                    continue

        if not metrics:
            raise ValueError(f"No valid metrics found in {csv_path}")

        return metrics

    def score(
        self,
        metrics: dict[str, MetricStats],
        objective: Objective | None = None,
        baselines: dict[str, float] | None = None,
    ) -> ScoringResult:
        """Score a set of metrics using the formal scoring model.

        Applies target-based normalization and weighted averaging.
        If cluster CPU or memory usage exceeds the 80% threshold,
        a penalty is applied to the composite score.

        Args:
            metrics: Raw metrics from the analyzer.
            objective: Optional objective for context (baselines may be
                       derived from success criteria in the future).
            baselines: Override baselines for this scoring call.

        Returns:
            ScoringResult with individual and composite scores.
        """
        effective_baselines = baselines or self.baselines
        weight_dict = self.weights.to_dict()
        weight_total = self.weights.total()

        metric_scores: list[MetricScore] = []

        for metric_name in SCORABLE_METRICS:
            if metric_name not in metrics:
                continue

            raw_value = metrics[metric_name].mean
            baseline = effective_baselines.get(metric_name, 1.0)
            weight = weight_dict.get(metric_name, 0.0)

            # Subtract fixed infrastructure cost before normalizing
            scoring_value = raw_value
            if metric_name == "cost":
                scoring_value = max(0.0, raw_value - FIXED_COST)

            # Target-based normalization: s = max(0, 1 - v / b)
            if baseline > 0:
                normalized = max(0.0, 1.0 - scoring_value / baseline)
            else:
                normalized = 0.0

            # Normalize weight relative to total
            effective_weight = weight / weight_total if weight_total > 0 else 0.0

            metric_scores.append(MetricScore(
                metric_name=metric_name,
                raw_value=raw_value,
                baseline_value=baseline,
                normalized_score=round(normalized, 4),
                weight=round(effective_weight, 4),
                weighted_score=round(normalized * effective_weight, 4),
            ))

        # Composite score
        composite = sum(ms.weighted_score for ms in metric_scores)

        # Check for cluster overload (CPU or memory > 80% capacity)
        overload_detected = False
        cpu_stats = metrics.get("cpu_usage")
        mem_stats = metrics.get("mem_usage")

        if cpu_stats and cpu_stats.mean > CLUSTER_LOAD_THRESHOLD:
            overload_detected = True
        if mem_stats and mem_stats.mean > CLUSTER_LOAD_THRESHOLD:
            overload_detected = True

        # Apply penalty (worsens score, but doesn't invalidate)
        penalty = self.weights.overload_penalty if overload_detected else 0.0
        composite = max(0.0, composite - penalty)

        return ScoringResult(
            metric_scores=metric_scores,
            composite_score=round(composite, 4),
            overload_detected=overload_detected,
            overload_penalty_applied=round(penalty, 4),
            weights_used=self.weights,
        )

    def deploy_prompt(
        self,
        prompt_text: str,
        simulator_path: Path,
        prompt_filename: str = "consolidator_agent.txt",
    ) -> Path:
        """Write a refined prompt to the simulator's prompts directory.

        Creates a backup of the existing prompt before overwriting.

        Args:
            prompt_text: The refined prompt text to deploy.
            simulator_path: Root path of the simulator project.
            prompt_filename: Name of the prompt file to write.

        Returns:
            Path to the written prompt file.
        """
        prompts_dir = simulator_path / "ai-engine" / "prompts"
        prompt_path = prompts_dir / prompt_filename

        # Backup existing prompt if it exists
        if prompt_path.exists():
            backup_path = prompts_dir / f"{prompt_filename}.backup"
            shutil.copy2(prompt_path, backup_path)

        # Write the new prompt
        prompt_path.write_text(prompt_text)
        return prompt_path

    def read_current_prompt(
        self,
        simulator_path: Path,
        prompt_filename: str = "consolidator_agent.txt",
    ) -> str:
        """Read the current prompt text from the simulator.

        Args:
            simulator_path: Root path of the simulator project.
            prompt_filename: Name of the prompt file to read.

        Returns:
            The current prompt text.

        Raises:
            FileNotFoundError: If the prompt file doesn't exist.
        """
        prompt_path = simulator_path / "ai-engine" / "prompts" / prompt_filename
        if not prompt_path.exists():
            raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
        return prompt_path.read_text()
