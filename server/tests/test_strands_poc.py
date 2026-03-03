"""Strands Agents SDK POC — UC-02 Micro-Purchase.

Mirrors Test 21 (test_21_uc02_micro_purchase) from the existing eval suite
but uses Strands Agent + BedrockModel instead of Claude Agent SDK query().

Proves:
  - Strands SDK works with Bedrock in our AWS account
  - Existing SKILL.md prompts are portable (zero changes to eagle-plugin/)
  - eagle_skill_constants.py loader is SDK-agnostic
  - No subprocess overhead — direct in-process boto3 converse call

Run:
  AWS_PROFILE=eagle pytest tests/test_strands_poc.py -v -s
  AWS_PROFILE=eagle python tests/test_strands_poc.py
"""

import os
import sys
import time

# Ensure server/ is on the path so eagle_skill_constants imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strands import Agent
from strands.models import BedrockModel
from eagle_skill_constants import SKILL_CONSTANTS


# ── Config ───────────────────────────────────────────────────────────

MODEL_ID = os.environ.get("STRANDS_MODEL_ID", "us.meta.llama4-maverick-17b-instruct-v1:0")
REGION = "us-east-1"


# ── Test ─────────────────────────────────────────────────────────────

def test_strands_uc02_micro_purchase():
    """UC-02: Micro-purchase fast path via Strands Agent.

    Same prompt, same indicators, same pass threshold (>= 3/5) as Test 21.
    """
    print("\n" + "=" * 70)
    print("STRANDS POC: UC-02 Micro-Purchase Workflow (<$15K Fast Path)")
    print("=" * 70)

    # 1. Load skill from existing eagle_skill_constants (SDK-agnostic)
    intake_content = SKILL_CONSTANTS.get("oa-intake")
    if not intake_content:
        print("  SKIP - oa-intake skill not found in SKILL_CONSTANTS")
        return

    print(f"  Skill loaded: oa-intake ({len(intake_content)} chars)")

    # 2. Build system prompt — identical tenant context to Test 21
    tenant_context = (
        "Tenant: nci-oa | User: cor-adams-001 | Tier: premium\n"
        "You are the OA Intake skill for the EAGLE Supervisor Agent.\n"
        "Handle micro-purchase requests efficiently with minimal questions.\n\n"
    )
    system_prompt = tenant_context + intake_content

    # 3. Construct Strands Agent with Bedrock
    model = BedrockModel(
        model_id=MODEL_ID,
        region_name=REGION,
    )
    agent = Agent(
        model=model,
        system_prompt=system_prompt,
        callback_handler=None,  # suppress stdout
    )

    # 4. Invoke synchronously — no subprocess, no async generator
    prompt = (
        "I have a quote for $13,800 from Fisher Scientific for lab supplies — "
        "centrifuge tubes, pipette tips, and reagents. Grant-funded, deliver to "
        "Building 37 Room 204. I want to use the purchase card. "
        "What's the fastest way to process this?"
    )

    print(f"  Prompt: {prompt[:80]}...")
    print(f"  Model: {MODEL_ID}")
    print()

    t0 = time.time()
    result = agent(prompt)
    elapsed = time.time() - t0

    # 5. Extract text
    result_text = str(result).lower()
    print(f"  Response length: {len(result_text)} chars")
    print(f"  Elapsed: {elapsed:.2f}s")
    print()

    # 6. Assert 5 indicators — identical keyword checks from Test 21
    indicators = {
        "micro_purchase": any(w in result_text for w in [
            "micro-purchase", "micro purchase", "micropurchase", "simplified",
        ]),
        "threshold": any(w in result_text for w in [
            "$15,000", "15k", "threshold", "below", "under",
        ]),
        "purchase_card": any(w in result_text for w in [
            "purchase card", "p-card", "card holder", "government purchase",
        ]),
        "streamlined": any(w in result_text for w in [
            "streamlined", "fast", "quick", "expedit", "minimal",
        ]),
        "far_reference": any(w in result_text for w in [
            "far 13", "part 13", "far part", "simplified acquisition",
        ]),
    }

    print("  UC-02 indicators:")
    for indicator, found in indicators.items():
        status = "FOUND" if found else "MISSING"
        print(f"    {indicator}: {status}")

    indicators_found = sum(1 for v in indicators.values() if v)
    passed = indicators_found >= 3

    print(f"\n  Indicators: {indicators_found}/5")
    print(f"  {'PASS' if passed else 'FAIL'} - Strands POC UC-02 Micro-Purchase")

    # Show snippet of response for debugging
    print(f"\n  Response preview:")
    preview = str(result)[:500]
    for line in preview.split("\n")[:10]:
        print(f"    {line.encode('ascii', 'replace').decode()}")

    assert passed, f"Only {indicators_found}/5 indicators found (need >= 3)"


# ── CLI Runner ───────────────────────────────────────────────────────

if __name__ == "__main__":
    test_strands_uc02_micro_purchase()
