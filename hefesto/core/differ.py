"""Differ component for generating prompt diffs."""

import difflib

from hefesto.schemas.input import PromptTemplate
from hefesto.schemas.output import DiffEntry, PromptDiff


class Differ:
    """
    Generates diffs between original and refined prompts.
    
    Produces both structured and human-readable diffs.
    """

    def diff_prompts(
        self,
        original: PromptTemplate,
        refined: PromptTemplate,
    ) -> PromptDiff:
        """
        Generate a diff between two prompt templates.
        
        Args:
            original: Original prompt template
            refined: Refined prompt template
            
        Returns:
            PromptDiff with changes for each section
        """
        return PromptDiff(
            system=self._diff_text(original.system, refined.system),
            user=self._diff_text(original.user, refined.user),
            constraints=[],  # Will be added if constraints change
        )

    def _diff_text(self, original: str, refined: str) -> list[DiffEntry]:
        """Generate diff entries for two text blocks."""
        if original == refined:
            return []
        
        entries = []
        
        # Use difflib for line-by-line comparison
        original_lines = original.splitlines(keepends=True)
        refined_lines = refined.splitlines(keepends=True)
        
        differ = difflib.unified_diff(
            original_lines,
            refined_lines,
            lineterm="",
        )
        
        # Parse diff output
        current_removals: list[str] = []
        current_additions: list[str] = []
        
        for line in differ:
            if line.startswith("---") or line.startswith("+++") or line.startswith("@@"):
                continue
            elif line.startswith("-"):
                current_removals.append(line[1:].rstrip("\n"))
            elif line.startswith("+"):
                current_additions.append(line[1:].rstrip("\n"))
            else:
                # Context line - flush accumulated changes
                entries.extend(
                    self._create_entries(current_removals, current_additions)
                )
                current_removals = []
                current_additions = []
        
        # Flush remaining changes
        entries.extend(self._create_entries(current_removals, current_additions))
        
        return entries

    def _create_entries(
        self,
        removals: list[str],
        additions: list[str],
    ) -> list[DiffEntry]:
        """Create diff entries from accumulated removals and additions."""
        entries = []
        
        # Match removals with additions where possible (modifications)
        min_len = min(len(removals), len(additions))
        
        for i in range(min_len):
            entries.append(DiffEntry(
                type="modify",
                original=removals[i],
                replacement=additions[i],
            ))
        
        # Remaining removals
        for i in range(min_len, len(removals)):
            entries.append(DiffEntry(
                type="remove",
                original=removals[i],
            ))
        
        # Remaining additions
        for i in range(min_len, len(additions)):
            entries.append(DiffEntry(
                type="add",
                replacement=additions[i],
            ))
        
        return entries

    def format_diff_text(self, diff: PromptDiff) -> str:
        """
        Format a PromptDiff as human-readable text.
        
        Args:
            diff: PromptDiff to format
            
        Returns:
            Human-readable diff string
        """
        lines = []
        
        if diff.system:
            lines.append("### System Prompt Changes")
            lines.extend(self._format_entries(diff.system))
            lines.append("")
        
        if diff.user:
            lines.append("### User Prompt Changes")
            lines.extend(self._format_entries(diff.user))
            lines.append("")
        
        if diff.constraints:
            lines.append("### Constraint Changes")
            lines.extend(self._format_entries(diff.constraints))
            lines.append("")
        
        if not any([diff.system, diff.user, diff.constraints]):
            lines.append("*No changes detected*")
        
        return "\n".join(lines)

    def _format_entries(self, entries: list[DiffEntry]) -> list[str]:
        """Format a list of diff entries as text lines."""
        lines = []
        
        for entry in entries:
            if entry.type == "add":
                lines.append(f"+ {entry.replacement}")
            elif entry.type == "remove":
                lines.append(f"- {entry.original}")
            elif entry.type == "modify":
                lines.append(f"- {entry.original}")
                lines.append(f"+ {entry.replacement}")
        
        return lines
