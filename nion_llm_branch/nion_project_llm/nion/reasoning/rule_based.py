"""Rule-based implementation of the ReasoningProvider interface.

Classification works in two stages:
  1. Detect independent boolean/text SIGNALS from the message content
     via keyword/pattern matching.
  2. Derive a single MESSAGE_TYPE from the combination of signals.
This two-stage approach is more robust than one long if/elif chain because
multiple signals can coexist (e.g. a feature request is also a question).
"""
import re
from typing import List

from nion.models import Message, MessageClassification, Task
from nion.reasoning.base import ReasoningProvider
from nion.registry import is_valid_l1_target

# Message type constants
STATUS_QUERY = "STATUS_QUERY"
FEATURE_REQUEST = "FEATURE_REQUEST"
DECISION_REQUEST = "DECISION_REQUEST"
MEETING_TRANSCRIPT = "MEETING_TRANSCRIPT"
ESCALATION = "ESCALATION"
AMBIGUOUS = "AMBIGUOUS"


def _contains_any(text: str, phrases: List[str]) -> bool:
    return any(p in text for p in phrases)


def _detect_signals(message: Message) -> dict:
    content = message.content or ""
    text = content.lower()
    word_count = len(text.split())

    is_question = "?" in content or bool(
        re.match(r"^\s*(what|can|should|why|how|when|who|is|are|do|does|did)\b", text)
    )

    has_status_query = _contains_any(text, ["status of", "what's the status", "update on", "where are we on", "progress on"])

    has_new_feature_request = _contains_any(
        text,
        ["add ", "can we add", "new feature", "integration", "export feature",
         "could we add", "feature request", "would like to add"],
    )

    has_decision_request = bool(
        re.search(r"\bshould we\b", text)
    ) or _contains_any(text, ["prioritize", "which should", "decide", "go/no-go", "go or no-go"])

    has_escalation = _contains_any(
        text,
        ["escalate", "legal", "urgent", "threatening", "still not delivered",
         "asap", "immediately", "critical issue", "angry", "furious"],
    )

    is_meeting_transcript = (
        message.source == "meeting"
        or len(re.findall(r"\b[A-Za-z][A-Za-z ]{0,20}:\s", content)) >= 2
    )

    has_blocker_or_issue = _contains_any(
        text,
        ["blocked", "bug", "bugs", "is down", "broken", "critical bug",
         "issue", "problem", "outage", "failing"],
    )

    has_decision_made = bool(
        re.search(r"\bwe (have )?decided\b|\bwe will\b|\bwe've decided\b", text)
    )

    is_ambiguous = (
        word_count <= 8
        and not is_question
        and not has_new_feature_request
        and not has_decision_request
        and not has_escalation
        and not is_meeting_transcript
    ) or message.project is None

    return {
        "is_question": is_question,
        "has_status_query": has_status_query,
        "has_new_feature_request": has_new_feature_request,
        "has_decision_request": has_decision_request,
        "has_escalation": has_escalation,
        "is_meeting_transcript": is_meeting_transcript,
        "has_blocker_or_issue": has_blocker_or_issue,
        "has_decision_made": has_decision_made,
        "is_ambiguous": is_ambiguous,
        "word_count": word_count,
    }


def _derive_message_type(signals: dict) -> str:
    # Priority order matters: more specific / higher-stakes signals win.
    if signals["is_meeting_transcript"]:
        return MEETING_TRANSCRIPT
    if signals["has_escalation"]:
        return ESCALATION
    if signals["has_new_feature_request"]:
        return FEATURE_REQUEST
    if signals["has_decision_request"]:
        return DECISION_REQUEST
    if signals["has_status_query"] or (signals["is_question"] and not signals["is_ambiguous"]):
        return STATUS_QUERY
    if signals["is_ambiguous"]:
        return AMBIGUOUS
    return STATUS_QUERY  # safe default: treat unclassified questions as status queries


