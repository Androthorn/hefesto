"""Generator component for refining prompts using LLM."""

import json
import re
from typing import Any

from hefesto.core.analyzer import AnalysisResult
from hefesto.core.differ import Differ
from hefesto.llm.base import LLMProvider, LLMMessage
from hefesto.schemas.input import AgentPrompt, Objective, PromptTemplate
from hefesto.schemas.output import RefinementResult, PromptDiff


# System prompt for the refinement LLM
REFINEMENT_SYSTEM_PROMPT = """You are an expert prompt engineer specializing in optimizing LLM agent prompts for reliability and consistency.

Your task is to analyze experimental data and refine agent prompts to achieve better, more consistent results.

## Your Approach

1. **Understand the Objective**: Carefully read what the user wants to achieve
2. **Analyze the Data**: Look at metrics, variance, and identified issues
3. **Identify Root Causes**: Determine why the current prompt leads to inconsistent results
4. **Propose Targeted Changes**: Make specific, focused improvements to the prompt

## Guidelines for Prompt Refinement

- **Preserve Structure**: Keep the same template structure (system/user sections, variables)
- **PRESERVE OUTPUT FORMAT**: The agent's output format (JSON schema, field names, value types) is consumed by an automated system and MUST remain EXACTLY the same. Never rename fields, change value types, or alter the response structure. You may only refine the *instructions* and *reasoning guidance* within the prompt.
- **Avoid Over-Constraint**: Do NOT write massive walls of dense pseudo-code logical rules (e.g., "1.a. If Analyst decision is X AND explicit confirmation..."). Rigid legalese makes it harder for the agent to reason systemically.
- **PREFER FEW-SHOT EXAMPLES OVER RULES**: This is the PRIMARY refinement technique. If the agent is failing a specific type of scenario, encode that failure as a concrete example inside the prompt using this format:

  ```
  ## Examples

  ### Example: [brief scenario label]
  **Input context**: [describe the workload/cluster state that causes failure]
  **Correct reasoning**: [explain what the agent should conclude and why]
  **Expected output**: { "decisions": [0], "explanations": ["because ..."] }
  ```

  Identify the worst-scoring scenarios from the provided metric data and write at least one such example for each root cause you find. Do NOT just add a new rule to the `Decision Criteria` section — encode it as an example instead.
- **Keep it Concise**: Any additions to the prompt should be specific and minimal. Do not grow the prompt length unnecessarily.
- **Consistency Techniques**: Consider adding:
  - Step-by-step reasoning requirements
  - Concrete few-shot examples of edge case handling (preferred over abstract rules)

## Output Format

You MUST respond with valid JSON in exactly this format:

```json
{
  "refined_template": {
    "system": "...",
    "user": "...",
    "variables": ["var1", "var2"]
  },
  "refined_constraints": ["constraint1", "constraint2"],
  "reasoning": "Explanation of why these changes were made...",
  "suggestions": ["suggestion1", "suggestion2"]
}
```

Do not include any text outside the JSON block."""


