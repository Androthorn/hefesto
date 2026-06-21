import re
from hefesto.llm.base import LLMProvider, LLMMessage
from hefesto.schemas.core import ScoredResult, Objective

REFINEMENT_SYSTEM_PROMPT = (
    "You improve prompts. Prefer adding a concrete few-shot example drawn from a "
    "real failing case over adding rules. Do NOT add nested legalistic rules "
    "(e.g. 1.a, 1.b); prefer conceptual guidance or examples. Keep edits concise. "
    "Return ONLY the full revised prompt text."
)

_NESTED_RULE = re.compile(r"\d+\.[a-z]")


def rule_density(text: str) -> int:
    return len(_NESTED_RULE.findall(text))


class Refiner:
    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider

    def propose(
        self,
        champion_prompt: str,
        selected_cases: list[ScoredResult],
        objective: Objective,
    ) -> str:
        examples = "\n".join(
            f"- input={r.case.input!r} output={r.output.text!r} score={r.composite:.2f}"
            for r in selected_cases
        )
        user = (
            f"Objective: {objective.goal}\n\n"
            f"Current prompt:\n{champion_prompt}\n\n"
            f"Best/worst cases:\n{examples}\n\n"
            "Propose an improved prompt."
        )
        resp = self.provider.complete([
            LLMMessage(role="system", content=REFINEMENT_SYSTEM_PROMPT),
            LLMMessage(role="user", content=user),
        ])
        return resp.content
