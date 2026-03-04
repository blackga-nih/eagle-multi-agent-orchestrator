"""
Human-readable status messages for agents and tools.

Maps internal agent/tool names to user-friendly display names
and contextual status messages.
"""

AGENT_DISPLAY_NAMES = {
    "supervisor": "EAGLE Assistant",
    "legal-counsel": "Legal Counsel",
    "market-intelligence": "Market Intelligence",
    "tech-translator": "Technical Translator",
    "public-interest": "Public Interest Advisor",
    "policy-supervisor": "Policy Supervisor",
    "policy-librarian": "Policy Librarian",
    "policy-analyst": "Policy Analyst",
}

SKILL_DISPLAY_NAMES = {
    "oa-intake": "Intake Workflow",
    "document-generator": "Document Generator",
    "compliance": "Compliance Checker",
    "knowledge-retrieval": "Knowledge Search",
    "tech-review": "Technical Review",
}

TOOL_STATUS_MESSAGES = {
    "s3_document_ops": {
        "list": "Listing documents...",
        "read": "Reading document...",
        "write": "Saving document...",
        "_default": "Accessing documents...",
    },
    "dynamodb_intake": {
        "get": "Loading intake data...",
        "put": "Saving intake data...",
        "query": "Querying records...",
        "_default": "Accessing intake data...",
    },
    "search_far": "Searching FAR/DFARS regulations...",
    "create_document": {
        "sow": "Generating Statement of Work...",
        "igce": "Generating Cost Estimate...",
        "market_research": "Generating Market Research...",
        "ja": "Generating Justification & Approval...",
        "_default": "Generating document...",
    },
    "cloudwatch_logs": "Querying logs...",
    "intake_workflow": {
        "start": "Starting intake workflow...",
        "advance": "Advancing to next phase...",
        "complete": "Completing intake...",
        "_default": "Processing intake...",
    },
}


def get_tool_status_message(tool_name: str, tool_input: dict = None) -> str:
    """Get a human-readable status message for a tool invocation."""
    entry = TOOL_STATUS_MESSAGES.get(tool_name)
    if entry is None:
        return f"Running {tool_name}..."
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict) and tool_input:
        for key in ("operation", "doc_type", "action", "type"):
            val = tool_input.get(key)
            if val and val in entry:
                return entry[val]
        return entry.get("_default", f"Running {tool_name}...")
    return f"Running {tool_name}..."


def get_agent_display_name(agent_name: str) -> str:
    """Get a human-readable display name for an agent."""
    return (
        AGENT_DISPLAY_NAMES.get(agent_name)
        or SKILL_DISPLAY_NAMES.get(agent_name)
        or agent_name.replace("-", " ").title()
    )
