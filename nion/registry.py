"""Static registry of Nion components and visibility rules.

This encodes the architecture described in the assessment doc:
- 3 L2 domains
- 2 cross-cutting L3 agents (visible to L1 AND all L2 domains)
- domain-specific L3 agents (visible ONLY to their owning L2 domain)
"""

L2_DOMAINS = [
    "TRACKING_EXECUTION",
    "COMMUNICATION_COLLABORATION",
    "LEARNING_IMPROVEMENT",
]

CROSS_CUTTING_AGENTS = {
    "knowledge_retrieval": "Retrieves context from database - project info, stakeholder details, historical data",
    "evaluation": "Validates outputs before delivery - checks accuracy, tone, completeness",
}

# Domain-specific L3 agents. Only visible to their owning L2 domain (+ cross-cutting).
L3_AGENTS_BY_DOMAIN = {
    "TRACKING_EXECUTION": {
        "action_item_extraction": "Extracts action items from message content, infers owners and due dates",
        "action_item_validation": "Validates action items have required fields, flags missing info",
        "action_item_tracking": "Tracks action items to completion, provides status snapshots",
        "risk_extraction": "Extracts risks from message content, assesses likelihood and impact",
        "risk_tracking": "Tracks risks, provides risk snapshots",
        "issue_extraction": "Extracts issues/problems from message content, assesses severity",
        "issue_tracking": "Tracks issues to resolution, provides issue snapshots",
        "decision_extraction": "Extracts decisions from message content, identifies decision maker",
        "decision_tracking": "Tracks decisions to implementation",
    },
    "COMMUNICATION_COLLABORATION": {
        "qna": "Formulates responses to questions, handles both direct answers and gap-aware responses",
        "report_generation": "Creates formatted reports (status reports, summaries, digests)",
        "message_delivery": "Sends messages via appropriate channels (email, Slack, Teams)",
        "meeting_attendance": "Captures meeting transcripts, generates meeting minutes",
    },
    "LEARNING_IMPROVEMENT": {
        "instruction_led_learning": "Learns from explicit instructions, stores SOPs and rules",
    },
}


def is_valid_l1_target(target_type: str, target: str) -> bool:
    """Enforces visibility rule: L1 may only address an L2 domain or a
    cross-cutting agent - never a domain-specific L3 agent directly."""
    if target_type == "L2":
        return target in L2_DOMAINS
    if target_type == "L3_CROSS_CUTTING":
        return target in CROSS_CUTTING_AGENTS
    return False


def is_valid_l2_subagent(domain: str, agent: str) -> bool:
    """Enforces visibility rule: an L2 domain may only invoke its own L3
    agents or a cross-cutting agent."""
    if agent in CROSS_CUTTING_AGENTS:
        return True
    return agent in L3_AGENTS_BY_DOMAIN.get(domain, {})


def domain_for_agent(agent: str) -> str:
    """Find which L2 domain owns a given domain-specific L3 agent."""
    for domain, agents in L3_AGENTS_BY_DOMAIN.items():
        if agent in agents:
            return domain
    raise ValueError(f"Agent '{agent}' is not a registered domain-specific L3 agent")
