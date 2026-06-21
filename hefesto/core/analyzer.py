"""Analyzer component for examining metrics and logs from experiment runs."""

from dataclasses import dataclass, field

from hefesto.schemas.input import ExperimentRun, MetricStats, Objective


@dataclass
class MetricAnalysis:
    """Analysis of a single metric across runs."""

    name: str
    runs_analyzed: int
    overall_mean: float
    overall_std: float
    coefficient_of_variation: float  # std / mean - measures relative variability
    is_high_variance: bool
    trend: str  # "stable", "increasing", "decreasing", "erratic"
    
    # Per-run stats
    run_means: list[float] = field(default_factory=list)
    run_stds: list[float] = field(default_factory=list)


@dataclass
class LogAnalysis:
    """Analysis of logs across runs."""

    total_entries: int
    error_count: int
    warning_count: int
    common_patterns: list[str] = field(default_factory=list)
    anomalies: list[str] = field(default_factory=list)


@dataclass
class AnalysisResult:
    """Complete analysis result for a set of experiment runs."""

    agent_name: str
    runs_analyzed: int
    prompt_versions: list[str]
    
    # Metric analysis
    metric_analyses: dict[str, MetricAnalysis] = field(default_factory=dict)
    high_variance_metrics: list[str] = field(default_factory=list)
    priority_metric_issues: list[str] = field(default_factory=list)
    
    # Log analysis
    log_analysis: LogAnalysis | None = None
    
    # Summary
    summary: str = ""
    key_issues: list[str] = field(default_factory=list)
    
    def to_prompt_context(self) -> str:
        """Convert analysis to a string suitable for LLM context."""
        lines = [
            f"## Analysis Summary for {self.agent_name}",
            f"",
            f"**Runs analyzed:** {self.runs_analyzed}",
            f"**Prompt versions used:** {', '.join(self.prompt_versions)}",
            "",
        ]
        
        if self.key_issues:
            lines.append("### Key Issues Identified")
            for issue in self.key_issues:
                lines.append(f"- {issue}")
            lines.append("")
        
        if self.high_variance_metrics:
            lines.append("### High Variance Metrics")
            for metric_name in self.high_variance_metrics:
                analysis = self.metric_analyses.get(metric_name)
                if analysis:
                    lines.append(
                        f"- **{metric_name}**: CV={analysis.coefficient_of_variation:.3f}, "
                        f"mean={analysis.overall_mean:.4f}, std={analysis.overall_std:.4f}"
                    )
            lines.append("")
        
        if self.priority_metric_issues:
            lines.append("### Priority Metric Issues")
            for issue in self.priority_metric_issues:
                lines.append(f"- {issue}")
            lines.append("")
        
        if self.log_analysis:
            lines.append("### Log Analysis")
            lines.append(f"- Total entries: {self.log_analysis.total_entries}")
            lines.append(f"- Errors: {self.log_analysis.error_count}")
            lines.append(f"- Warnings: {self.log_analysis.warning_count}")
            if self.log_analysis.anomalies:
                lines.append("- Anomalies detected:")
                for anomaly in self.log_analysis.anomalies[:5]:  # Limit to 5
                    lines.append(f"  - {anomaly}")
            lines.append("")
        
        return "\n".join(lines)


