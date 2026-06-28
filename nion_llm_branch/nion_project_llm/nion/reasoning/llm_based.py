"""LLM-backed implementation of the ReasoningProvider interface.

This is a drop-in replacement for RuleBasedReasoningProvider: it implements
the same classify() / plan() / generate_output() contract, so engine.py and
coordinator.py require zero changes to use it.

Design choices (see README for the full rationale):
  - classify():        delegated to the Anthropic API (Claude). Falls back
                        to the rule-based classifier on any API error or
                        unparseable response.
  - plan():             NOT delegated to the LLM. Reuses the existing
                        rule-based plan templates directly, because the L1
                        plan is also where the visibility rule is
                        structurally enforced - keeping it deterministic
                        avoids having to validate/retry arbitrary LLM task
                        proposals against the registry on every call.
  - generate_output():  delegated to the Anthropic API for richer, less
                        templated agent output. Falls back to the
                        rule-based generator on any API error or empty
                        response.

Requires:
  - `pip install anthropic`
  - an ANTHROPIC_API_KEY environment variable set
"""
import json
import os
from typing import List, Optional

from nion.models import Message, MessageClassification, Task
from nion.reasoning.base import ReasoningProvider
from nion.reasoning.rule_based import (
    AMBIGUOUS,
    DECISION_REQUEST,
    ESCALATION,
    FEATURE_REQUEST,
    MEETING_TRANSCRIPT,
    STATUS_QUERY,
    RuleBasedReasoningProvider,
)

VALID_MESSAGE_TYPES = {
    STATUS_QUERY,
    FEATURE_REQUEST,
    DECISION_REQUEST,
    MEETING_TRANSCRIPT,
    ESCALATION,
    AMBIGUOUS,
}

DEFAULT_MODEL = "claude-sonnet-4-6"

CLASSIFY_SYSTEM_PROMPT = f"""You are the classification component of Nion, an AI Program Manager.
Given a message (from email/Slack/a meeting transcript), classify it into exactly one of these types:

- STATUS_QUERY: asking for the current status/progress of something, no new scope.
- FEATURE_REQUEST: asking to add new scope/features, possibly with a question about feasibility.
- DECISION_REQUEST: asking which of several options to prioritize, or asking for a recommendation/decision.
- MEETING_TRANSCRIPT: a meeting transcript with multiple speakers, status updates, blockers.
- ESCALATION: urgent, frustrated, or threatening tone (e.g. legal escalation, missed deadline complaints).
- AMBIGUOUS: too vague/short to determine intent, or missing critical context (e.g. no project specified).

Respond with ONLY a JSON object, no other text, no markdown fences, in this exact shape:
{{
  "message_type": "<one of the six types above>",
  "is_question": <true/false>,
  "has_escalation": <true/false>,
  "is_meeting_transcript": <true/false>,
  "features": ["<short phrase describing each new feature/scope item mentioned, if any>"],
  "reasoning": "<one sentence explaining the classification>"
}}
"""

GENERATE_OUTPUT_SYSTEM_PROMPT = """You are an L3 execution agent inside Nion, an AI Program Manager
orchestration engine. You will be told which specific agent you are simulating, given the original
message and its classification, and asked to produce realistic but clearly-synthetic output for that
agent's function.

Respond with ONLY a JSON object, no other text, no markdown fences, in this exact shape:
{
  "output_lines": ["<line 1>", "<line 2>", "..."]
}

Each output line should be a short, concrete bullet of synthetic agent output (e.g. an extracted
action item with an owner/due-date placeholder, a risk with likelihood/impact, a drafted response).
Keep total output under 12 lines. Do not include any text outside the JSON object.
"""


def _get_client():
    """Lazily import + construct the Anthropic client so this module can be
    imported even when the `anthropic` package isn't installed (e.g. on the
    rule-based-only branch/environment)."""
    try:
        import anthropic
    except ImportError as e:
        raise RuntimeError(
            "The 'anthropic' package is required for LLMReasoningProvider. "
            "Install it with: pip install anthropic"
        ) from e

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY environment variable is not set. "
            "Set it before using LLMReasoningProvider, e.g.:\n"
            "  export ANTHROPIC_API_KEY=sk-ant-...   (macOS/Linux)\n"
            "  $env:ANTHROPIC_API_KEY='sk-ant-...'    (Windows PowerShell)"
        )
    return anthropic.Anthropic(api_key=api_key)


