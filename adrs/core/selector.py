"""Solution Selector for ADRS.

Queries stored evaluation results and selects past solutions to feed
back into the Prompt Generator for context-aware refinement.
"""

from adrs.schemas.evaluation import EvaluationResult
from adrs.storage.repository import Repository


class SolutionSelector:
    """Selects past solutions from storage to inform the next refinement.

    Provides strategies for picking which past solutions (and their scores)
    should be included in the prompt context for the next LLM refinement call.
    """

    def __init__(self, repository: Repository) -> None:
        """Initialize the selector with a repository.

        Args:
            repository: Repository instance for querying stored evaluations.
        """
        self.repository = repository

    def select_top(
        self,
        agent_name: str = "consolidator_agent",
        n: int = 3,
    ) -> list[dict]:
        """Select the top N solutions by composite score.

        Args:
            agent_name: Agent name to filter by.
            n: Number of solutions to return.

        Returns:
            List of evaluation records (dicts) sorted by score descending.
        """
        return self.repository.get_top_evaluations(agent_name, limit=n)

    def select_recent(
        self,
        agent_name: str = "consolidator_agent",
        n: int = 3,
    ) -> list[dict]:
        """Select the N most recent solutions with their scores.

        Useful for showing the LLM the progression of recent refinements.

        Args:
            agent_name: Agent name to filter by.
            n: Number of solutions to return.

        Returns:
            List of evaluation records (dicts) sorted by timestamp descending.
        """
        return self.repository.get_recent_evaluations(agent_name, limit=n)

    def select_for_refinement(
        self,
        agent_name: str = "consolidator_agent",
        top_n: int = 2,
        recent_n: int = 1,
    ) -> list[dict]:
        """Select a mix of top-performing and recent solutions.

        This is the recommended strategy for refinement context:
        includes the best solutions found so far plus the most recent
        attempt, giving the LLM both targets to aim for and awareness
        of what was just tried.

        Args:
            agent_name: Agent name to filter by.
            top_n: Number of top-scoring solutions to include.
            recent_n: Number of most recent solutions to include.

        Returns:
            Deduplicated list of evaluation records.
        """
        top = self.select_top(agent_name, n=top_n)
        recent = self.select_recent(agent_name, n=recent_n)

        # Deduplicate by iteration number
        seen_iterations: set[int] = set()
        combined: list[dict] = []

        for record in top:
            iteration = record.get("iteration", -1)
            if iteration not in seen_iterations:
                seen_iterations.add(iteration)
                combined.append(record)

        for record in recent:
            iteration = record.get("iteration", -1)
            if iteration not in seen_iterations:
                seen_iterations.add(iteration)
                combined.append(record)

        return combined

    def format_for_prompt(self, evaluations: list[dict]) -> str:
        """Format selected evaluations as a text block for the LLM prompt.

        Args:
            evaluations: List of evaluation records from the selector.

        Returns:
            Formatted string suitable for inclusion in the refinement prompt.
        """
        if not evaluations:
            return "No previous evaluations available."

        lines = ["## Previous Solutions and Their Evaluations\n"]

        for eval_record in evaluations:
            iteration = eval_record.get("iteration", "?")
            score = eval_record.get("composite_score", "?")
            version = eval_record.get("prompt_version", "?")
            prompt_text = eval_record.get("prompt_text", "")
            metrics_summary = eval_record.get("metrics_summary", "")

            lines.append(f"### Iteration {iteration} (Score: {score}, Version: {version})")
            if metrics_summary:
                lines.append(f"Metrics: {metrics_summary}")
            if prompt_text:
                lines.append(f"Prompt used:\n```\n{prompt_text}\n```")
            lines.append("")

        return "\n".join(lines)