class Generator:
    """
    Generates refined prompts using an LLM.
    
    Takes analysis results and current prompts, and produces improved versions
    aimed at achieving the specified objective.
    """

    def __init__(
        self,
        llm_provider: LLMProvider,
        temperature: float = 0.7,
        max_tokens: int = 8192,
    ):
        """
        Initialize the generator.
        
        Args:
            llm_provider: LLM provider to use for generation
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response
        """
        self.llm = llm_provider
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.differ = Differ()

    def refine(
        self,
        prompt: AgentPrompt,
        analysis: AnalysisResult,
        objective: Objective,
        past_evaluations_context: str | None = None,
    ) -> RefinementResult:
        """
        Refine a single agent prompt based on analysis and objective.
        
        Args:
            prompt: Current agent prompt to refine
            analysis: Analysis results from experiment runs
            objective: The optimization objective
            past_evaluations_context: Optional formatted text of past solutions
                and their evaluation scores for context-aware refinement
            
        Returns:
            RefinementResult with refined prompt and explanations
        """
        # Build the user prompt for the LLM
        user_content = self._build_refinement_request(
            prompt, analysis, objective, past_evaluations_context
        )
        
        # Call the LLM
        messages = [
            LLMMessage(role="system", content=REFINEMENT_SYSTEM_PROMPT),
            LLMMessage(role="user", content=user_content),
        ]
        
        response = self.llm.complete(
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        
        # Parse the response
        parsed = self._parse_response(response.content)
        
        # Generate version number
        new_version = self._increment_version(prompt.version)
        
        # Generate diff
        diff = self.differ.diff_prompts(prompt.template, parsed["refined_template"])
        
        return RefinementResult(
            agent_name=prompt.agent_name,
            original_version=prompt.version,
            refined_version=new_version,
            refined_template=parsed["refined_template"],
            refined_constraints=parsed.get("refined_constraints", prompt.constraints),
            diff=diff,
            reasoning=parsed.get("reasoning", "No reasoning provided"),
            suggestions=parsed.get("suggestions", []),
            analysis_summary=analysis.summary,
        )

    def _build_refinement_request(
        self,
        prompt: AgentPrompt,
        analysis: AnalysisResult,
        objective: Objective,
        past_evaluations_context: str | None = None,
    ) -> str:
        """Build the user prompt for the refinement request."""
        sections = [
            "# Prompt Refinement Request",
            "",
            "## Objective",
            f"**Goal:** {objective.goal}",
            "",
        ]
        
        if objective.success_criteria:
            sections.append("**Success Criteria:**")
            for criterion in objective.success_criteria:
                sections.append(f"- {criterion.to_string()}")
            sections.append("")
        
        if objective.focus_areas:
            sections.append(f"**Focus Areas:** {', '.join(objective.focus_areas)}")
            sections.append("")
        
        # Add analysis
        sections.append(analysis.to_prompt_context())
        
        # Add current prompt
        sections.extend([
            "## Current Prompt",
            "",
            f"**Agent:** {prompt.agent_name}",
            f"**Version:** {prompt.version}",
            "",
            "### System Prompt",
            "```",
            prompt.template.system,
            "```",
            "",
            "### User Prompt Template",
            "```",
            prompt.template.user,
            "```",
            "",
            f"**Variables:** {', '.join(prompt.template.variables) or 'None'}",
            "",
        ])
        
        if prompt.constraints:
            sections.append("### Constraints")
            for constraint in prompt.constraints:
                sections.append(f"- {constraint}")
            sections.append("")
        
        # Add past evaluations context if available
        if past_evaluations_context:
            sections.extend([
                "## Previous Solutions and Their Evaluations",
                "",
                "The following past solutions were tried. Learn from their "
                "scores and metrics to generate an improved prompt. Focus on "
                "what worked well (high scores) and what failed (low scores).",
                "",
                past_evaluations_context,
                "",
            ])
        
        sections.extend([
            "## Instructions",
            "",
            "Analyze the issues identified in the analysis and refine the prompt to:",
            "1. Address the key issues, especially high variance metrics",
            "2. Improve consistency across identical runs",
            "3. Maintain the original intent and capabilities",
            "4. **CRITICAL: Do NOT change the agent's output format** — the JSON response "
            "schema (field names, value types, array structure) is consumed by an automated "
            "system and must remain EXACTLY the same. You may only refine the instructions, "
            "reasoning guidance, decision criteria, and constraints within the prompt.",
            "5. **REQUIRED: Add at least one `## Examples` block** inside the refined prompt "
            "body. Identify the worst-performing scenario from the metric data (e.g., high "
            "pending_pods with low time_with_pending score, or a case where migrations spiked) "
            "and add a concrete:\n"
            "   - **Input context**: describe the workload/cluster state\n"
            "   - **Correct reasoning**: explain the right conclusion and why\n"
            "   - **Expected output**: the exact JSON output the agent should produce\n"
            "   Do NOT add a new abstract rule — encode the fix as an example instead.",
        ])
        
        if past_evaluations_context:
            sections.extend([
                "5. Learn from the previous solutions — improve on the best-scoring ones",
                "6. Avoid repeating approaches that led to low scores",
            ])
        
        sections.extend([
            "",
            "Respond with the refined prompt in the JSON format specified.",
        ])
        
        return "\n".join(sections)

    def _parse_response(self, response: str) -> dict[str, Any]:
        """Parse the LLM response into structured data."""
        json_str = self._extract_json_object(response)

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            # LLMs sometimes embed literal newlines/tabs inside JSON string
            # values (especially Gemini). Attempt to repair before failing.
            repaired = self._repair_json(json_str)
            try:
                data = json.loads(repaired)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON in LLM response: {e}")
        
        # Validate required fields
        if "refined_template" not in data:
            raise ValueError("LLM response missing 'refined_template' field")
        
        template_data = data["refined_template"]
        if not all(k in template_data for k in ["system", "user"]):
            raise ValueError("refined_template missing required fields (system, user)")
        
        # Convert to Pydantic model
        data["refined_template"] = PromptTemplate(
            system=template_data["system"],
            user=template_data["user"],
            variables=template_data.get("variables", []),
        )
        
        return data

    @staticmethod
    def _extract_json_object(text: str) -> str:
        """Extract a complete JSON object from text using balanced-brace matching.

        This is more robust than regex-based extraction because it correctly
        handles cases where the JSON string values contain markdown code
        blocks (triple backticks) that would confuse regex patterns.
        """
        start = text.find('{')
        if start == -1:
            raise ValueError("Could not find JSON object in LLM response")

        depth = 0
        in_string = False
        i = start
        while i < len(text):
            ch = text[i]

            # Skip escaped characters inside strings
            if in_string and ch == '\\':
                i += 2
                continue

            if ch == '"':
                in_string = not in_string
            elif not in_string:
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        return text[start:i + 1]
            i += 1

        raise ValueError("Unbalanced JSON object in LLM response (missing closing brace)")

    @staticmethod
    def _repair_json(json_str: str) -> str:
        """Repair malformed JSON from LLM responses.

        Escapes literal newlines, carriage returns, and tabs that appear
        inside JSON string values — a common issue with Gemini models.
        """
        result: list[str] = []
        in_string = False
        i = 0
        while i < len(json_str):
            ch = json_str[i]

            # Skip escaped characters inside strings
            if in_string and ch == '\\':
                result.append(ch)
                if i + 1 < len(json_str):
                    result.append(json_str[i + 1])
                    i += 2
                else:
                    i += 1
                continue

            if ch == '"':
                in_string = not in_string
                result.append(ch)
            elif in_string and ch == '\n':
                result.append('\\n')
            elif in_string and ch == '\r':
                result.append('\\r')
            elif in_string and ch == '\t':
                result.append('\\t')
            else:
                result.append(ch)
            i += 1

        return ''.join(result)

    def _increment_version(self, version: str) -> str:
        """Increment a version string (e.g., v1.0 -> v1.1)."""
        # Try to parse as v{major}.{minor}
        match = re.match(r"v?(\d+)\.(\d+)", version)
        if match:
            major, minor = int(match.group(1)), int(match.group(2))
            return f"v{major}.{minor + 1}"
        
        # Try to parse as v{number}
        match = re.match(r"v?(\d+)", version)
        if match:
            num = int(match.group(1))
            return f"v{num + 1}"
        
        # Fallback: append .1
        return f"{version}.1"