def _extract_keywords(message: Message, signals: dict) -> dict:
    """Pull a few human-readable snippets out of the content to make
    templated output feel grounded rather than generic."""
    content = message.content or ""
    keywords = {}

    # crude "feature" noun-phrase grabber for FEATURE_REQUEST messages.
    # Finds the clause after "add"/"adding", then splits on " and " / commas
    # so "add X and Y" yields two separate feature phrases.
    keywords["features"] = []
    add_clause_match = re.search(
        r"(?:add|adding)\s+(.+?)(?:\.|\?|$| before | in the )",
        content,
        flags=re.IGNORECASE,
    )
    if add_clause_match:
        clause = add_clause_match.group(1)
        parts = re.split(r"\s+and\s+|,\s*", clause)
        for part in parts:
            cleaned = re.sub(r"^a\s+|^an\s+", "", part.strip(), flags=re.IGNORECASE)
            cleaned = cleaned.strip()
            if cleaned and len(cleaned) <= 50:
                keywords["features"].append(cleaned)
    keywords["features"] = keywords["features"][:3]

    if signals["is_meeting_transcript"]:
        speakers = re.findall(r"([A-Za-z][A-Za-z ]{0,20}):\s*([^.]+\.)", content)
        keywords["speaker_lines"] = speakers

    return keywords


class RuleBasedReasoningProvider(ReasoningProvider):
    def classify(self, message: Message) -> MessageClassification:
        signals = _detect_signals(message)
        message_type = _derive_message_type(signals)
        keywords = _extract_keywords(message, signals)
        return MessageClassification(message_type=message_type, signals=signals, keywords=keywords)

    def plan(self, message: Message, classification: MessageClassification) -> List[Task]:
        builder = _PLAN_BUILDERS.get(classification.message_type, _plan_status_query)
        tasks = builder(message, classification)
        for t in tasks:
            if not is_valid_l1_target(t.target_type, t.target):
                raise ValueError(
                    f"Visibility rule violation: L1 cannot target '{t.target}' "
                    f"(target_type={t.target_type})"
                )
        return tasks

    def generate_output(
        self,
        agent: str,
        message: Message,
        classification: MessageClassification,
        context: dict,
    ) -> List[str]:
        generator = _OUTPUT_GENERATORS.get(agent)
        if generator is None:
            return [f"{agent} executed (no detailed template available)"]
        return generator(message, classification, context)


# ---------------------------------------------------------------------------
# Plan builders - one per message type. Each returns an ordered List[Task].
# Task ids are assigned sequentially as TASK-001, TASK-002, ...
# ---------------------------------------------------------------------------

def _next_id(n: int) -> str:
    return f"TASK-{n:03d}"


def _plan_feature_request(message: Message, classification: MessageClassification) -> List[Task]:
    tasks = []
    tasks.append(Task(_next_id(1), "L2", "TRACKING_EXECUTION", "Extract action items from customer request"))
    tasks.append(Task(_next_id(2), "L2", "TRACKING_EXECUTION", "Extract risks from scope change request"))
    tasks.append(Task(_next_id(3), "L2", "TRACKING_EXECUTION", "Extract decision needed"))
    tasks.append(Task(_next_id(4), "L3_CROSS_CUTTING", "knowledge_retrieval", "Retrieve project context and timeline"))
    tasks.append(Task(
        _next_id(5), "L2", "COMMUNICATION_COLLABORATION", "Formulate gap-aware response",
        depends_on=[tasks[0].id, tasks[1].id, tasks[2].id, tasks[3].id],
    ))
    tasks.append(Task(_next_id(6), "L3_CROSS_CUTTING", "evaluation", "Evaluate response before sending", depends_on=[tasks[4].id]))
    tasks.append(Task(_next_id(7), "L2", "COMMUNICATION_COLLABORATION", "Send response to sender", depends_on=[tasks[5].id]))
    return tasks


def _plan_status_query(message: Message, classification: MessageClassification) -> List[Task]:
    tasks = []
    tasks.append(Task(_next_id(1), "L3_CROSS_CUTTING", "knowledge_retrieval", "Retrieve current status and context for requested item"))
    tasks.append(Task(_next_id(2), "L2", "COMMUNICATION_COLLABORATION", "Formulate status response", depends_on=[tasks[0].id]))
    tasks.append(Task(_next_id(3), "L3_CROSS_CUTTING", "evaluation", "Evaluate response before sending", depends_on=[tasks[1].id]))
    tasks.append(Task(_next_id(4), "L2", "COMMUNICATION_COLLABORATION", "Send response to sender", depends_on=[tasks[2].id]))
    return tasks


