#!/usr/bin/env python3
"""
Multi-Agent Orchestrator — Claude Agent SDK

Demonstrates the Supervisor → Subagent pattern from TAC Lesson 26 (O-Agent).
A supervisor delegates to specialist subagents, each with its own context window,
tools, and model. The supervisor only has the Task tool, forcing delegation.

Key TAC Patterns:
  - Supervisor-only-Task: supervisor.allowed_tools = ["Task"]
  - Separate context windows: each AgentDefinition gets its own context
  - Skill → Subagent conversion: skill markdown → AgentDefinition.prompt
  - Parent tracking: parent_tool_use_id links subagent messages to Task calls
  - Tier-gated tools: subscription level controls which tools each subagent gets
  - Cost budgeting: max_budget_usd per query + per-subagent model selection

Usage:
    python examples/sdk/orchestrator.py

Requires:
    pip install claude-agent-sdk
    # Plus either:
    export ANTHROPIC_API_KEY=sk-...          # Direct API
    # Or:
    export CLAUDE_CODE_USE_BEDROCK=1         # AWS Bedrock
    export AWS_REGION=us-east-1
"""

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Any

from claude_agent_sdk import (
    AgentDefinition,
    ClaudeAgentOptions,
    query,
)


# ── Subagent Definitions ──────────────────────────────────
# Each agent gets its own context window and scoped tools.

AGENTS = {
    "researcher": AgentDefinition(
        description=(
            "Researches topics by reading files and searching code. "
            "Use for questions that need codebase exploration."
        ),
        prompt=(
            "You are a code researcher. Given a question, explore the codebase "
            "using Glob and Read to find relevant files, then summarize your "
            "findings in 3-5 bullet points. Be precise — cite file paths and "
            "line numbers. Do NOT make assumptions about files you haven't read."
        ),
        tools=["Read", "Glob", "Grep"],
        model="haiku",  # Fast + cheap for exploration
    ),
    "analyzer": AgentDefinition(
        description=(
            "Analyzes code quality, identifies patterns, and counts metrics. "
            "Use for code review and assessment tasks."
        ),
        prompt=(
            "You are a code analyst. Given code or a codebase section, analyze:\n"
            "1. Code patterns and anti-patterns\n"
            "2. Complexity and maintainability\n"
            "3. Test coverage gaps\n"
            "4. Security concerns\n\n"
            "Provide a structured report with severity ratings (low/medium/high)."
        ),
        tools=["Read", "Grep"],
        model="sonnet",  # Smarter model for analysis
    ),
    "reporter": AgentDefinition(
        description=(
            "Generates formatted reports and summaries. "
            "Use after research and analysis are complete."
        ),
        prompt=(
            "You are a technical writer. Given analysis results, produce a "
            "clear, concise report in markdown format with:\n"
            "- Executive summary (2-3 sentences)\n"
            "- Key findings (bullet list)\n"
            "- Recommendations (prioritized)\n\n"
            "Write for a technical audience. No fluff."
        ),
        tools=[],  # No tools — just synthesis
        model="haiku",
    ),
}


# ── Message Collector ─────────────────────────────────────
# Processes messages from the query() async generator.

@dataclass
class OrchestratorResult:
    """Collects results from an orchestration run."""
    session_id: str | None = None
    messages: list[dict[str, Any]] = None
    subagent_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0

    def __post_init__(self):
        if self.messages is None:
            self.messages = []


def process_message(message: Any, result: OrchestratorResult, verbose: bool = True):
    """Process a single message from the query() stream."""
    msg_type = type(message).__name__

    if msg_type == "SystemMessage":
        # First message — extract session_id
        if hasattr(message, "data") and isinstance(message.data, dict):
            result.session_id = message.data.get("session_id")
        if verbose:
            print(f"[system] Session: {result.session_id}")

    elif msg_type == "AssistantMessage":
        # Model output — check if it's from a subagent
        parent_id = getattr(message, "parent_tool_use_id", None)
        if parent_id:
            result.subagent_calls += 1
            prefix = "[subagent]"
        else:
            prefix = "[supervisor]"

        # Extract text content
        content = getattr(message, "content", [])
        for block in content:
            if hasattr(block, "text"):
                result.messages.append({"role": prefix, "text": block.text})
                if verbose:
                    # Truncate long output for readability
                    text = block.text[:200] + "..." if len(block.text) > 200 else block.text
                    print(f"{prefix} {text}")
            elif hasattr(block, "name"):
                # Tool use block
                if verbose:
                    print(f"{prefix} -> tool: {block.name}")

    elif msg_type == "ResultMessage":
        # Final message — extract usage stats
        usage = getattr(message, "usage", None)
        if usage:
            result.total_input_tokens = getattr(usage, "input_tokens", 0)
            result.total_output_tokens = getattr(usage, "output_tokens", 0)
        cost = getattr(message, "cost_usd", 0.0)
        result.total_cost_usd = cost or 0.0

        # Capture session_id if not already set
        if not result.session_id:
            result.session_id = getattr(message, "session_id", None)

        if verbose:
            print(f"\n[result] Tokens: {result.total_input_tokens}in / "
                  f"{result.total_output_tokens}out | "
                  f"Cost: ${result.total_cost_usd:.4f} | "
                  f"Subagent calls: {result.subagent_calls}")