class Analyzer:
    """
    Analyzes experiment runs to identify issues and patterns.
    
    The analyzer examines metrics and logs to find:
    - High variance metrics (inconsistent results)
    - Trends over time
    - Common error patterns in logs
    - Issues with priority metrics
    """

    def __init__(
        self,
        priority_metrics: list[str] | None = None,
        variance_threshold: float = 0.1,
    ):
        """
        Initialize the analyzer.
        
        Args:
            priority_metrics: Metrics to prioritize in analysis
            variance_threshold: Coefficient of variation threshold for flagging high variance
        """
        self.priority_metrics = priority_metrics or ["pending_pods", "number_of_migrations"]
        self.variance_threshold = variance_threshold

    def analyze(
        self,
        runs: list[ExperimentRun],
        objective: Objective | None = None,
    ) -> AnalysisResult:
        """
        Analyze a set of experiment runs.
        
        Args:
            runs: List of experiment runs to analyze
            objective: Optional objective to guide analysis priorities
            
        Returns:
            AnalysisResult with detailed findings
        """
        if not runs:
            raise ValueError("No runs provided for analysis")
        
        # Group runs by agent
        agent_name = runs[0].agent_name
        prompt_versions = list(set(run.prompt_version for run in runs))
        
        # Analyze metrics
        metric_analyses = self._analyze_metrics(runs)
        
        # Identify high variance metrics
        high_variance = [
            name for name, analysis in metric_analyses.items()
            if analysis.is_high_variance
        ]
        
        # Check priority metrics
        priority_issues = self._check_priority_metrics(metric_analyses, objective)
        
        # Analyze logs
        log_analysis = self._analyze_logs(runs)
        
        # Generate summary and key issues
        key_issues = self._identify_key_issues(
            metric_analyses, high_variance, priority_issues, log_analysis
        )
        summary = self._generate_summary(runs, high_variance, key_issues)
        
        return AnalysisResult(
            agent_name=agent_name,
            runs_analyzed=len(runs),
            prompt_versions=prompt_versions,
            metric_analyses=metric_analyses,
            high_variance_metrics=high_variance,
            priority_metric_issues=priority_issues,
            log_analysis=log_analysis,
            summary=summary,
            key_issues=key_issues,
        )

    def _analyze_metrics(
        self, runs: list[ExperimentRun]
    ) -> dict[str, MetricAnalysis]:
        """Analyze all metrics across runs."""
        # Collect all metric names
        all_metrics: set[str] = set()
        for run in runs:
            all_metrics.update(run.metrics.keys())
        
        analyses = {}
        for metric_name in all_metrics:
            analyses[metric_name] = self._analyze_single_metric(runs, metric_name)
        
        return analyses

    def _analyze_single_metric(
        self, runs: list[ExperimentRun], metric_name: str
    ) -> MetricAnalysis:
        """Analyze a single metric across all runs."""
        run_means = []
        run_stds = []
        
        for run in runs:
            if metric_name in run.metrics:
                stats = run.metrics[metric_name]
                run_means.append(stats.mean)
                run_stds.append(stats.std)
        
        if not run_means:
            return MetricAnalysis(
                name=metric_name,
                runs_analyzed=0,
                overall_mean=0,
                overall_std=0,
                coefficient_of_variation=0,
                is_high_variance=False,
                trend="unknown",
            )
        
        # Calculate overall statistics
        overall_mean = sum(run_means) / len(run_means)
        
        # Variance of the means (how much the mean varies between runs)
        if len(run_means) > 1:
            variance = sum((m - overall_mean) ** 2 for m in run_means) / (len(run_means) - 1)
            overall_std = variance ** 0.5
        else:
            overall_std = 0
        
        # Coefficient of variation
        cv = overall_std / overall_mean if overall_mean != 0 else 0
        
        # Determine trend
        trend = self._determine_trend(run_means)
        
        return MetricAnalysis(
            name=metric_name,
            runs_analyzed=len(run_means),
            overall_mean=overall_mean,
            overall_std=overall_std,
            coefficient_of_variation=abs(cv),
            is_high_variance=abs(cv) > self.variance_threshold,
            trend=trend,
            run_means=run_means,
            run_stds=run_stds,
        )

    def _determine_trend(self, values: list[float]) -> str:
        """Determine the trend of a series of values."""
        if len(values) < 2:
            return "insufficient_data"
        
        # Simple trend detection using linear regression slope
        n = len(values)
        x_mean = (n - 1) / 2
        y_mean = sum(values) / n
        
        numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        
        if denominator == 0:
            return "stable"
        
        slope = numerator / denominator
        relative_slope = slope / y_mean if y_mean != 0 else slope
        
        if abs(relative_slope) < 0.05:
            return "stable"
        elif relative_slope > 0.1:
            return "increasing"
        elif relative_slope < -0.1:
            return "decreasing"
        else:
            return "slight_" + ("increase" if relative_slope > 0 else "decrease")

    def _check_priority_metrics(
        self,
        metric_analyses: dict[str, MetricAnalysis],
        objective: Objective | None,
    ) -> list[str]:
        """Check priority metrics for issues."""
        issues = []
        
        # Use objective's priority metrics if provided, else use default
        priority = (
            objective.priority_metrics
            if objective and objective.priority_metrics
            else self.priority_metrics
        )
        
        for metric_name in priority:
            if metric_name not in metric_analyses:
                issues.append(f"Priority metric '{metric_name}' not found in data")
                continue
            
            analysis = metric_analyses[metric_name]
            
            if analysis.is_high_variance:
                issues.append(
                    f"Priority metric '{metric_name}' has high variance "
                    f"(CV={analysis.coefficient_of_variation:.3f})"
                )
            
            if analysis.trend in ("increasing", "decreasing"):
                issues.append(
                    f"Priority metric '{metric_name}' shows {analysis.trend} trend"
                )
        
        # Check success criteria if objective provided
        if objective:
            for criterion in objective.success_criteria:
                if criterion.metric in metric_analyses:
                    analysis = metric_analyses[criterion.metric]
                    # Simplified check - would need more logic for full comparison
                    if analysis.is_high_variance:
                        issues.append(
                            f"Success criterion '{criterion.to_string()}' at risk "
                            f"due to high variance"
                        )
        
        return issues

    def _analyze_logs(self, runs: list[ExperimentRun]) -> LogAnalysis:
        """Analyze logs across all runs."""
        total_entries = 0
        error_count = 0
        warning_count = 0
        messages: list[str] = []
        
        for run in runs:
            for log in run.logs:
                total_entries += 1
                messages.append(log.message)
                
                level = log.level.upper()
                if level == "ERROR":
                    error_count += 1
                elif level in ("WARN", "WARNING"):
                    warning_count += 1
        
        # Find common patterns (simple frequency analysis)
        common_patterns = self._find_common_patterns(messages)
        
        # Identify anomalies
        anomalies = []
        if error_count > 0:
            anomalies.append(f"Found {error_count} error(s) in logs")
        if warning_count > total_entries * 0.1:  # More than 10% warnings
            anomalies.append(f"High warning rate: {warning_count}/{total_entries}")
        
        return LogAnalysis(
            total_entries=total_entries,
            error_count=error_count,
            warning_count=warning_count,
            common_patterns=common_patterns,
            anomalies=anomalies,
        )

    def _find_common_patterns(self, messages: list[str], min_count: int = 2) -> list[str]:
        """Find common patterns in log messages."""
        # Simple word-based pattern matching
        word_counts: dict[str, int] = {}
        for msg in messages:
            words = msg.lower().split()
            for word in words:
                if len(word) > 3:  # Ignore short words
                    word_counts[word] = word_counts.get(word, 0) + 1
        
        # Return most common words as "patterns"
        sorted_words = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)
        return [word for word, count in sorted_words[:10] if count >= min_count]

    def _identify_key_issues(
        self,
        metric_analyses: dict[str, MetricAnalysis],
        high_variance: list[str],
        priority_issues: list[str],
        log_analysis: LogAnalysis,
    ) -> list[str]:
        """Identify the key issues to address."""
        issues = []
        
        # High variance is a key issue
        if high_variance:
            issues.append(
                f"High variance detected in {len(high_variance)} metric(s): "
                f"{', '.join(high_variance[:3])}"
            )
        
        # Priority metric issues
        issues.extend(priority_issues)
        
        # Log issues
        if log_analysis.error_count > 0:
            issues.append(f"Errors detected in logs ({log_analysis.error_count} total)")
        
        return issues

    def _generate_summary(
        self,
        runs: list[ExperimentRun],
        high_variance: list[str],
        key_issues: list[str],
    ) -> str:
        """Generate a human-readable summary."""
        summary_parts = [
            f"Analyzed {len(runs)} experiment run(s).",
        ]
        
        if high_variance:
            summary_parts.append(
                f"Found high variance in {len(high_variance)} metric(s), "
                "indicating inconsistent results across runs."
            )
        else:
            summary_parts.append("Metric variance is within acceptable limits.")
        
        if key_issues:
            summary_parts.append(f"Identified {len(key_issues)} key issue(s) to address.")
        else:
            summary_parts.append("No critical issues identified.")
        
        return " ".join(summary_parts)