def _plan_decision_request(message: Message, classification: MessageClassification) -> List[Task]:
    tasks = []
    tasks.append(Task(_next_id(1), "L2", "TRACKING_EXECUTION", "Extract decision needed and identify decision criteria"))
    tasks.append(Task(_next_id(2), "L3_CROSS_CUTTING", "knowledge_retrieval", "Retrieve project context relevant to the decision"))
    tasks.append(Task(
        _next_id(3), "L2", "COMMUNICATION_COLLABORATION", "Formulate recommendation/response",
        depends_on=[tasks[0].id, tasks[1].id],
    ))
    tasks.append(Task(_next_id(4), "L3_CROSS_CUTTING", "evaluation", "Evaluate response before sending", depends_on=[tasks[2].id]))
    tasks.append(Task(_next_id(5), "L2", "COMMUNICATION_COLLABORATION", "Send response to sender", depends_on=[tasks[3].id]))
    return tasks


def _plan_meeting_transcript(message: Message, classification: MessageClassification) -> List[Task]:
    tasks = []
    tasks.append(Task(_next_id(1), "L2", "COMMUNICATION_COLLABORATION", "Capture meeting transcript and generate minutes"))
    tasks.append(Task(_next_id(2), "L2", "TRACKING_EXECUTION", "Extract action items from meeting discussion"))
    tasks.append(Task(_next_id(3), "L2", "TRACKING_EXECUTION", "Extract issues/blockers raised in meeting"))
    tasks.append(Task(
        _next_id(4), "L2", "COMMUNICATION_COLLABORATION", "Generate meeting summary report",
        depends_on=[tasks[0].id, tasks[1].id, tasks[2].id],
    ))
    return tasks


def _plan_escalation(message: Message, classification: MessageClassification) -> List[Task]:
    tasks = []
    tasks.append(Task(_next_id(1), "L2", "TRACKING_EXECUTION", "Extract escalated issue and assess severity"))
    tasks.append(Task(_next_id(2), "L3_CROSS_CUTTING", "knowledge_retrieval", "Retrieve history and context for the escalated item"))
    tasks.append(Task(
        _next_id(3), "L2", "COMMUNICATION_COLLABORATION", "Formulate urgent response addressing escalation",
        depends_on=[tasks[0].id, tasks[1].id],
    ))
    tasks.append(Task(_next_id(4), "L3_CROSS_CUTTING", "evaluation", "Evaluate response tone and accuracy before sending", depends_on=[tasks[2].id]))
    tasks.append(Task(_next_id(5), "L2", "COMMUNICATION_COLLABORATION", "Send priority response to sender", depends_on=[tasks[3].id]))
    return tasks


def _plan_ambiguous(message: Message, classification: MessageClassification) -> List[Task]:
    tasks = []
    tasks.append(Task(_next_id(1), "L3_CROSS_CUTTING", "knowledge_retrieval", "Attempt best-effort context retrieval (limited info available)"))
    tasks.append(Task(
        _next_id(2), "L2", "COMMUNICATION_COLLABORATION", "Formulate gap-aware clarifying response",
        depends_on=[tasks[0].id],
    ))
    tasks.append(Task(_next_id(3), "L3_CROSS_CUTTING", "evaluation", "Evaluate response before sending", depends_on=[tasks[1].id]))
    tasks.append(Task(_next_id(4), "L2", "COMMUNICATION_COLLABORATION", "Send clarifying response to sender", depends_on=[tasks[2].id]))
    return tasks


_PLAN_BUILDERS = {
    FEATURE_REQUEST: _plan_feature_request,
    STATUS_QUERY: _plan_status_query,
    DECISION_REQUEST: _plan_decision_request,
    MEETING_TRANSCRIPT: _plan_meeting_transcript,
    ESCALATION: _plan_escalation,
    AMBIGUOUS: _plan_ambiguous,
}


# ---------------------------------------------------------------------------
# Output generators - one per L3 agent. Each returns List[str] of bullet
# lines (without the leading "• " - the renderer adds that). `context` is
# a dict the execution engine populates with results from already-completed
# tasks (e.g. previously extracted action items, risk count, etc.) so later
# agents like `qna` can reference earlier findings.
# ---------------------------------------------------------------------------

