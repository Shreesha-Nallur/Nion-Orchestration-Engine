# Core data models for the orchestration engine.
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Message:
    # Normalised representation of the JSON input message
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
    # Classification step gives the detected signlas and derived type
    message_type: str
    signals: dict = field(default_factory=dict)
    keywords: dict = field(default_factory=dict)  # words used to tailor the output


@dataclass
class Task:
    # L1 plan level task
    id: str
    target_type: str  # "L2" or "L3_CROSS_CUTTING"
    target: str        # domain name or cross-cutting agent name
    purpose: str
    depends_on: List[str] = field(default_factory=list)


@dataclass
class SubTask:
    # L3 agent nested inside an L2 domain
    id: str
    agent: str
    parent_task_id: str


@dataclass
class ExecutionResult:
    # Result of executing a task at L2 or cross cutting L3
    task_id: str
    label: str                 # e.g. "L2:TRACKING_EXECUTION" or "L3:knowledge_retrieval (Cross-Cutting)"
    status: str = "COMPLETED"
    output_lines: List[str] = field(default_factory=list)
    children: List["SubTaskResult"] = field(default_factory=list)


@dataclass
class SubTaskResult:
    # Result of L3 invocation nested in L2 domain
    subtask_id: str
    agent: str
    status: str = "COMPLETED"
    output_lines: List[str] = field(default_factory=list)
