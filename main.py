#!/usr/bin/env python3
"""Nion Orchestration Engine - CLI entrypoint.

Usage:
    python3 main.py path/to/message.json
    python3 main.py < message.json
    echo '{"message_id": "...", ...}' | python3 main.py
"""
import json
import sys

from nion.engine import ExecutionEngine
from nion.models import Message
from nion.reasoning.rule_based import RuleBasedReasoningProvider
from nion.renderer import OutputRenderer


def run(message_dict: dict) -> str:
    provider = RuleBasedReasoningProvider()
    engine = ExecutionEngine(provider)
    renderer = OutputRenderer()

    message = Message.from_dict(message_dict)
    classification = provider.classify(message)
    tasks = provider.plan(message, classification)
    results = engine.execute_plan(tasks, message, classification)
    return renderer.render(message, tasks, results)


def main():
    if len(sys.argv) > 1:
        with open(sys.argv[1], "r") as f:
            data = json.load(f)
    else:
        data = json.load(sys.stdin)

    print(run(data))


if __name__ == "__main__":
    main()
