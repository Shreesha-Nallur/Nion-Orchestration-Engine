"""L2Coordinator: receives a Task targeting its domain, decides which of its
own L3 agents (or cross-cutting agents) to invoke to fulfil it, executes them,
and aggregates results into a SubTaskResult list.

Visibility rule enforced here: an L2Coordinator can only invoke L3 agents
registered under its own domain, or cross-cutting agents - never another
domain's L3 agents.
"""
from typing import List

from nion.models import Message, MessageClassification, SubTaskResult, Task
from nion.registry import L3_AGENTS_BY_DOMAIN, is_valid_l2_subagent
from nion.reasoning.base import ReasoningProvider

# For each (domain, message_type) we define which of the domain's L3 agents
# are relevant. This keeps agent-selection logic declarative and easy to
# extend, while still being driven by the message classification.
_DOMAIN_AGENT_SELECTION = {
    "TRACKING_EXECUTION": {
        "FEATURE_REQUEST": {
            "Extract action items": "action_item_extraction",
            "Extract risks": "risk_extraction",
            "Extract decision": "decision_extraction",
        },
        "DECISION_REQUEST": {
            "Extract decision": "decision_extraction",
        },
        "MEETING_TRANSCRIPT": {
            "Extract action items": "action_item_extraction",
            "Extract issues": "issue_extraction",
        },
        "ESCALATION": {
            "Extract issue": "issue_extraction",
        },
    },
    "COMMUNICATION_COLLABORATION": {
        "FEATURE_REQUEST": {"Formulate response": "qna", "Send response": "message_delivery"},
        "STATUS_QUERY": {"Formulate response": "qna", "Send response": "message_delivery"},
        "DECISION_REQUEST": {"Formulate response": "qna", "Send response": "message_delivery"},
        "ESCALATION": {"Formulate response": "qna", "Send response": "message_delivery"},
        "AMBIGUOUS": {"Formulate response": "qna", "Send response": "message_delivery"},
        "MEETING_TRANSCRIPT": {
            "Capture transcript": "meeting_attendance",
            "Generate report": "report_generation",
        },
    },
}

# Purpose-keyword -> agent selection: we match on substrings in Task.purpose
# to decide, for a COMMUNICATION_COLLABORATION task, whether it's a
# "formulate" step (-> qna) or a "send" step (-> message_delivery), since
# both share the same L2 domain but appear as separate Tasks in the plan.
_PURPOSE_AGENT_HINTS = [
    ("capture meeting transcript", "meeting_attendance"),
    ("generate meeting summary report", "report_generation"),
    ("send", "message_delivery"),
    ("formulate", "qna"),
    ("extract action items", "action_item_extraction"),
    ("extract risks", "risk_extraction"),
    ("extract decision", "decision_extraction"),
    ("extract issues", "issue_extraction"),
    ("extract escalated issue", "issue_extraction"),
]


def _select_agents_for_task(domain: str, task: Task) -> List[str]:
    """Decide which L3 agent(s) under `domain` fulfil this Task, using the
    Task's purpose text as the signal (since one domain can serve many
    distinct purposes depending on message type)."""
    purpose_lower = task.purpose.lower()
    matched = []
    for hint, agent in _PURPOSE_AGENT_HINTS:
        if hint in purpose_lower and agent in L3_AGENTS_BY_DOMAIN.get(domain, {}):
            matched.append(agent)
    if matched:
        return matched

    # Fallback: if purpose mentions multiple extraction types in one task
    # (rare with current templates, but defensive), match each by keyword.
    fallback_map = {
        "action item": "action_item_extraction",
        "risk": "risk_extraction",
        "decision": "decision_extraction",
        "issue": "issue_extraction",
    }
    for kw, agent in fallback_map.items():
        if kw in purpose_lower and agent in L3_AGENTS_BY_DOMAIN.get(domain, {}):
            matched.append(agent)
    return matched or []


class L2Coordinator:
    def __init__(self, domain: str, reasoning_provider: ReasoningProvider):
        self.domain = domain
        self.reasoning_provider = reasoning_provider

    def execute(
        self,
        task: Task,
        message: Message,
        classification: MessageClassification,
        context: dict,
    ) -> List[SubTaskResult]:
        agents = _select_agents_for_task(self.domain, task)
        results = []
        for i, agent in enumerate(agents, start=1):
            if not is_valid_l2_subagent(self.domain, agent):
                raise ValueError(
                    f"Visibility rule violation: L2:{self.domain} cannot invoke "
                    f"agent '{agent}' (not in its domain or cross-cutting)"
                )
            output_lines = self.reasoning_provider.generate_output(agent, message, classification, context)
            subtask_id = f"{task.id}-{chr(64 + i)}"  # TASK-001-A, -B, ...
            results.append(SubTaskResult(subtask_id=subtask_id, agent=agent, output_lines=output_lines))
        return results
