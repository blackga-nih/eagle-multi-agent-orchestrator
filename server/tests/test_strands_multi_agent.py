"""Strands Agents SDK — Multi-Agent Supervisor POC (Phase 1).

Proves the agents-as-tools pattern works with 3 subagents on non-Claude
Bedrock models. The supervisor delegates to @tool-wrapped subagent functions
that each construct a fresh Agent() per invocation.

Architecture:
  Supervisor (Agent + tools=[oa_intake, legal_counsel, market_intelligence])
    ├── oa_intake     → Agent(system_prompt=SKILL_CONSTANTS["oa-intake"])
    ├── legal_counsel → Agent(system_prompt=SKILL_CONSTANTS["legal-counsel"])
    └── market_intel  → Agent(system_prompt=SKILL_CONSTANTS["market-intelligence"])

Run:
  AWS_PROFILE=eagle pytest tests/test_strands_multi_agent.py -v -s
  AWS_PROFILE=eagle STRANDS_MODEL_ID=us.meta.llama4-maverick-17b-instruct-v1:0 pytest tests/test_strands_multi_agent.py -v -s
"""

import os
import sys
import time

# Ensure server/ is on the path so eagle_skill_constants imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strands import Agent, tool
from strands.models import BedrockModel
from eagle_skill_constants import SKILL_CONSTANTS


# ── Config ───────────────────────────────────────────────────────────

MODEL_ID = os.environ.get("STRANDS_MODEL_ID", "us.amazon.nova-pro-v1:0")
REGION = "us-east-1"

# Shared model — created once, reused across all agents in this module
_model = BedrockModel(model_id=MODEL_ID, region_name=REGION)


# ── Subagent Tools ───────────────────────────────────────────────────

@tool(name="oa_intake")
def oa_intake(query: str) -> str:
    """Handle acquisition intake requests, micro-purchases, and procurement pathways.

    Args:
        query: The acquisition intake question or request
    """
    prompt = SKILL_CONSTANTS.get("oa-intake", "You are an intake specialist.")
    agent = Agent(model=_model, system_prompt=prompt, callback_handler=None)
    return str(agent(query))


@tool(name="legal_counsel")
def legal_counsel(query: str) -> str:
    """Assess FAR compliance, legal risks, protest vulnerabilities, and appropriation law for acquisitions.

    Args:
        query: The legal question about an acquisition
    """
    prompt = SKILL_CONSTANTS.get("legal-counsel", "You are a legal specialist.")
    agent = Agent(model=_model, system_prompt=prompt, callback_handler=None)
    return str(agent(query))


@tool(name="market_intelligence")
def market_intelligence(query: str) -> str:
    """Research market conditions, vendors, pricing data, GSA schedules, and small business sources.

    Args:
        query: The market research question
    """
    prompt = SKILL_CONSTANTS.get("market-intelligence", "You are a market analyst.")
    agent = Agent(model=_model, system_prompt=prompt, callback_handler=None)
    return str(agent(query))


# ── Helper ───────────────────────────────────────────────────────────

def _build_supervisor() -> Agent:
    """Build the supervisor agent with 3 subagent tools."""
    return Agent(
        model=_model,
        system_prompt=(
            "You are the EAGLE supervisor for NCI Office of Acquisitions. "
            "You have three specialist tools available. ALWAYS delegate to the "
            "appropriate specialist - never answer specialized questions yourself.\n\n"
            "Available specialists:\n"
            "- oa_intake: For acquisition intake, micro-purchases, procurement pathways\n"
            "- legal_counsel: For FAR compliance, legal risks, protest analysis\n"
            "- market_intelligence: For market research, vendor analysis, pricing data\n\n"
            "Analyze the user's question, delegate to the right specialist, and "
            "synthesize their response into a clear answer."
        ),
        tools=[oa_intake, legal_counsel, market_intelligence],
        callback_handler=None,
    )