# ── Orchestrator ──────────────────────────────────────────

async def orchestrate(
    prompt: str,
    agents: dict[str, AgentDefinition] | None = None,
    resume_session: str | None = None,
    max_turns: int = 15,
    max_budget_usd: float = 0.50,
    verbose: bool = True,
) -> OrchestratorResult:
    """
    Run the supervisor orchestrator with subagent delegation.

    Args:
        prompt: The user's query
        agents: Subagent definitions (defaults to AGENTS)
        resume_session: Session ID to resume (multi-turn)
        max_turns: Maximum tool-use loop iterations
        max_budget_usd: Cost cap in USD
        verbose: Print messages as they arrive

    Returns:
        OrchestratorResult with collected messages and stats
    """
    if agents is None:
        agents = AGENTS

    # Build environment — detect Bedrock vs Direct API
    env = {}
    if os.environ.get("CLAUDE_CODE_USE_BEDROCK") == "1":
        env["CLAUDE_CODE_USE_BEDROCK"] = "1"
        env["AWS_REGION"] = os.environ.get("AWS_REGION", "us-east-1")

    # Build options
    options = ClaudeAgentOptions(
        model="sonnet",
        system_prompt=(
            "You are a Technical Analysis Supervisor. You have three specialist "
            "subagents available via the Task tool:\n\n"
            "1. **researcher** — Explores the codebase (Glob, Read, Grep)\n"
            "2. **analyzer** — Reviews code quality and patterns (Read, Grep)\n"
            "3. **reporter** — Writes formatted reports (no tools)\n\n"
            "For every user request:\n"
            "1. First delegate to researcher to gather facts\n"
            "2. Then delegate to analyzer to assess the findings\n"
            "3. Finally delegate to reporter to produce the output\n\n"
            "You MUST delegate — do not answer directly. Use the Task tool "
            "with the agent name and a clear prompt for each delegation."
        ),
        allowed_tools=["Task"],  # ONLY Task — forces delegation
        agents=agents,
        permission_mode="bypassPermissions",
        max_turns=max_turns,
        max_budget_usd=max_budget_usd,
        cwd=os.getcwd(),
        env=env,
    )

    # Add resume if multi-turn
    if resume_session:
        options = ClaudeAgentOptions(
            **{**vars(options), "resume": resume_session}
        )

    # Execute
    result = OrchestratorResult()
    if verbose:
        print(f"{'=' * 60}")
        print(f"Orchestrator: {prompt[:80]}")
        print(f"{'=' * 60}")

    async for message in query(prompt=prompt, options=options):
        process_message(message, result, verbose=verbose)

    return result


# ── Tier-Gated Agents ────────────────────────────────────
# Demonstrates how subscription tiers control agent capabilities.

TIER_TOOLS = {
    "basic": {
        "researcher": ["Glob"],             # Basic: search only
        "analyzer": ["Read"],               # Basic: read only
        "reporter": [],                     # Basic: no tools
    },
    "advanced": {
        "researcher": ["Read", "Glob"],     # Advanced: + read files
        "analyzer": ["Read", "Grep"],       # Advanced: + search content
        "reporter": [],
    },
    "premium": {
        "researcher": ["Read", "Glob", "Grep", "Bash"],  # Premium: full access
        "analyzer": ["Read", "Grep", "Bash"],
        "reporter": ["Write"],              # Premium: can write reports
    },
}


def build_tier_agents(tier: str) -> dict[str, AgentDefinition]:
    """Build agents with tier-appropriate tool access."""
    tier_tools = TIER_TOOLS.get(tier, TIER_TOOLS["basic"])
    return {
        name: AgentDefinition(
            description=agent.description,
            prompt=agent.prompt,
            tools=tier_tools.get(name, []),
            model=agent.model,
        )
        for name, agent in AGENTS.items()
    }


# ── Multi-Turn Session ────────────────────────────────────
# Demonstrates session resume for conversational workflows.

async def multi_turn_session():
    """Example: multi-turn orchestration with session resume."""
    # Turn 1: Initial analysis
    result1 = await orchestrate(
        "Analyze the project structure and identify the main entry points."
    )
    session_id = result1.session_id
    print(f"\n[session] Turn 1 complete. Session: {session_id}\n")

    # Turn 2: Follow-up using session context
    if session_id:
        result2 = await orchestrate(
            "Based on what you found, which components have the most complexity?",
            resume_session=session_id,
        )
        print(f"\n[session] Turn 2 complete. Cost so far: "
              f"${result1.total_cost_usd + result2.total_cost_usd:.4f}")


# ── Main ──────────────────────────────────────────────────

async def main():
    """Run the orchestrator demo."""
    import sys

    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:])
    else:
        prompt = "Analyze this project's test coverage and identify gaps."

    # Single-turn orchestration
    result = await orchestrate(prompt)

    # Print summary
    print(f"\n{'=' * 60}")
    print(f"Session: {result.session_id}")
    print(f"Subagent calls: {result.subagent_calls}")
    print(f"Total cost: ${result.total_cost_usd:.4f}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    asyncio.run(main())
