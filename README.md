# Nion Orchestration Engine

A simplified simulation of Nion's three-tier orchestration architecture (L1 Orchestrator → L2 Coordinators → L3 Agents). Given an input message (JSON), the program reasons about it and prints a full orchestration map showing the L1 plan followed by L2/L3 execution.

## Setup

Requires Python 3.8+. No external dependencies.

**Path of the files**
```
main.py                         
nion/
| models.py                     
| registry.py                   
| reasoning/
| | base.py                     
| | rule_based.py                
| coordinator.py                
| engine.py                     
| renderer.py                   
tests/
| fixtures/                    
| test_visibility_rules.py     
test_case_outputs/                 
```

```bash
cd Nion-Orchestration-Engine
py main.py "<path to message.json>"
```

## Running the test cases

All 6 assessment test cases are located under `tests/fixtures/`. To run any of them:

```bash
py main.py tests/fixtures/msg_101_status_question.json
py main.py tests/fixtures/msg_102_feasibility_question.json
py main.py tests/fixtures/msg_103_decision_request.json
py main.py tests/fixtures/msg_104_meeting_transcript.json
py main.py tests/fixtures/msg_105_urgent_escalation.json
py main.py tests/fixtures/msg_106_ambiguous.json
```

The outputs for each test case is available as a .txt file as well as images inside a .pdf file and is located under `test_case_outputs`.

## Running the automated check for visibility

```bash
py tests/test_visibility_rules.py
```

This checks:
- **Visibility rule (L1)**: the L1 plan never targets a domain-specific L3 agent directly — only `L2:<domain>` or `L3:<cross-cutting-agent>`.
- **Visibility rule (L2)**: each L2 coordinator only ever invokes its own domain's L3 agents or the cross-cutting agents — never another domain's.
- **Classification correctness**: every fixture classifies into the expected message type.
- **End-to-end smoke test**: every fixture plans, executes, and renders without error.


### Reasoning approach: Rule-based

The reasoning layer (deciding what a message is about, what to extract, and what response to draft) is implemented via the `ReasoningProvider` interface, with a `RuleBasedReasoningProvider` as the concrete implementation. 
Classification works in two stages:

1. **Signal detection** — keyword/pattern matching over the message content
   to detect things like `is_question`, `has_new_feature_request`,
   `has_decision_request`, `has_escalation`, `is_meeting_transcript`,
   `is_ambiguous`, etc.
2. **Message-type derivation** — a set of rules(ordered by priority) combines
   those signals into one of six message types: `FEATURE_REQUEST`,
   `STATUS_QUERY`, `DECISION_REQUEST`, `MEETING_TRANSCRIPT`, `ESCALATION`,
   `AMBIGUOUS`.

Each message type maps to a predefined L1 Task plan template (which L2 domains/cross-cutting agents get invoked, in what order, and with what dependencies). 
Within an L2 domain, the coordinator picks specific L3 agents based on the Task's purpose.


### Visibility rules — how they're enforced

The visibility rules:
- L1 sees only L2 domains + cross-cutting agents (never domain-specific L3 agents directly).
- Each L2 sees only its own L3 agents + cross-cutting agents.

This is enforced structurally:
- `registry.is_valid_l1_target()` is called on every `Task` the planner produces; 
  a `Task` that names a domain-specific L3 agent raises a `ValueError` immediately.
- `registry.is_valid_l2_subagent()` is called by `L2Coordinator.execute()` before invoking any agent; 
  an attempt to invoke another domain's L3 agent raises a `ValueError`.
- This is also covered by `tests/test_visibility_rules.py`, which checks every fixture's generated plan against both rules.

## Message type - Plan Summary

| Message Type | L1 Plan Shape |
|---|---|
| `FEATURE_REQUEST` | action_item + risk + decision extraction + knowledge_retrieval → qna (depends on all 4) → evaluation → message_delivery |
| `STATUS_QUERY` | knowledge_retrieval → qna → evaluation → message_delivery |
| `DECISION_REQUEST` | decision_extraction + knowledge_retrieval → qna → evaluation → message_delivery |
| `MEETING_TRANSCRIPT` | meeting_attendance + action_item_extraction + issue_extraction (parallel) → report_generation |
| `ESCALATION` | issue_extraction + knowledge_retrieval → qna → evaluation → message_delivery  |
| `AMBIGUOUS` | knowledge_retrieval → qna → evaluation → message_delivery |

## Known limitations / design choices

- Classification is rule-based (keyword/regex), not a real NLP model. 
  This allows for dummy/templated output, and keeps the engine fully deterministic and dependency-free.
- The `qna` agent's draft response is plain-text with embedded formatting 
  (e.g. "WHAT I KNOW / WHAT I'VE LOGGED / WHAT I NEED" sections) rather than
  a separately-tracked structured object.
- `knowledge_retrieval` always returns the same canned project metadata
  (release date, code freeze, team capacity, etc.) regardless of which real
  project is named, since there's no real project database to query.