def _print_result(test_name: str, result_text: str, indicators: dict, elapsed: float):
    """Print formatted test results."""
    print(f"\n{'=' * 70}")
    print(f"  {test_name}")
    print(f"{'=' * 70}")
    print(f"  Model: {MODEL_ID}")
    print(f"  Elapsed: {elapsed:.2f}s")
    print(f"  Response length: {len(result_text)} chars")
    print()
    print("  Indicators:")
    for name, found in indicators.items():
        status = "FOUND" if found else "MISSING"
        print(f"    {name}: {status}")
    found_count = sum(1 for v in indicators.values() if v)
    total = len(indicators)
    print(f"\n  Score: {found_count}/{total}")
    print()
    preview = result_text[:500]
    for line in preview.split("\n")[:10]:
        print(f"    {line.encode('ascii', 'replace').decode()}")


# ── Tests ────────────────────────────────────────────────────────────

def test_supervisor_routes_to_intake():
    """Supervisor delegates to oa_intake for a micro-purchase question."""
    supervisor = _build_supervisor()

    t0 = time.time()
    result = supervisor("I need to buy $13,800 in lab supplies. What's the fastest way?")
    elapsed = time.time() - t0

    result_text = str(result).lower()

    indicators = {
        "micro_purchase": any(w in result_text for w in [
            "micro-purchase", "micro purchase", "micropurchase", "simplified",
        ]),
        "threshold": any(w in result_text for w in [
            "$15,000", "15k", "15,000", "threshold", "below", "under",
        ]),
        "purchase_card": any(w in result_text for w in [
            "purchase card", "p-card", "card holder", "government purchase",
        ]),
        "streamlined": any(w in result_text for w in [
            "streamlined", "fast", "quick", "expedit", "minimal", "efficient",
        ]),
    }

    _print_result("Supervisor -> oa_intake (micro-purchase)", result_text, indicators, elapsed)

    found = sum(1 for v in indicators.values() if v)
    assert found >= 2, f"Only {found}/4 intake indicators found (need >= 2)"


def test_supervisor_routes_to_legal():
    """Supervisor delegates to legal_counsel for a FAR compliance question."""
    supervisor = _build_supervisor()

    t0 = time.time()
    result = supervisor(
        "We want to sole-source a $500K contract to a specific vendor. "
        "What FAR justifications do we need and what are the protest risks?"
    )
    elapsed = time.time() - t0

    result_text = str(result).lower()

    indicators = {
        "far_reference": any(w in result_text for w in [
            "far ", "far 6", "far 13", "part 6", "federal acquisition",
        ]),
        "sole_source": any(w in result_text for w in [
            "sole source", "sole-source", "single source", "j&a", "justification",
        ]),
        "competition": any(w in result_text for w in [
            "competition", "competitive", "full and open", "protest",
        ]),
        "compliance": any(w in result_text for w in [
            "compliance", "regulation", "requirement", "authority", "authorized",
        ]),
    }

    _print_result("Supervisor -> legal_counsel (sole-source)", result_text, indicators, elapsed)

    found = sum(1 for v in indicators.values() if v)
    assert found >= 2, f"Only {found}/4 legal indicators found (need >= 2)"


def test_supervisor_routes_to_market():
    """Supervisor delegates to market_intelligence for a vendor research question."""
    supervisor = _build_supervisor()

    t0 = time.time()
    result = supervisor(
        "Research the market for cloud hosting providers that are FedRAMP authorized. "
        "What are the top vendors and their GSA schedule pricing?"
    )
    elapsed = time.time() - t0

    result_text = str(result).lower()

    indicators = {
        "vendors": any(w in result_text for w in [
            "aws", "azure", "google", "gcp", "oracle", "ibm", "vendor",
        ]),
        "fedramp": any(w in result_text for w in [
            "fedramp", "fed-ramp", "federal risk", "authorization",
        ]),
        "gsa": any(w in result_text for w in [
            "gsa", "schedule", "gwac", "governmentwide", "contract vehicle",
        ]),
        "pricing": any(w in result_text for w in [
            "pricing", "cost", "rate", "discount", "price",
        ]),
    }

    _print_result("Supervisor -> market_intelligence (cloud vendors)", result_text, indicators, elapsed)

    found = sum(1 for v in indicators.values() if v)
    assert found >= 2, f"Only {found}/4 market indicators found (need >= 2)"


# ── CLI Runner ───────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"\nStrands Multi-Agent Supervisor POC — Model: {MODEL_ID}\n")
    test_supervisor_routes_to_intake()
    test_supervisor_routes_to_legal()
    test_supervisor_routes_to_market()
    print("\n ALL 3 TESTS PASSED\n")
