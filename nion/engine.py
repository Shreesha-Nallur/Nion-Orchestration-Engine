"""ExecutionEngine: walks the L1 plan in order, and for each Task either:
  - dispatches to the appropriate L2Coordinator (which invokes its own L3
    agents), or
  - executes a cross-cutting L3 agent directly (since L1 has direct
    visibility into cross-cutting agents).

Accumulates a running `context` dict across tasks so later steps (e.g. qna)
can reference earlier results if needed (not heavily used by the current
rule-based templates, but the hook is there for the LLM-backed provider).
"""
from typing import List

from nion.coordinator import L2Coordinator
from nion.models import ExecutionResult, Message, MessageClassification, Task
from nion.registry import CROSS_CUTTING_AGENTS, L2_DOMAINS
from nion.reasoning.base import ReasoningProvider


class ExecutionEngine:
    def __init__(self, reasoning_provider: ReasoningProvider):
        self.reasoning_provider = reasoning_provider
        self.coordinators = {
            domain: L2Coordinator(domain, reasoning_provider) for domain in L2_DOMAINS
        }

    def execute_plan(
        self,
        tasks: List[Task],
        message: Message,
        classification: MessageClassification,
    ) -> List[ExecutionResult]:
        results: List[ExecutionResult] = []
        context: dict = {}

        for task in tasks:
            if task.target_type == "L2":
                coordinator = self.coordinators[task.target]
                subtask_results = coordinator.execute(task, message, classification, context)
                result = ExecutionResult(
                    task_id=task.id,
                    label=f"L2:{task.target}",
                    children=subtask_results,
                )
            elif task.target_type == "L3_CROSS_CUTTING":
                if task.target not in CROSS_CUTTING_AGENTS:
                    raise ValueError(f"Unknown cross-cutting agent: {task.target}")
                output_lines = self.reasoning_provider.generate_output(
                    task.target, message, classification, context
                )
                result = ExecutionResult(
                    task_id=task.id,
                    label=f"L3:{task.target} (Cross-Cutting)",
                    output_lines=output_lines,
                )
            else:
                raise ValueError(f"Unknown task target_type: {task.target_type}")

            results.append(result)
            context[task.id] = result

        return results
