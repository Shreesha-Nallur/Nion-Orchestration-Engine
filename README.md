# Nion Orchestration Engine

A simplified simulation of Nion's three-tier orchestration architecture
(L1 Orchestrator → L2 Coordinators → L3 Agents). Given an input message
(JSON), the program reasons about it and prints a full orchestration map
showing the L1 plan followed by L2/L3 execution.

## Setup

Requires Python 3.8+. No external dependencies — standard library only.

```bash
cd nion_project
python3 main.py path/to/message.json
```

Or pipe JSON via stdin:

```bash
cat message.json | python3 main.py
```

## Running the test cases

All 6 assessment test cases (plus the spec's worked example, MSG-001) are
saved under `tests/fixtures/`. To run any of them:

```bash
python3 main.py tests/fixtures/msg_101_status_question.json
python3 main.py tests/fixtures/msg_102_feasibility_question.json
python3 main.py tests/fixtures/msg_103_decision_request.json
python3 main.py tests/fixtures/msg_104_meeting_transcript.json
python3 main.py tests/fixtures/msg_105_urgent_escalation.json
python3 main.py tests/fixtures/msg_106_ambiguous.json
```

Pre-generated output for every test case (and the worked example) is saved
under `sample_outputs/`.

## Running the automated tests

```bash
python3 tests/test_visibility_rules.py
```

This checks:
- **Visibility rule (L1)**: the L1 plan never targets a domain-specific L3
  agent directly — only `L2:<domain>` or `L3:<cross-cutting-agent>`.
- **Visibility rule (L2)**: each L2 coordinator only ever invokes its own
  domain's L3 agents or the cross-cutting agents — never another domain's.
- **Classification correctness**: every fixture (worked example + all 6
  test cases) classifies into the expected message type.
- **End-to-end smoke test**: every fixture plans, executes, and renders
  without error.

## Architecture

```
main.py                         CLI entrypoint
nion/
  models.py                     Message, Task, SubTask, ExecutionResult, etc.
  registry.py                   Static component registry + visibility-rule
                                 helper functions (is_valid_l1_target,
                                 is_valid_l2_subagent)
  reasoning/
    base.py                     ReasoningProvider interface (classify, plan,
                                 generate_output)
    rule_based.py                RuleBasedReasoningProvider: keyword/pattern
                                 based classification, plan templates per
                                 message type, templated L3 output generation
  coordinator.py                L2Coordinator: selects + invokes the right
                                 L3 agents for a Task within its domain
  engine.py                     ExecutionEngine: walks the L1 plan, routes
                                 each Task to an L2Coordinator or runs a
                                 cross-cutting L3 agent directly
  renderer.py                   OutputRenderer: formats the final text report
tests/
  fixtures/                    All 7 input JSONs (worked example + 6 test cases)
  test_visibility_rules.py      Automated tests (see above)
sample_outputs/                 Saved output for every test case
```

### Reasoning approach: rule-based, with an LLM hook

The "intelligence" layer (deciding what a message is about, what to extract,
and what response to draft) is implemented via the `ReasoningProvider`
interface, with a `RuleBasedReasoningProvider` as the only concrete
implementation. Classification works in two stages:

1. **Signal detection** — keyword/pattern matching over the message content
   to detect things like `is_question`, `has_new_feature_request`,
   `has_decision_request`, `has_escalation`, `is_meeting_transcript`,
   `is_ambiguous`, etc.
2. **Message-type derivation** — a priority-ordered set of rules combines
   those signals into one of six message types: `FEATURE_REQUEST`,
   `STATUS_QUERY`, `DECISION_REQUEST`, `MEETING_TRANSCRIPT`, `ESCALATION`,
   `AMBIGUOUS`.

Each message type maps to a predefined **L1 task plan template** (which L2
domains / cross-cutting agents get invoked, in what order, with what
dependencies). Within an L2 domain, the **coordinator** picks specific L3
agents based on the Task's purpose text.

L3 "execution" output (the bullet content under each agent) is templated
text, lightly parameterized using details pulled from the message (e.g. the
specific feature name in a feature request, or speaker lines in a meeting
transcript) — per the spec's note that *"L3 entries showing responses are
just dummy placeholders and can be generated randomly."*

This is intentionally **swappable**: because all reasoning goes through the
`ReasoningProvider` interface, a future `LLMReasoningProvider` (e.g. backed
by the Claude API) could implement the same three methods —
`classify`, `plan`, `generate_output` — and be dropped in to `main.py`
without touching `engine.py`, `coordinator.py`, or `renderer.py` at all.

### Visibility rules — how they're enforced

The spec requires:
- L1 sees only L2 domains + cross-cutting agents (never domain-specific L3
  agents directly).
- Each L2 sees only its own L3 agents + cross-cutting agents.

This is enforced **structurally**, not just by convention:
- `registry.is_valid_l1_target()` is called on every `Task` the planner
  produces; a `Task` that names a domain-specific L3 agent raises a
  `ValueError` immediately.
- `registry.is_valid_l2_subagent()` is called by `L2Coordinator.execute()`
  before invoking any agent; an attempt to invoke another domain's L3 agent
  raises a `ValueError`.
- This is also covered by `tests/test_visibility_rules.py`, which checks
  every fixture's generated plan against both rules.

## Message type → plan summary

| Message Type | L1 Plan Shape |
|---|---|
| `FEATURE_REQUEST` | action_item + risk + decision extraction (parallel, TRACKING_EXECUTION) + knowledge_retrieval → qna (depends on all 4) → evaluation → message_delivery |
| `STATUS_QUERY` | knowledge_retrieval → qna → evaluation → message_delivery |
| `DECISION_REQUEST` | decision_extraction + knowledge_retrieval → qna → evaluation → message_delivery |
| `MEETING_TRANSCRIPT` | meeting_attendance + action_item_extraction + issue_extraction (parallel) → report_generation |
| `ESCALATION` | issue_extraction (HIGH severity) + knowledge_retrieval → qna (urgent tone) → evaluation → message_delivery (flagged HIGH priority) |
| `AMBIGUOUS` | best-effort knowledge_retrieval → qna (gap-heavy, asks clarifying questions, no fabricated specifics) → evaluation → message_delivery |

## Known limitations / design choices

- Classification is rule-based (keyword/regex), not a real NLP model. This
  matches the spec's allowance for dummy/templated output, and keeps the
  engine fully deterministic and dependency-free for grading.
- The `qna` agent's draft response is plain-text with embedded formatting
  (e.g. "WHAT I KNOW / WHAT I'VE LOGGED / WHAT I NEED" sections) rather than
  a separately-tracked structured object — this mirrors the style of the
  spec's worked example output.
- `knowledge_retrieval` always returns the same canned project metadata
  (release date, code freeze, team capacity, etc.) regardless of which real
  project is named, since there's no real project database to query. This
  is explicitly allowed by the spec ("dummy placeholders").
