# The renderer formats the orchestration map as per given sample output format
from typing import List

from nion.models import ExecutionResult, Message, Task

SEPARATOR_WIDTH = 78
SEPARATOR = "=" * SEPARATOR_WIDTH


def _format_output_block(output_lines: List[str], indent: str) -> List[str]:
    rendered = []
    for line in output_lines:
        parts = line.split("\n")
        rendered.append(f"{indent}\u2022 {parts[0]}")
        for cont in parts[1:]:
            rendered.append(f"{indent}{cont}" if cont.strip() else "")
    return rendered


class OutputRenderer:
    def render(
        self,
        message: Message,
        tasks: List[Task],
        results: List[ExecutionResult],
    ) -> str:
        lines = []
        lines.append(SEPARATOR)
        lines.append("NION ORCHESTRATION MAP")
        lines.append(SEPARATOR)
        lines.append(f"Message: {message.message_id}")
        lines.append(f"From: {message.sender_name} ({message.sender_role})")
        lines.append(f"Project: {message.project if message.project is not None else 'N/A'}")
        lines.append("")

        lines.append(SEPARATOR)
        lines.append("L1 PLAN")
        lines.append(SEPARATOR)
        for task in tasks:
            if task.target_type == "L2":
                target_str = f"L2:{task.target}"
            else:
                target_str = f"L3:{task.target} (Cross-Cutting)"
            lines.append(f"[{task.id}] \u2192 {target_str}")
            lines.append(f"  Purpose: {task.purpose}")
            if task.depends_on:
                lines.append(f"  Depends On: {', '.join(task.depends_on)}")
            lines.append("")

        lines.append(SEPARATOR)
        lines.append("L2/L3 EXECUTION")
        lines.append(SEPARATOR)
        lines.append("")
        for result in results:
            if result.children:
                lines.append(f"[{result.task_id}] {result.label}")
                for child in result.children:
                    lines.append(f"  \u2514\u2500\u25b6 [{child.subtask_id}] L3:{child.agent}")
                    lines.append(f"      Status: {child.status}")
                    lines.append("      Output:")
                    lines.extend(_format_output_block(child.output_lines, "        "))
                lines.append("")
            else:
                lines.append(f"[{result.task_id}] {result.label}")
                lines.append(f"  Status: {result.status}")
                lines.append("  Output:")
                lines.extend(_format_output_block(result.output_lines, "    "))
                lines.append("")

        lines.append(SEPARATOR)
        lines.append("")
        return "\n".join(lines)