def _extract_json(text: str) -> Optional[dict]:
    """Best-effort JSON extraction: handles the happy path (pure JSON) and
    the common failure mode of the model wrapping it in markdown fences."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


class LLMReasoningProvider(ReasoningProvider):
    def __init__(self, model: str = DEFAULT_MODEL, max_tokens: int = 1000, verbose: bool = False):
        self.model = model
        self.max_tokens = max_tokens
        self.verbose = verbose
        # Rule-based provider is used both as the planner and as the
        # fallback path for classify()/generate_output().
        self._fallback = RuleBasedReasoningProvider()

    def _log(self, msg: str):
        if self.verbose:
            print(f"[LLMReasoningProvider] {msg}")

    # -- classify -----------------------------------------------------------

    def classify(self, message: Message) -> MessageClassification:
        try:
            client = _get_client()
            response = client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=CLASSIFY_SYSTEM_PROMPT,
                messages=[{
                    "role": "user",
                    "content": (
                        f"Source: {message.source}\n"
                        f"Sender: {message.sender_name} ({message.sender_role})\n"
                        f"Project: {message.project}\n"
                        f"Content: {message.content}"
                    ),
                }],
            )
            raw_text = "".join(
                block.text for block in response.content if getattr(block, "type", None) == "text"
            )
            parsed = _extract_json(raw_text)
            if parsed is None:
                self._log("classify(): could not parse LLM JSON response, falling back to rule-based")
                return self._fallback.classify(message)

            message_type = parsed.get("message_type")
            if message_type not in VALID_MESSAGE_TYPES:
                self._log(f"classify(): LLM returned invalid message_type '{message_type}', falling back")
                return self._fallback.classify(message)

            # Build a MessageClassification compatible with the rest of the
            # engine, reusing the rule-based signal detector for any signal
            # fields the LLM didn't return, so downstream code (which reads
            # classification.signals[...] in a few places) never KeyErrors.
            rule_based_classification = self._fallback.classify(message)
            signals = dict(rule_based_classification.signals)
            signals["is_question"] = parsed.get("is_question", signals.get("is_question", False))
            signals["has_escalation"] = parsed.get("has_escalation", signals.get("has_escalation", False))
            signals["is_meeting_transcript"] = parsed.get(
                "is_meeting_transcript", signals.get("is_meeting_transcript", False)
            )

            keywords = dict(rule_based_classification.keywords)
            llm_features = parsed.get("features")
            if llm_features:
                keywords["features"] = llm_features[:3]

            return MessageClassification(message_type=message_type, signals=signals, keywords=keywords)

        except RuntimeError as e:
            # Missing package / missing API key - not worth retrying, just fall back.
            self._log(f"classify(): {e}. Falling back to rule-based.")
            return self._fallback.classify(message)
        except Exception as e:  # network errors, API errors, etc.
            self._log(f"classify(): LLM call failed ({e}). Falling back to rule-based.")
            return self._fallback.classify(message)

    # -- plan -----------------------------------------------------------
    # Intentionally NOT LLM-driven (see module docstring). Reuses the
    # rule-based planner directly so visibility-rule enforcement stays in
    # one place.

    def plan(self, message: Message, classification: MessageClassification) -> List[Task]:
        return self._fallback.plan(message, classification)

    # -- generate_output ------------------------------------------------

    def generate_output(
        self,
        agent: str,
        message: Message,
        classification: MessageClassification,
        context: dict,
    ) -> List[str]:
        try:
            client = _get_client()
            user_prompt = (
                f"Simulate the L3 agent '{agent}'.\n"
                f"Message type: {classification.message_type}\n"
                f"Source: {message.source}\n"
                f"Sender: {message.sender_name} ({message.sender_role})\n"
                f"Project: {message.project}\n"
                f"Content: {message.content}\n"
                f"Known feature/keyword hints: {classification.keywords.get('features')}\n"
            )
            response = client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=GENERATE_OUTPUT_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
            raw_text = "".join(
                block.text for block in response.content if getattr(block, "type", None) == "text"
            )
            parsed = _extract_json(raw_text)
            if not parsed or not parsed.get("output_lines"):
                self._log(f"generate_output({agent}): unparseable/empty LLM response, falling back")
                return self._fallback.generate_output(agent, message, classification, context)
            return parsed["output_lines"]

        except RuntimeError as e:
            self._log(f"generate_output({agent}): {e}. Falling back to rule-based.")
            return self._fallback.generate_output(agent, message, classification, context)
        except Exception as e:
            self._log(f"generate_output({agent}): LLM call failed ({e}). Falling back to rule-based.")
            return self._fallback.generate_output(agent, message, classification, context)