def _gen_action_item_extraction(message, classification, context) -> List[str]:
    features = classification.keywords.get("features") or []
    if features:
        lines = []
        for i, feature in enumerate(features, start=1):
            lines.append(
                f'AI-{i:03d}: "Evaluate {feature}"\n'
                "    Owner: ? | Due: ? | Flags: [MISSING_OWNER, MISSING_DUE_DATE]"
            )
        return lines

    speaker_lines = classification.keywords.get("speaker_lines")
    if speaker_lines:
        # In meeting transcripts, commitments/deliverables (not blockers/bugs)
        # are the action items.
        commitment_markers = ["ready by", "will", "going to", "need to", "might need to"]
        blocker_markers = ["blocked", "bug", "down", "broken", "critical"]
        lines = []
        idx = 1
        for speaker, line in speaker_lines:
            lower = line.lower()
            if any(m in lower for m in commitment_markers) and not any(b in lower for b in blocker_markers):
                lines.append(
                    f'AI-{idx:03d}: "{line.strip()}"\n'
                    f"    Owner: {speaker} | Due: ? | Flags: [MISSING_DUE_DATE]"
                )
                idx += 1
        if lines:
            return lines

    return ['AI-001: "Review and evaluate the request described in the message"\n'
            "    Owner: ? | Due: ? | Flags: [MISSING_OWNER, MISSING_DUE_DATE]"]


def _gen_risk_extraction(message, classification, context) -> List[str]:
    features = classification.keywords.get("features") or []
    risks = []
    if len(features) >= 2:
        risks.append(('"Adding multiple features within the same timeline"', "HIGH", "HIGH"))
        risks.append(('"Scope creep from expanded requirements"', "MEDIUM", "MEDIUM"))
    elif len(features) == 1:
        risks.append((f'"Adding {features[0]} may impact existing release timeline"', "MEDIUM", "MEDIUM"))
    else:
        risks.append(('"Unclear scope may lead to misaligned expectations"', "MEDIUM", "LOW"))
    lines = []
    for i, (desc, likelihood, impact) in enumerate(risks, start=1):
        lines.append(f"RISK-{i:03d}: {desc}\n    Likelihood: {likelihood} | Impact: {impact}")
    return lines


def _gen_decision_extraction(message, classification, context) -> List[str]:
    if classification.message_type == DECISION_REQUEST:
        desc = '"Determine priority between competing initiatives"'
    else:
        desc = '"Accept or reject the request described in the message"'
    return [f"DEC-001: {desc}\n    Decision Maker: ? | Status: PENDING"]


def _gen_issue_extraction(message, classification, context) -> List[str]:
    content = (message.content or "")
    severity = "HIGH" if classification.signals.get("has_escalation") else "MEDIUM"
    speaker_lines = classification.keywords.get("speaker_lines")
    lines = []
    if speaker_lines:
        idx = 1
        for speaker, line in speaker_lines:
            lower = line.lower()
            if any(k in lower for k in ["blocked", "bug", "down", "broken", "critical"]):
                lines.append(
                    f'ISSUE-{idx:03d}: "{line.strip()}" (raised by {speaker})\n'
                    f"    Severity: {severity} | Status: OPEN"
                )
                idx += 1
        if lines:
            return lines
    truncated_raw = content[:80].strip()
    if len(content) > 80:
        # break on the last whitespace within the truncation window to avoid
        # cutting mid-word
        last_space = truncated_raw.rfind(" ")
        if last_space > 40:  # only trim further if it doesn't lose too much
            truncated_raw = truncated_raw[:last_space]
        truncated = f"{truncated_raw}..."
    else:
        truncated = truncated_raw
    return [f'ISSUE-001: "{truncated}"\n    Severity: {severity} | Status: OPEN']


def _gen_meeting_attendance(message, classification, context) -> List[str]:
    speaker_lines = classification.keywords.get("speaker_lines") or []
    lines = [f"Meeting captured: {len(speaker_lines)} speaker contributions logged"]
    for speaker, line in speaker_lines:
        lines.append(f"{speaker}: {line.strip()}")
    lines.append("Minutes generated and stored")
    return lines


def _gen_knowledge_retrieval(message, classification, context) -> List[str]:
    project = message.project or "UNKNOWN"
    if message.project is None:
        return [
            "Project: UNKNOWN (not specified in message)",
            "Context retrieval limited - no project identifier available",
        ]
    return [
        f"Project: {project}",
        "Current Release Date: Dec 15",
        "Days Remaining: 20",
        "Code Freeze: Dec 10",
        "Current Progress: 70%",
        "Team Capacity: 85% utilized",
        "Engineering Manager: Alex Kim",
        "Tech Lead: David Park",
    ]


