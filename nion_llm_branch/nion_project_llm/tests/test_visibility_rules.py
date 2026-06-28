"""Tests that the L1->L2/Cross-Cutting and L2->own-L3/Cross-Cutting
visibility rules are enforced for every plan generated across all fixtures."""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nion.coordinator import _select_agents_for_task
from nion.models import Message
from nion.reasoning.rule_based import RuleBasedReasoningProvider
from nion.registry import L3_AGENTS_BY_DOMAIN, is_valid_l1_target, is_valid_l2_subagent

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def test_l1_plan_never_targets_domain_specific_l3():
    """L1 plan tasks may only target an L2 domain or a cross-cutting agent;
    domain-specific L3 agent names (e.g. 'qna', 'action_item_extraction')
    must never appear as a Task.target."""
    provider = RuleBasedReasoningProvider()
    domain_specific_agents = set()
    for agents in L3_AGENTS_BY_DOMAIN.values():
        domain_specific_agents.update(agents.keys())

    for fp in sorted(glob.glob(os.path.join(FIXTURES_DIR, "*.json"))):
        with open(fp) as f:
            data = json.load(f)
        message = Message.from_dict(data)
        classification = provider.classify(message)
        tasks = provider.plan(message, classification)
        for task in tasks:
            assert task.target not in domain_specific_agents, (
                f"{fp}: L1 task {task.id} illegally targets domain-specific "
                f"L3 agent '{task.target}'"
            )
            assert is_valid_l1_target(task.target_type, task.target), (
                f"{fp}: L1 task {task.id} has invalid target "
                f"'{task.target}' (type={task.target_type})"
            )
    print("test_l1_plan_never_targets_domain_specific_l3: PASS")


def test_l2_only_invokes_own_or_cross_cutting_agents():
    """For every Task routed to an L2 domain, the agents selected by the
    coordinator must belong to that domain or be cross-cutting."""
    provider = RuleBasedReasoningProvider()
    for fp in sorted(glob.glob(os.path.join(FIXTURES_DIR, "*.json"))):
        with open(fp) as f:
            data = json.load(f)
        message = Message.from_dict(data)
        classification = provider.classify(message)
        tasks = provider.plan(message, classification)
        for task in tasks:
            if task.target_type != "L2":
                continue
            agents = _select_agents_for_task(task.target, task)
            for agent in agents:
                assert is_valid_l2_subagent(task.target, agent), (
                    f"{fp}: L2:{task.target} task {task.id} illegally "
                    f"selected agent '{agent}'"
                )
    print("test_l2_only_invokes_own_or_cross_cutting_agents: PASS")


def test_all_fixtures_classify_as_expected():
    expected = {
        "msg_001_worked_example.json": "FEATURE_REQUEST",
        "msg_101_status_question.json": "STATUS_QUERY",
        "msg_102_feasibility_question.json": "FEATURE_REQUEST",
        "msg_103_decision_request.json": "DECISION_REQUEST",
        "msg_104_meeting_transcript.json": "MEETING_TRANSCRIPT",
        "msg_105_urgent_escalation.json": "ESCALATION",
        "msg_106_ambiguous.json": "AMBIGUOUS",
    }
    provider = RuleBasedReasoningProvider()
    for filename, expected_type in expected.items():
        fp = os.path.join(FIXTURES_DIR, filename)
        with open(fp) as f:
            data = json.load(f)
        message = Message.from_dict(data)
        classification = provider.classify(message)
        assert classification.message_type == expected_type, (
            f"{filename}: expected {expected_type}, got {classification.message_type}"
        )
    print("test_all_fixtures_classify_as_expected: PASS")


def test_every_plan_executes_without_error():
    """End-to-end smoke test: every fixture should plan + execute + render
    without raising."""
    from nion.engine import ExecutionEngine
    from nion.renderer import OutputRenderer

    provider = RuleBasedReasoningProvider()
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
        assert "L1 PLAN" in output
        assert "L2/L3 EXECUTION" in output
    print("test_every_plan_executes_without_error: PASS")


if __name__ == "__main__":
    test_l1_plan_never_targets_domain_specific_l3()
    test_l2_only_invokes_own_or_cross_cutting_agents()
    test_all_fixtures_classify_as_expected()
    test_every_plan_executes_without_error()
    print("\nAll tests passed.")
