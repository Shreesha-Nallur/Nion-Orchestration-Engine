"""Abstract interface for the 'reasoning' layer: classification, planning,
and L3 output generation. Swappable so a future LLM-backed implementation
can drop in without touching the orchestration engine."""
from abc import ABC, abstractmethod
from typing import List

from nion.models import Message, MessageClassification, Task


class ReasoningProvider(ABC):
    @abstractmethod
    def classify(self, message: Message) -> MessageClassification:
        """Analyze the message and determine its type + relevant signals."""
        raise NotImplementedError

    @abstractmethod
    def plan(self, message: Message, classification: MessageClassification) -> List[Task]:
        """Build the L1 task plan (list of Tasks targeting L2 domains or
        cross-cutting L3 agents only)."""
        raise NotImplementedError

    @abstractmethod
    def generate_output(
        self,
        agent: str,
        message: Message,
        classification: MessageClassification,
        context: dict,
    ) -> List[str]:
        """Generate the dummy/templated output lines for a given L3 agent
        invocation, tailored using signals/keywords detected from the message."""
        raise NotImplementedError