def _gen_qna(message, classification, context) -> List[str]:
    mtype = classification.message_type
    sender_first_name = (message.sender_name or "there").split(" ")[0]

    if mtype == FEATURE_REQUEST:
        features = classification.keywords.get("features") or ["the requested feature(s)"]
        feature_str = " and ".join(features)
        response = (
            f'Response: "Thanks for the update, {sender_first_name}! For {feature_str}:\n\n'
            "    WHAT I KNOW:\n"
            "    • Current timeline: Dec 15 (code freeze Dec 10)\n"
            "    • Team capacity: 85% utilized\n"
            "    • Progress: 70% complete\n\n"
            "    WHAT I'VE LOGGED:\n"
            f"    • {len(features)} action item{'s' if len(features) != 1 else ''} for feature evaluation\n"
            "    • Risk(s) flagged for timeline/scope impact\n"
            "    • 1 pending decision\n\n"
            "    WHAT I NEED:\n"
            "    • Complexity estimates from Engineering (Alex Kim / David Park)\n"
            "    • Go/no-go decision from leadership\n\n"
            "    I cannot assess feasibility without Engineering input on whether "
            "this can fit in the remaining timeline at current capacity.\""
        )
    elif mtype == STATUS_QUERY:
        response = (
            f'Response: "Hi {sender_first_name}, here is the current status:\n\n'
            "    • Progress: 70% complete\n"
            "    • Team capacity: 85% utilized\n"
            "    • On track for the Dec 15 release date (code freeze Dec 10)\n\n"
            "    Let me know if you need a more detailed breakdown.\""
        )
    elif mtype == DECISION_REQUEST:
        response = (
            f'Response: "Hi {sender_first_name}, based on current context:\n\n'
            "    • Team capacity: 85% utilized, 70% through current scope\n"
            "    • This decision has been logged as DEC-001 (PENDING)\n\n"
            "    WHAT I NEED:\n"
            "    • Risk/impact input from the relevant leads before recommending "
            "a priority order.\""
        )
    elif mtype == ESCALATION:
        response = (
            f'Response: "Hi {sender_first_name}, I understand the urgency. Here is what I found:\n\n'
            "    • Issue logged as ISSUE-001 with HIGH severity\n"
            "    • Pulling historical context on this item now\n\n"
            "    WHAT I NEED:\n"
            "    • Confirmation from the original owner on root cause and revised timeline "
            "before I can provide a full explanation.\""
        )
    else:  # AMBIGUOUS
        response = (
            f'Response: "Hi {sender_first_name}, thanks for flagging this. The message doesn\'t '
            "specify which project, task, or area you mean.\n\n"
            "    WHAT I NEED:\n"
            "    • Which project this relates to\n"
            "    • What specifically should be sped up (a feature, a process, a delivery date)\n\n"
            "    Once I have that, I can pull the right context and give you a concrete answer.\""
        )
    return [response]


def _gen_report_generation(message, classification, context) -> List[str]:
    speaker_lines = classification.keywords.get("speaker_lines") or []
    lines = [
        "Report Type: Meeting Summary",
        f"Contributions Captured: {len(speaker_lines)}",
        "Action Items Logged: see TRACKING_EXECUTION output",
        "Issues Logged: see TRACKING_EXECUTION output",
        "Report Status: GENERATED",
    ]
    return lines


def _gen_evaluation(message, classification, context) -> List[str]:
    return [
        "Relevance: PASS",
        "Accuracy: PASS",
        "Tone: PASS",
        "Gaps Acknowledged: PASS",
        "Result: APPROVED",
    ]


def _gen_message_delivery(message, classification, context) -> List[str]:
    lines = [
        f"Channel: {message.source}",
        f"Recipient: {message.sender_name}",
    ]
    if classification.message_type == FEATURE_REQUEST:
        lines.append("CC: Alex Kim (Engineering Manager)")
    if classification.message_type == ESCALATION:
        lines.append("Priority: HIGH")
    lines.append("Delivery Status: SENT")
    return lines


_OUTPUT_GENERATORS = {
    "action_item_extraction": _gen_action_item_extraction,
    "risk_extraction": _gen_risk_extraction,
    "decision_extraction": _gen_decision_extraction,
    "issue_extraction": _gen_issue_extraction,
    "meeting_attendance": _gen_meeting_attendance,
    "knowledge_retrieval": _gen_knowledge_retrieval,
    "qna": _gen_qna,
    "report_generation": _gen_report_generation,
    "evaluation": _gen_evaluation,
    "message_delivery": _gen_message_delivery,
}
