"""Tests for LLMReasoningProvider - focused on the fallback path, which is
the part that must be bulletproof regardless of API availability. These
tests do NOT require a live ANTHROPIC_API_KEY: they explicitly unset it to
exercise the fallback-to-rule-based behavior.

A full live-API test is intentionally not included here since it would
require a real key and network access in CI; run main.py --provider llm
manually with a key set to test the live path.
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nion.engine import ExecutionEngine
from nion.models import Message
from nion.reasoning.llm_based import LLMReasoningProvider, VALID_MESSAGE_TYPES
from nion.renderer import OutputRenderer

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def test_llm_provider_falls_back_without_api_key():
    """With no ANTHROPIC_API_KEY set, classify() and generate_output() must
    fall back to rule-based behavior rather than raising."""
    os.environ.pop("ANTHROPIC_API_KEY", None)
    provider = LLMReasoningProvider()

    for fp in sorted(glob.glob(os.path.join(FIXTURES_DIR, "*.json"))):
        with open(fp) as f:
            data = json.load(f)
        message = Message.from_dict(data)
        classification = provider.classify(message)
        assert classification.message_type in VALID_MESSAGE_TYPES, (
            f"{fp}: fallback classify() returned invalid type "
            f"'{classification.message_type}'"
        )
        # generate_output should also fall back cleanly for any agent name
        output = provider.generate_output("qna", message, classification, {})
        assert isinstance(output, list) and len(output) > 0
    print("test_llm_provider_falls_back_without_api_key: PASS")


def test_llm_provider_plan_matches_rule_based():
    """plan() is intentionally NOT LLM-driven - it must produce identical
    output to RuleBasedReasoningProvider for the same input."""
    from nion.reasoning.rule_based import RuleBasedReasoningProvider

    os.environ.pop("ANTHROPIC_API_KEY", None)
    llm_provider = LLMReasoningProvider()
    rule_provider = RuleBasedReasoningProvider()

    for fp in sorted(glob.glob(os.path.join(FIXTURES_DIR, "*.json"))):
        with open(fp) as f:
            data = json.load(f)
        message = Message.from_dict(data)
        classification = rule_provider.classify(message)
        llm_tasks = llm_provider.plan(message, classification)
        rule_tasks = rule_provider.plan(message, classification)
        assert [t.id for t in llm_tasks] == [t.id for t in rule_tasks]
        assert [t.target for t in llm_tasks] == [t.target for t in rule_tasks]
    print("test_llm_provider_plan_matches_rule_based: PASS")


def test_end_to_end_with_llm_provider_no_key():
    """Full pipeline (classify -> plan -> execute -> render) must complete
    without error even with no API key, via fallback."""
    os.environ.pop("ANTHROPIC_API_KEY", None)
    provider = LLMReasoningProvider()
    engine = ExecutionEngine(provider)
    renderer = OutputRenderer()

    for fp in sorted(glob.glob(os.path.join(FIXTURES_DIR, "*.json"))):
        with open(fp) as f:
            data = json.load(f)
        message = Message.from_dict(data)
        classification = provider.classify(message)
        tasks = provider.plan(message, classification)
        results = engine.execute_plan(tasks, message, classification)
        output = renderer.render(message, tasks, results)
        assert "NION ORCHESTRATION MAP" in output
    print("test_end_to_end_with_llm_provider_no_key: PASS")


if __name__ == "__main__":
    test_llm_provider_falls_back_without_api_key()
    test_llm_provider_plan_matches_rule_based()
    test_end_to_end_with_llm_provider_no_key()
    print("\nAll LLM provider tests passed.")
