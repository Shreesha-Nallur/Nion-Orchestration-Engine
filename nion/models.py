"""Core data models for the Nion orchestration engine."""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Message:
    """Normalized representation of the input JSON message."""
    message_id: str
    source: str
    sender_name: str
    sender_role: str
    content: str
    project: Optional[str]

    @staticmethod
    def from_dict(data: dict) -> "Message":
        sender = data.get("sender") or {}
        return Message(
            message_id=data.get("message_id", "UNKNOWN"),
            source=data.get("source", "unknown"),
            sender_name=sender.get("name", "Unknown Sender"),
            sender_role=sender.get("role", "Unknown Role"),
            content=data.get("content", ""),
            project=data.get("project"),
        )


@dataclass
class MessageClassification:
    """Output of the classification step: detected signals + derived type."""
    message_type: str
    signals: dict = field(default_factory=dict)
    keywords: dict = field(default_factory=dict)  # extracted bits of text used to tailor output


@dataclass
class Task:
    """An L1-plan-level task. target_type is 'L2' or 'L3_CROSS_CUTTING'.

    Visibility rule enforced by construction: an L1 Task may only target
    an L2 domain or a registered cross-cutting L3 agent - never a
    domain-specific L3 agent directly.
    """
    id: str
    target_type: str  # "L2" or "L3_CROSS_CUTTING"
    target: str        # domain name or cross-cutting agent name
    purpose: str
    depends_on: List[str] = field(default_factory=list)


@dataclass
class SubTask:
    """An L3 agent invocation nested under an L2 domain task."""
    id: str
    agent: str
    parent_task_id: str


@dataclass
class ExecutionResult:
    """Result of executing a Task (L2-level) or a cross-cutting L3 directly."""
    task_id: str
    label: str                 # e.g. "L2:TRACKING_EXECUTION" or "L3:knowledge_retrieval (Cross-Cutting)"
    status: str = "COMPLETED"
    output_lines: List[str] = field(default_factory=list)
    children: List["SubTaskResult"] = field(default_factory=list)


@dataclass
class SubTaskResult:
    """Result of an L3 agent invocation nested under an L2 ExecutionResult."""
    subtask_id: str
    agent: str
    status: str = "COMPLETED"
    output_lines: List[str] = field(default_factory=list)
