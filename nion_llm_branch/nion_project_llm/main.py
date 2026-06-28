#!/usr/bin/env python3
"""Nion Orchestration Engine - CLI entrypoint.

Usage:
    python3 main.py path/to/message.json
    python3 main.py path/to/message.json --provider llm
    python3 main.py < message.json
    echo '{"message_id": "...", ...}' | python3 main.py

The --provider flag selects which ReasoningProvider implementation drives
classification and L3 output generation (the L1 plan itself always uses the
rule-based templates - see nion/reasoning/llm_based.py for why).
  rule (default): fully offline, deterministic, no dependencies.
  llm:            uses the Anthropic API (requires `pip install anthropic`
                  and an ANTHROPIC_API_KEY environment variable). Falls
                  back to rule-based automatically on any API error.
"""
import argparse
import json
import sys

from nion.engine import ExecutionEngine
from nion.models import Message
from nion.renderer import OutputRenderer


def _build_provider(provider_name: str, verbose: bool):
    if provider_name == "llm":
        from nion.reasoning.llm_based import LLMReasoningProvider
        return LLMReasoningProvider(verbose=verbose)
    from nion.reasoning.rule_based import RuleBasedReasoningProvider
    return RuleBasedReasoningProvider()


def run(message_dict: dict, provider_name: str = "rule", verbose: bool = False) -> str:
    provider = _build_provider(provider_name, verbose)
    engine = ExecutionEngine(provider)
    renderer = OutputRenderer()

    message = Message.from_dict(message_dict)
    classification = provider.classify(message)
    tasks = provider.plan(message, classification)
    results = engine.execute_plan(tasks, message, classification)
    return renderer.render(message, tasks, results)


def main():
    parser = argparse.ArgumentParser(description="Nion Orchestration Engine")
    parser.add_argument(
        "input_file",
        nargs="?",
        help="Path to input message JSON file. If omitted, reads from stdin.",
    )
    parser.add_argument(
        "--provider",
        choices=["rule", "llm"],
        default="rule",
        help="Reasoning provider to use (default: rule)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print provider-level diagnostics (e.g. LLM fallback notices) to stderr-equivalent.",
    )
    args = parser.parse_args()

    if args.input_file:
        with open(args.input_file, "r") as f:
            data = json.load(f)
    else:
        data = json.load(sys.stdin)

    print(run(data, provider_name=args.provider, verbose=args.verbose))


if __name__ == "__main__":
    main()
