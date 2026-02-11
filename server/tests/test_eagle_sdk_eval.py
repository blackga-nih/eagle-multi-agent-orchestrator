"""
EAGLE SDK Evaluation Suite

Tests the core patterns for the EAGLE multi-tenant architecture:
1-6.   SDK patterns: sessions, resume, context, traces, cost, subagents
7-15.  Skill validation: OA intake, legal, market, tech, public, doc gen, supervisor chain
16-20. AWS tool integration: S3 ops, DynamoDB CRUD, CloudWatch logs, document generation,
       CloudWatch E2E verification — direct execute_tool() calls with boto3 confirmation
21-27. UC workflow validation: micro-purchase, option exercise, contract modification,
       CO package review, contract close-out, shutdown notification, score consolidation
28.    SDK architecture: skill→subagent orchestration via AgentDefinition

SDK: claude-agent-sdk >= 0.1.29
Backend: AWS Bedrock (CLAUDE_CODE_USE_BEDROCK=1)
"""

import argparse
import asyncio
import json
import os
import shutil
import sys
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Any

# Add server/ to path so we can import app modules and eagle_skill_constants
_server_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, _server_dir)
sys.path.insert(0, os.path.join(_server_dir, "app"))
from agentic_service import execute_tool

from claude_agent_sdk import (
    query,
    ClaudeAgentOptions,
    AgentDefinition,
    tool,
    create_sdk_mcp_server,
)

try:
    from eval_aws_publisher import (
        publish_eval_metrics,
        archive_results_to_s3,
        archive_videos_to_s3,
    )
    _HAS_AWS_PUBLISHER = True
except ImportError:
    _HAS_AWS_PUBLISHER = False

# ============================================================
# CLI flags
# ============================================================

_parser = argparse.ArgumentParser(description="EAGLE SDK Evaluation Suite")
_parser.add_argument(
    "--model", default="haiku",
    help="Override model for ALL test invocations (default: haiku). "
         "Use 'haiku' to keep costs low.",
)
_parser.add_argument(
    "--async", dest="run_async", action="store_true",
    help="Run independent tests concurrently (tests 3-20 in parallel).",
)
_parser.add_argument(
    "--tests", default=None,
    help="Comma-separated test numbers to run (e.g. '1,2,7'). Default: all.",
)
_parser.add_argument(
    "--record-video", dest="record_video", action="store_true",
    help="Record browser video of eval-page UC diagrams for applicable tests. "
         "Requires: pip install playwright && playwright install chromium",
)
_parser.add_argument(
    "--headed", action="store_true",
    help="Show browser window during video recording (default: headless).",
)
_parser.add_argument(
    "--base-url", default="http://localhost:3000",
    help="Frontend base URL for video recording (default: http://localhost:3000).",
)
_parser.add_argument(
    "--auth-email", default=None,
    help="Login email for video recording (or set EAGLE_TEST_EMAIL env var).",
)
_parser.add_argument(
    "--auth-password", default=None,
    help="Login password for video recording (or set EAGLE_TEST_PASSWORD env var).",
)
_args = _parser.parse_args()

# Global model override — every test reads from here
MODEL: str = _args.model


# ============================================================
# Custom Tools - simulating tier-gated MCP tools
# ============================================================

@dataclass
class ProductLookupInput:
    product_name: str

@tool("lookup_product", "Look up product details by name", ProductLookupInput)
async def lookup_product_tool(input: ProductLookupInput) -> dict[str, Any]:
    products = {
        "widget pro": {"id": "WP-001", "name": "Widget Pro", "price": 29.99, "stock": 150},
        "gadget lite": {"id": "GL-002", "name": "Gadget Lite", "price": 14.99, "stock": 500},
        "sensor max": {"id": "SM-003", "name": "Sensor Max", "price": 49.99, "stock": 75},
    }
    key = input.product_name.lower()
    result = products.get(key, {"error": f"Product '{input.product_name}' not found"})
    return {"content": [{"type": "text", "text": json.dumps(result)}]}


# ============================================================
# Tier configuration (mirrors subscription_service.py)
# ============================================================

TIER_TOOLS = {
    "basic": ["Read", "Glob"],
    "advanced": ["Read", "Glob", "Grep", "Task"],
    "premium": ["Read", "Glob", "Grep", "Task",
                 "mcp__inventory__lookup_product"],
}

TIER_BUDGETS = {
    "basic": 0.05,
    "advanced": 0.15,
    "premium": 0.50,
}


# ============================================================
# Trace collector
# ============================================================

class TraceCollector:
    """Collects and categorizes SDK message traces."""

    def __init__(self):
        self.messages = []
        self.text_blocks = []
        self.thinking_blocks = []
        self.tool_use_blocks = []
        self.result_messages = []
        self.system_messages = []
        self.session_id = None
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cost_usd = 0.0
        self.log_lines = []  # Raw log lines for trace display

    def _log(self, msg):
        """Print and capture a log line."""
        print(msg)
        self.log_lines.append(msg)

    def process(self, message, indent: int = 0):
        prefix = "  " * indent
        msg_type = type(message).__name__
        self.messages.append({"type": msg_type, "message": message})

        # SystemMessage: capture session_id from data dict
        if msg_type == "SystemMessage":
            if hasattr(message, "data") and isinstance(message.data, dict):
                sid = message.data.get("session_id")
                if sid:
                    self.session_id = sid
                    self._log(f"{prefix}  [SystemMessage/init] session_id={sid}")
            self.system_messages.append(message)
            return

        # AssistantMessage / UserMessage: process content blocks
        if hasattr(message, "content") and message.content is not None:
            for block in message.content:
                # SDK blocks use class names, not a 'type' attribute
                block_class = type(block).__name__

                if block_class == "TextBlock":
                    text = getattr(block, "text", "")
                    if text.strip():
                        self.text_blocks.append(text)
                        self._log(f"{prefix}  [{msg_type}/TextBlock] {text[:200]}")

                elif block_class == "ThinkingBlock":
                    thinking = getattr(block, "thinking", getattr(block, "text", ""))
                    self.thinking_blocks.append(thinking)
                    self._log(f"{prefix}  [{msg_type}/ThinkingBlock] {thinking[:150]}...")

                elif block_class == "ToolUseBlock":
                    name = getattr(block, "name", "?")
                    tool_id = getattr(block, "id", "?")
                    inp = getattr(block, "input", {})
                    self.tool_use_blocks.append({
                        "tool": name, "id": tool_id, "input": inp
                    })
                    if name == "Task":
                        subagent = inp.get("subagent_type", inp.get("description", "?"))
                        self._log(f"{prefix}  [{msg_type}/ToolUseBlock] SUBAGENT -> {subagent}")
                    else:
                        self._log(f"{prefix}  [{msg_type}/ToolUseBlock] {name}({json.dumps(inp)[:120]})")

                elif block_class == "ToolResultBlock":
                    tool_id = getattr(block, "tool_use_id", "?")
                    content = getattr(block, "content", "")
                    content_preview = str(content)[:100] if content else ""
                    self._log(f"{prefix}  [{msg_type}/ToolResultBlock] id={tool_id} {content_preview}")

        # ResultMessage: usage is a dict, session_id and total_cost_usd are direct attrs
        if msg_type == "ResultMessage":
            # Capture session_id from ResultMessage too
            if hasattr(message, "session_id") and message.session_id:
                self.session_id = message.session_id

            # Usage is a dict, not an object
            if hasattr(message, "usage") and message.usage is not None:
                usage = message.usage
                if isinstance(usage, dict):
                    input_t = usage.get("input_tokens", 0) or 0
                    output_t = usage.get("output_tokens", 0) or 0
                    cache_create = usage.get("cache_creation_input_tokens", 0) or 0
                    cache_read = usage.get("cache_read_input_tokens", 0) or 0
                else:
                    input_t = getattr(usage, "input_tokens", 0) or 0
                    output_t = getattr(usage, "output_tokens", 0) or 0
                    cache_create = getattr(usage, "cache_creation_input_tokens", 0) or 0
                    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0

                # Total billed tokens include cache creation + direct
                total_in = input_t + cache_create + cache_read
                self.total_input_tokens += total_in
                self.total_output_tokens += output_t
                self.result_messages.append({
                    "input_tokens": input_t,
                    "output_tokens": output_t,
                    "cache_creation_input_tokens": cache_create,
                    "cache_read_input_tokens": cache_read,
                    "total_input_effective": total_in,
                })
                self._log(f"{prefix}  [{msg_type}/usage] {input_t}+{cache_create}cache_create+{cache_read}cache_read in / {output_t} out")

            # Total cost USD
            total_cost = getattr(message, "total_cost_usd", None)
            if total_cost is not None:
                self.total_cost_usd = getattr(self, "total_cost_usd", 0) + total_cost
                self._log(f"{prefix}  [{msg_type}/cost] ${total_cost:.6f}")

            # Result text
            if hasattr(message, "result") and message.result:
                text = message.result
                self._log(f"{prefix}  [{msg_type}/result] {text[:300]}")

        # Subagent context
        if hasattr(message, "parent_tool_use_id") and message.parent_tool_use_id:
            parent = message.parent_tool_use_id
            is_bedrock = parent.startswith("toolu_bdrk_")
            self._log(f"{prefix}  (subagent context, parent={parent}, bedrock={is_bedrock})")

    def summary(self):
        return {
            "total_messages": len(self.messages),
            "text_blocks": len(self.text_blocks),
            "thinking_blocks": len(self.thinking_blocks),
            "tool_use_blocks": len(self.tool_use_blocks),
            "result_messages": len(self.result_messages),
            "system_messages": len(self.system_messages),
            "session_id": self.session_id,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_cost_usd": self.total_cost_usd,
        }


# ============================================================
# Test 1: Session creation + tenant context injection
# ============================================================

async def test_1_session_creation():
    """Create a new session with tenant context in system_prompt."""
    print("\n" + "=" * 70)
    print("TEST 1: Session Creation + Tenant Context Injection")
    print("=" * 70)

    tenant_id = "acme-corp"
    user_id = "user-001"
    subscription_tier = "premium"

    system_prompt = (
        f"You are an AI assistant for tenant '{tenant_id}'. "
        f"Subscription tier: {subscription_tier}. "
        f"Current user: {user_id}. "
        f"Always acknowledge the tenant and tier when greeting. "
        f"Respond concisely."
    )

    options = ClaudeAgentOptions(
        model=MODEL,
        system_prompt=system_prompt,
        allowed_tools=TIER_TOOLS[subscription_tier],
        permission_mode="bypassPermissions",
        max_turns=3,
        max_budget_usd=TIER_BUDGETS[subscription_tier],
        cwd=os.path.dirname(os.path.abspath(__file__)),
        env={
            "CLAUDE_CODE_USE_BEDROCK": "1",
            "AWS_REGION": "us-east-1",
        },
    )

    print(f"  Tenant: {tenant_id} | User: {user_id} | Tier: {subscription_tier}")
    print(f"  Budget: ${TIER_BUDGETS[subscription_tier]}")
    print(f"  Tools: {TIER_TOOLS[subscription_tier]}")
    print()

    collector = TraceCollector()

    async for message in query(
        prompt="Hello! What tenant am I from and what is my subscription tier?",
        options=options,
    ):
        collector.process(message, indent=2)

    print()
    summary = collector.summary()
    print(f"  --- Results ---")
    print(f"  Session ID: {summary['session_id']}")
    print(f"  Messages: {summary['total_messages']}")
    print(f"  Text blocks: {summary['text_blocks']}")
    print(f"  Tokens: {summary['total_input_tokens']} in / {summary['total_output_tokens']} out")
    print(f"  Cost: ${summary['total_cost_usd']:.6f}")

    # Check all text sources: text_blocks (AssistantMessage) + result (ResultMessage)
    all_text_sources = list(collector.text_blocks)
    for msg_entry in collector.messages:
        msg = msg_entry["message"]
        if hasattr(msg, "result") and msg.result:
            all_text_sources.append(msg.result)
    all_text = " ".join(all_text_sources).lower()

    tenant_mentioned = "acme" in all_text or tenant_id in all_text
    tier_mentioned = subscription_tier in all_text

    print(f"  Tenant recognized in response: {tenant_mentioned}")
    print(f"  Tier recognized in response: {tier_mentioned}")

    passed = summary["session_id"] is not None and summary["total_messages"] > 0
    print(f"\n  {'PASS' if passed else 'FAIL'} - Session created with tenant context")
    return passed, summary["session_id"]


# ============================================================
# Test 2: Session resume (stateless multi-turn)
# ============================================================

async def test_2_session_resume(session_id: str):
    """Resume a session using query(resume=session_id) for multi-turn.

    KEY DISCOVERY: resume restores conversation history but NOT system_prompt.
    system_prompt must be provided on every query - this is correct for
    multi-tenant because tenant context should always be explicitly set.
    """
    print("\n" + "=" * 70)
    print("TEST 2: Session Resume (Stateless Multi-Turn)")
    print("=" * 70)

    if not session_id:
        print("  SKIP - No session_id from Test 1")
        return None

    print(f"  Resuming session: {session_id}")
    print(f"  Note: system_prompt MUST be re-provided (not carried over)")
    print()

    # IMPORTANT: system_prompt is NOT preserved across resume.
    # Always include tenant context in system_prompt on every query.
    tenant_id = "acme-corp"
    user_id = "user-001"
    subscription_tier = "premium"

    options = ClaudeAgentOptions(
        model=MODEL,
        resume=session_id,
        system_prompt=(
            f"You are an AI assistant for tenant '{tenant_id}'. "
            f"Subscription tier: {subscription_tier}. "
            f"Current user: {user_id}. "
            f"Always acknowledge the tenant and tier when asked. "
            f"Respond concisely."
        ),
        allowed_tools=["Read", "Glob"],
        permission_mode="bypassPermissions",
        max_turns=3,
        max_budget_usd=0.10,
        cwd=os.path.dirname(os.path.abspath(__file__)),
        env={
            "CLAUDE_CODE_USE_BEDROCK": "1",
            "AWS_REGION": "us-east-1",
        },
    )

    collector = TraceCollector()

    async for message in query(
        prompt=(
            "What was my first question to you in this conversation? "
            "Also, what tenant and tier are in your system instructions?"
        ),
        options=options,
    ):
        collector.process(message, indent=2)

    print()
    summary = collector.summary()
    print(f"  --- Results ---")
    print(f"  Session ID: {summary['session_id'] or session_id}")
    print(f"  Messages: {summary['total_messages']}")
    print(f"  Tokens: {summary['total_input_tokens']} in / {summary['total_output_tokens']} out")
    print(f"  Cost: ${summary['total_cost_usd']:.6f}")

    # Verify session was resumed: same session_id returned
    same_session = (summary['session_id'] or "") == session_id
    print(f"  Same session ID: {same_session}")

    # Check all text sources for context restoration
    all_text_sources = list(collector.text_blocks)
    for msg_entry in collector.messages:
        msg = msg_entry["message"]
        if hasattr(msg, "result") and msg.result:
            all_text_sources.append(msg.result)
    all_text = " ".join(all_text_sources).lower()

    # Check if tenant context from system_prompt was preserved
    tenant_found = "acme" in all_text
    tier_found = "premium" in all_text
    # Also check if the model at least references the previous conversation
    conversation_aware = (
        "previous" in all_text or "earlier" in all_text
        or "tenant" in all_text or "greeting" in all_text
        or tenant_found or tier_found
    )

    print(f"  Tenant found in response: {tenant_found}")
    print(f"  Tier found in response: {tier_found}")
    print(f"  Conversation-aware: {conversation_aware}")

    # Session resume passes if: same session ID + model has context
    passed = same_session and summary["total_messages"] > 0 and conversation_aware
    print(f"\n  {'PASS' if passed else 'FAIL'} - Session resumed with context preserved")
    return passed


# ============================================================
# Test 3: Trace observation (ThinkingBlock, ToolUseBlock)
# ============================================================

async def test_3_trace_observation():
    """Observe SDK trace types that the frontend will render."""
    print("\n" + "=" * 70)
    print("TEST 3: Trace Observation (Frontend Event Types)")
    print("=" * 70)

    options = ClaudeAgentOptions(
        model=MODEL,
        system_prompt=(
            "You are a file analysis assistant. "
            "When asked about files, use the Glob tool to find them "
            "and Read tool to examine them. Be concise."
        ),
        allowed_tools=["Read", "Glob"],
        permission_mode="bypassPermissions",
        max_turns=5,
        max_budget_usd=0.15,
        cwd=os.path.dirname(os.path.abspath(__file__)),
        env={
            "CLAUDE_CODE_USE_BEDROCK": "1",
            "AWS_REGION": "us-east-1",
        },
    )

    print(f"  Tools: Read, Glob (should trigger ToolUseBlock traces)")
    print()

    collector = TraceCollector()

    async for message in query(
        prompt="How many Python files are in this directory? List them.",
        options=options,
    ):
        collector.process(message, indent=2)

    print()
    summary = collector.summary()
    print(f"  --- Trace Analysis ---")
    print(f"  Messages: {summary['total_messages']}")
    print(f"  Text blocks: {summary['text_blocks']} (→ orchestrator_chat events)")
    print(f"  Thinking blocks: {summary['thinking_blocks']} (→ thinking_block events)")
    print(f"  Tool use blocks: {summary['tool_use_blocks']} (→ tool_use_block events)")
    print(f"  Result messages: {summary['result_messages']} (→ orchestrator_updated events)")
    print(f"  Tokens: {summary['total_input_tokens']} in / {summary['total_output_tokens']} out")
    print(f"  Cost: ${summary['total_cost_usd']:.6f}")

    # Tool calls observed
    for tu in collector.tool_use_blocks:
        tool_id_preview = tu['id'][:30] + "..." if len(tu['id']) > 30 else tu['id']
        print(f"    Tool: {tu['tool']} (id: {tool_id_preview})")

    # Message type breakdown
    msg_types = {}
    for m in collector.messages:
        mt = m["type"]
        msg_types[mt] = msg_types.get(mt, 0) + 1
    print(f"  Message types: {msg_types}")

    # Verify we got tool_use traces (the key thing for frontend rendering)
    has_tool_traces = summary["tool_use_blocks"] > 0
    # Text can come from TextBlock or ResultMessage.result
    has_text = summary["text_blocks"] > 0 or any(
        hasattr(m["message"], "result") and m["message"].result
        for m in collector.messages
    )
    has_usage = summary["total_input_tokens"] > 0

    print(f"\n  Tool traces for frontend: {has_tool_traces}")
    print(f"  Text content for chat: {has_text}")
    print(f"  Usage metrics for cost ticker: {has_usage}")

    passed = has_tool_traces and has_text and has_usage
    print(f"\n  {'PASS' if passed else 'FAIL'} - Trace types observed for frontend rendering")
    return passed


# ============================================================
# Test 4: Subagent orchestration with tenant scope
# ============================================================

async def test_4_subagent_orchestration():
    """Test subagents (the most valuable SDK feature for multi-tenant)."""
    print("\n" + "=" * 70)
    print("TEST 4: Subagent Orchestration (Tenant-Scoped)")
    print("=" * 70)

    tenant_id = "globex-inc"
    subscription_tier = "premium"

    options = ClaudeAgentOptions(
        model=MODEL,
        system_prompt=(
            f"You are an AI assistant for tenant '{tenant_id}' "
            f"(tier: {subscription_tier}). "
            f"You have specialized subagents. Use them when appropriate."
        ),
        allowed_tools=["Read", "Glob", "Grep", "Task"],
        permission_mode="bypassPermissions",
        max_turns=10,
        max_budget_usd=TIER_BUDGETS[subscription_tier],
        cwd=os.path.dirname(os.path.abspath(__file__)),
        env={
            "CLAUDE_CODE_USE_BEDROCK": "1",
            "AWS_REGION": "us-east-1",
        },
        agents={
            "file-analyzer": AgentDefinition(
                description="Analyzes file structure and counts files. Use for file system questions.",
                prompt=(
                    "You analyze directory structures. Use Glob to find files "
                    "and report counts and patterns. Be concise."
                ),
                tools=["Glob"],
                model=MODEL,
            ),
            "code-reader": AgentDefinition(
                description="Reads and summarizes code files. Use for understanding code.",
                prompt=(
                    "You read code files and summarize them in 2-3 sentences. "
                    "Focus on purpose, key functions, and dependencies."
                ),
                tools=["Read"],
                model=MODEL,
            ),
        },
    )

    print(f"  Tenant: {tenant_id} | Tier: {subscription_tier}")
    print(f"  Subagents: file-analyzer, code-reader")
    print()

    collector = TraceCollector()

    async for message in query(
        prompt=(
            "Do two things:\n"
            "1. Use the file-analyzer to count .py files in this directory\n"
            "2. Use the code-reader to summarize what config.py does\n"
            "Report both results."
        ),
        options=options,
    ):
        collector.process(message, indent=2)

    print()
    summary = collector.summary()
    print(f"  --- Trace Analysis ---")
    print(f"  Messages: {summary['total_messages']}")
    print(f"  Tool use blocks: {summary['tool_use_blocks']}")
    print(f"  Tokens: {summary['total_input_tokens']} in / {summary['total_output_tokens']} out")

    # Check for subagent invocations
    subagent_calls = [t for t in collector.tool_use_blocks if t["tool"] == "Task"]
    other_calls = [t for t in collector.tool_use_blocks if t["tool"] != "Task"]

    print(f"  Subagent invocations: {len(subagent_calls)}")
    for sc in subagent_calls:
        agent_type = sc["input"].get("subagent_type", sc["input"].get("description", "?"))
        print(f"    -> {agent_type}")
    print(f"  Tool calls within subagents: {len(other_calls)}")
    for oc in other_calls:
        print(f"    -> {oc['tool']}")

    # Check for Bedrock backend confirmation
    bedrock_confirmed = False
    for tu in collector.tool_use_blocks:
        if tu["id"].startswith("toolu_bdrk_"):
            bedrock_confirmed = True
            break

    print(f"  Bedrock backend (toolu_bdrk_ prefix): {bedrock_confirmed}")

    passed = len(subagent_calls) > 0 or summary["total_messages"] > 2
    print(f"\n  {'PASS' if passed else 'FAIL'} - Subagent orchestration with tenant scope")
    return passed


# ============================================================
# Test 5: Cost tracking and tier budget enforcement
# ============================================================

async def test_5_cost_tracking():
    """Track cost/tokens from ResultMessage - for the cost ticker UI."""
    print("\n" + "=" * 70)
    print("TEST 5: Cost Tracking (ResultMessage.usage)")
    print("=" * 70)

    # Simulate tracking across multiple queries for a tenant
    tenant_id = "acme-corp"
    subscription_tier = "basic"

    print(f"  Tenant: {tenant_id} | Tier: {subscription_tier}")
    print(f"  Budget limit: ${TIER_BUDGETS[subscription_tier]}")
    print()

    total_cost_record = {
        "tenant_id": tenant_id,
        "subscription_tier": subscription_tier,
        "queries": 0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "sdk_total_cost_usd": 0.0,
    }

    # Run 2 queries to accumulate cost tracking
    for i, prompt in enumerate([
        "What is 2 + 2? Answer in one word.",
        "What is the capital of France? One word answer.",
    ], 1):
        print(f"  --- Query {i} ---")

        options = ClaudeAgentOptions(
            model=MODEL,
            system_prompt=f"You are a concise assistant for tenant '{tenant_id}'. One-line answers only.",
            allowed_tools=TIER_TOOLS[subscription_tier],
            permission_mode="bypassPermissions",
            max_turns=2,
            max_budget_usd=TIER_BUDGETS[subscription_tier],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            env={
                "CLAUDE_CODE_USE_BEDROCK": "1",
                "AWS_REGION": "us-east-1",
            },
        )

        collector = TraceCollector()
        async for message in query(prompt=prompt, options=options):
            collector.process(message, indent=3)

        summary = collector.summary()
        total_cost_record["queries"] += 1
        total_cost_record["total_input_tokens"] += summary["total_input_tokens"]
        total_cost_record["total_output_tokens"] += summary["total_output_tokens"]
        total_cost_record["sdk_total_cost_usd"] += summary["total_cost_usd"]

        print(f"    Tokens: {summary['total_input_tokens']} in / {summary['total_output_tokens']} out")
        print(f"    SDK cost: ${summary['total_cost_usd']:.6f}")
        print()

    print(f"  --- Cost Attribution Record ---")
    print(f"  {json.dumps(total_cost_record, indent=4)}")

    within_budget = total_cost_record["sdk_total_cost_usd"] <= TIER_BUDGETS[subscription_tier]
    has_usage = total_cost_record["total_input_tokens"] > 0
    has_cost = total_cost_record["sdk_total_cost_usd"] > 0

    print(f"\n  Within tier budget: {within_budget}")
    print(f"  Usage tracked: {has_usage}")
    print(f"  Cost tracked: {has_cost}")

    passed = has_usage or has_cost
    print(f"\n  {'PASS' if passed else 'FAIL'} - Cost tracking from ResultMessage")
    return passed


# ============================================================
# Test 6: Custom tools via MCP (premium tier only)
# ============================================================

async def test_6_tier_gated_tools():
    """Test custom MCP tools gated by subscription tier."""
    print("\n" + "=" * 70)
    print("TEST 6: Tier-Gated Custom Tools (MCP)")
    print("=" * 70)

    mcp_server = create_sdk_mcp_server(
        "inventory",
        tools=[lookup_product_tool],
    )

    # Premium tier gets MCP tools
    options = ClaudeAgentOptions(
        model=MODEL,
        system_prompt=(
            "You are an inventory assistant for a premium-tier tenant. "
            "Use lookup_product to find products. Be concise."
        ),
        allowed_tools=["mcp__inventory__lookup_product"],
        mcp_servers={"inventory": mcp_server},
        permission_mode="bypassPermissions",
        max_turns=5,
        max_budget_usd=0.10,
        env={
            "CLAUDE_CODE_USE_BEDROCK": "1",
            "AWS_REGION": "us-east-1",
        },
    )

    print(f"  Tier: premium (has MCP tool access)")
    print(f"  Tools: lookup_product via MCP")
    print()

    collector = TraceCollector()

    mcp_race_condition = False
    try:
        async for message in query(
            prompt="Look up the product called Widget Pro.",
            options=options,
        ):
            collector.process(message, indent=2)
    except ExceptionGroup as eg:
        # Handle MCP server cleanup race condition (Windows)
        cli_errors = [e for e in eg.exceptions if "CLIConnection" in type(e).__name__]
        if cli_errors:
            print(f"    [Note] MCP server cleanup race condition (expected on Windows)")
            mcp_race_condition = True
        else:
            raise
    except Exception as e:
        if "CLIConnection" in type(e).__name__ or "MCP" in str(e) or "ExceptionGroup" in type(e).__name__:
            print(f"    [Note] MCP cleanup: {type(e).__name__}: {e}")
            mcp_race_condition = True
        else:
            raise

    print()
    summary = collector.summary()
    print(f"  --- Results ---")
    print(f"  Messages: {summary['total_messages']}")
    print(f"  Tool calls: {summary['tool_use_blocks']}")
    print(f"  Tokens: {summary['total_input_tokens']} in / {summary['total_output_tokens']} out")

    # Check if the MCP tool was actually called
    mcp_calls = [t for t in collector.tool_use_blocks
                 if "lookup_product" in t["tool"]]
    print(f"  MCP tool calls: {len(mcp_calls)}")

    if mcp_race_condition and summary["total_messages"] == 0:
        print(f"\n  SKIP - MCP server race condition (Windows); no messages collected")
        return None

    passed = len(mcp_calls) > 0 or summary["total_messages"] > 0
    print(f"\n  {'PASS' if passed else 'FAIL'} - Tier-gated MCP tools")
    return passed


# ============================================================
# Test 7: Skill loading via system_prompt
# ============================================================

from eagle_skill_constants import SKILL_CONSTANTS, OA_INTAKE_SKILL


def load_skill_or_prompt(skill_name: str = None, prompt_file: str = None) -> tuple:
    """Load a skill or legacy agent prompt from embedded constants.

    Args:
        skill_name: Name of skill (e.g., "oa-intake", "document-generator")
        prompt_file: Name of legacy prompt file (e.g., "02-legal.txt")

    Returns:
        (content, source_key) tuple, or (None, None) if not found
    """
    key = skill_name or prompt_file
    if key and key in SKILL_CONSTANTS:
        return SKILL_CONSTANTS[key], f"test_skill_constants[{key}]"
    return None, None


def load_skill_file() -> tuple:
    """Load the OA Intake skill markdown as a system prompt (backward compat)."""
    return load_skill_or_prompt(skill_name="oa-intake")


async def test_7_skill_loading():
    """Test loading a skill file and injecting it as system_prompt."""
    print("\n" + "=" * 70)
    print("TEST 7: Skill Loading (OA Intake Skill → system_prompt)")
    print("=" * 70)

    skill_content, skill_path = load_skill_file()
    if not skill_content:
        print(f"  SKIP - Skill constant not found")
        return None

    print(f"  Skill loaded: {skill_path}")
    print(f"  Skill size: {len(skill_content)} chars")

    # Inject skill as system_prompt - this is how the orchestrator loads skills
    tenant_context = (
        "Tenant: nci-oa | User: intake-officer-01 | Tier: premium\n"
        "You are operating as the OA Intake Agent for this tenant.\n\n"
    )

    options = ClaudeAgentOptions(
        model=MODEL,
        system_prompt=tenant_context + skill_content,
        allowed_tools=[],
        permission_mode="bypassPermissions",
        max_turns=3,
        max_budget_usd=0.15,
        cwd=os.path.dirname(os.path.abspath(__file__)),
        env={
            "CLAUDE_CODE_USE_BEDROCK": "1",
            "AWS_REGION": "us-east-1",
        },
    )

    print(f"  System prompt: tenant_context + skill ({len(tenant_context) + len(skill_content)} chars)")
    print()

    collector = TraceCollector()

    async for message in query(
        prompt="Hi, I need to buy a new microscope. Not sure about the price. Need it in 2 months.",
        options=options,
    ):
        collector.process(message, indent=2)

    print()
    summary = collector.summary()
    print(f"  --- Results ---")
    print(f"  Messages: {summary['total_messages']}")
    print(f"  Tokens: {summary['total_input_tokens']} in / {summary['total_output_tokens']} out")
    print(f"  Cost: ${summary['total_cost_usd']:.6f}")

    # Check that the skill knowledge is reflected in the response
    all_text = " ".join(collector.text_blocks).lower()
    for msg_entry in collector.messages:
        msg = msg_entry["message"]
        if hasattr(msg, "result") and msg.result:
            all_text += " " + msg.result.lower()

    # The skill should produce acquisition-specific responses:
    # - asks clarifying questions (Phase 2)
    # - mentions cost ranges
    # - follows the "Trish" philosophy
    skill_indicators = {
        "clarifying_questions": any(w in all_text for w in ["manufacturer", "model", "new or", "refurbished", "budget", "funding"]),
        "cost_awareness": any(w in all_text for w in ["$", "cost", "price", "range", "estimate", "value"]),
        "acquisition_knowledge": any(w in all_text for w in ["acquisition", "procurement", "purchase", "sow", "micro", "simplified"]),
        "follow_up_pattern": "?" in all_text,  # Should ask follow-up questions
    }

    print(f"  Skill indicators in response:")
    for indicator, found in skill_indicators.items():
        print(f"    {indicator}: {found}")

    # Pass if skill knowledge is evident (at least 2 of 4 indicators)
    indicators_found = sum(1 for v in skill_indicators.values() if v)
    passed = indicators_found >= 2 and summary["total_messages"] > 0
    print(f"\n  Skill indicators: {indicators_found}/4")
    print(f"  {'PASS' if passed else 'FAIL'} - Skill loaded and applied via system_prompt")
    return passed


# ============================================================
# Test 8: Subagent tool use tracking (deep trace inspection)
# ============================================================

async def test_8_subagent_tool_tracking():
    """Track which tools each subagent uses - verify parent_tool_use_id."""
    print("\n" + "=" * 70)
    print("TEST 8: Subagent Tool Use Tracking (Deep Trace)")
    print("=" * 70)

    options = ClaudeAgentOptions(
        model=MODEL,
        system_prompt=(
            "You are a code analysis assistant with specialized subagents. "
            "ALWAYS delegate file tasks to the appropriate subagent."
        ),
        allowed_tools=["Read", "Glob", "Grep", "Task"],
        permission_mode="bypassPermissions",
        max_turns=12,
        max_budget_usd=0.30,
        cwd=os.path.dirname(os.path.abspath(__file__)),
        env={
            "CLAUDE_CODE_USE_BEDROCK": "1",
            "AWS_REGION": "us-east-1",
        },
        agents={
            "file-scanner": AgentDefinition(
                description="Scans for files matching patterns. Use for finding files.",
                prompt=(
                    "You find files using Glob. "
                    "Return filenames and count. Be concise."
                ),
                tools=["Glob"],
                model=MODEL,
            ),
            "code-inspector": AgentDefinition(
                description="Reads and inspects code files. Use for understanding code content.",
                prompt=(
                    "You read code files with Read and search for patterns with Grep. "
                    "Report what you find concisely."
                ),
                tools=["Read", "Grep"],
                model=MODEL,
            ),
        },
    )

    print(f"  Subagents:")
    print(f"    file-scanner: tools=[Glob]")
    print(f"    code-inspector: tools=[Read, Grep]")
    print()

    # Detailed trace collector - tracks parent_tool_use_id
    subagent_traces = {}  # parent_tool_use_id -> list of tool calls
    all_tool_calls = []
    all_messages = []

    async for message in query(
        prompt=(
            "Do these three things using your subagents:\n"
            "1. Use file-scanner to find all .py files in the root directory\n"
            "2. Use code-inspector to read config.py and tell me the port number\n"
            "Report both results."
        ),
        options=options,
    ):
        msg_type = type(message).__name__
        all_messages.append(message)

        # Track parent_tool_use_id for tool calls inside subagents
        parent_id = getattr(message, "parent_tool_use_id", None)

        if hasattr(message, "content") and message.content is not None:
            for block in message.content:
                block_class = type(block).__name__

                if block_class == "ToolUseBlock":
                    name = getattr(block, "name", "?")
                    tool_id = getattr(block, "id", "?")
                    inp = getattr(block, "input", {})

                    call_record = {
                        "tool": name,
                        "id": tool_id,
                        "input": inp,
                        "parent_tool_use_id": parent_id,
                        "msg_type": msg_type,
                    }
                    all_tool_calls.append(call_record)

                    # Group by parent
                    if parent_id:
                        if parent_id not in subagent_traces:
                            subagent_traces[parent_id] = {
                                "agent_type": None,
                                "tool_calls": [],
                            }
                        subagent_traces[parent_id]["tool_calls"].append(call_record)

                    if name == "Task":
                        agent_type = inp.get("subagent_type", inp.get("description", "?"))
                        print(f"    [SUBAGENT] {agent_type} (id: {tool_id[:25]}...)")
                        # Link subagent type to its tool_use_id for children
                        if tool_id not in subagent_traces:
                            subagent_traces[tool_id] = {
                                "agent_type": agent_type,
                                "tool_calls": [],
                            }
                        else:
                            subagent_traces[tool_id]["agent_type"] = agent_type
                    else:
                        parent_label = f" (inside {parent_id[:15]}...)" if parent_id else ""
                        print(f"    [TOOL] {name}{parent_label}")

        if msg_type == "ResultMessage" and hasattr(message, "result"):
            print(f"    [RESULT] {message.result[:200]}")

    print()
    print(f"  --- Subagent Tool Tracking ---")
    print(f"  Total tool calls: {len(all_tool_calls)}")
    print(f"  Total messages: {len(all_messages)}")

    # Subagent-spawned tool calls (Task)
    task_calls = [c for c in all_tool_calls if c["tool"] == "Task"]
    print(f"  Subagent invocations (Task): {len(task_calls)}")

    # Tools called inside subagent contexts
    tools_with_parent = [c for c in all_tool_calls if c["parent_tool_use_id"] and c["tool"] != "Task"]
    tools_without_parent = [c for c in all_tool_calls if not c["parent_tool_use_id"] and c["tool"] != "Task"]
    print(f"  Tools inside subagents (has parent_tool_use_id): {len(tools_with_parent)}")
    print(f"  Tools at top level (no parent): {len(tools_without_parent)}")

    # Per-subagent breakdown
    print(f"\n  Subagent contexts: {len(subagent_traces)}")
    for parent_id, trace_data in subagent_traces.items():
        agent = trace_data["agent_type"] or "unknown"
        tools = trace_data["tool_calls"]
        tool_names = [t["tool"] for t in tools]
        is_bedrock = parent_id.startswith("toolu_bdrk_")
        print(f"    [{agent}] parent={parent_id[:25]}... bedrock={is_bedrock}")
        print(f"      Tools used: {tool_names}")

    # Validate: subagents should use their designated tools
    passed = len(task_calls) > 0 and len(all_tool_calls) > len(task_calls)
    print(f"\n  {'PASS' if passed else 'FAIL'} - Subagent tool use tracked with parent context")
    return passed


# ============================================================
# Test 9: OA Intake Workflow (CT Scanner Acquisition)
# ============================================================

async def test_9_oa_intake_workflow():
    """
    Run through the OA Intake workflow from the CT scanner transcript.
    Tests multi-turn conversation with skill-loaded system_prompt.
    Validates that the agent follows the skill's 5-phase workflow.
    """
    print("\n" + "=" * 70)
    print("TEST 9: OA Intake Workflow (CT Scanner Acquisition)")
    print("=" * 70)

    skill_content, skill_path = load_skill_file()
    if not skill_content:
        print(f"  SKIP - Skill file not found")
        return None

    print(f"  Skill: {skill_path}")
    print(f"  Workflow: CT Scanner intake (from transcript)")
    print()

    # Phase 1: Initial intake - user provides basic info
    tenant_context = (
        "Tenant: nci-oa | User: dr-smith-001 | Tier: premium\n"
        "You are the OA Intake Agent. Follow the skill workflow exactly.\n\n"
    )

    options_base = dict(
        model=MODEL,
        system_prompt=tenant_context + skill_content,
        allowed_tools=["Read"],
        permission_mode="bypassPermissions",
        max_turns=3,
        max_budget_usd=0.15,
        cwd=os.path.dirname(os.path.abspath(__file__)),
        env={
            "CLAUDE_CODE_USE_BEDROCK": "1",
            "AWS_REGION": "us-east-1",
        },
    )

    # Workflow messages from the transcript
    workflow_turns = [
        {
            "phase": "Phase 1: Initial Intake",
            "user": "Cat scan machine. Not sure the price. I need it in 6 weeks.",
            "expect": ["ct", "scanner", "cost", "price", "timeline", "equipment"],
        },
        {
            "phase": "Phase 2: Clarifying Questions",
            "user": "I don't care about the manufacturer; it needs to be new, um, 128 slice. Yes, we have an urgent deadline.",
            "expect": ["128", "slice", "urgent", "negotiat", "$", "250"],
        },
        {
            "phase": "Phase 3: Urgency & Funding",
            "user": "Yes, a grant is expiring. I think we have an existing NIH contract.",
            "expect": ["grant", "contract", "vehicle", "fund", "expir"],
        },
    ]

    session_id = None
    phase_results = []
    total_cost = 0.0

    for i, turn in enumerate(workflow_turns):
        print(f"  --- {turn['phase']} ---")
        print(f"  User: {turn['user'][:80]}")

        if session_id:
            options = ClaudeAgentOptions(**options_base, resume=session_id)
        else:
            options = ClaudeAgentOptions(**options_base)

        collector = TraceCollector()

        async for message in query(prompt=turn["user"], options=options):
            collector.process(message, indent=3)

        summary = collector.summary()
        total_cost += summary["total_cost_usd"]

        # Capture session_id from first turn
        if not session_id and summary["session_id"]:
            session_id = summary["session_id"]
            print(f"    Session: {session_id}")

        # Check expected keywords in response
        all_text = " ".join(collector.text_blocks).lower()
        for msg_entry in collector.messages:
            msg = msg_entry["message"]
            if hasattr(msg, "result") and msg.result:
                all_text += " " + msg.result.lower()

        keywords_found = [kw for kw in turn["expect"] if kw in all_text]
        keywords_missing = [kw for kw in turn["expect"] if kw not in all_text]
        phase_pass = len(keywords_found) >= len(turn["expect"]) // 2

        phase_results.append({
            "phase": turn["phase"],
            "pass": phase_pass,
            "found": keywords_found,
            "missing": keywords_missing,
            "tokens": summary["total_input_tokens"] + summary["total_output_tokens"],
        })

        print(f"    Keywords found: {keywords_found}")
        if keywords_missing:
            print(f"    Keywords missing: {keywords_missing}")
        print(f"    Tokens: {summary['total_input_tokens']} in / {summary['total_output_tokens']} out")
        print(f"    {'PASS' if phase_pass else 'FAIL'}")
        print()

    print(f"  --- Workflow Summary ---")
    print(f"  Session: {session_id}")
    print(f"  Total cost: ${total_cost:.6f}")
    print(f"  Phases:")
    for pr in phase_results:
        status = "PASS" if pr["pass"] else "FAIL"
        print(f"    {pr['phase']}: {status} (found {len(pr['found'])}/{len(pr['found']) + len(pr['missing'])} keywords)")

    all_passed = all(pr["pass"] for pr in phase_results)
    passed = all_passed and session_id is not None
    print(f"\n  {'PASS' if passed else 'FAIL'} - OA Intake workflow ({len(phase_results)} phases)")
    return passed


# ============================================================
# Test 10: Legal Counsel Skill (Sole Source J&A Review)
# ============================================================

async def test_10_legal_counsel_skill():
    """Test Legal Counsel skill loaded from legacy prompt 02-legal.txt.
    Validates protest risk assessment, FAR citation, and case law references.
    """
    print("\n" + "=" * 70)
    print("TEST 10: Legal Counsel Skill (Sole Source J&A Review)")
    print("=" * 70)

    skill_content, skill_path = load_skill_or_prompt(prompt_file="02-legal.txt")
    if not skill_content:
        print(f"  SKIP - Legal prompt not found")
        return None

    print(f"  Skill loaded: {skill_path}")
    print(f"  Scenario: Sole source $985K Illumina sequencer")
    print()

    tenant_context = (
        "Tenant: nci-oa | User: co-johnson-001 | Tier: premium\n"
        "You are the Legal Counsel skill for the EAGLE Supervisor Agent.\n\n"
    )

    options = ClaudeAgentOptions(
        model=MODEL,
        system_prompt=tenant_context + skill_content,
        allowed_tools=[],
        permission_mode="bypassPermissions",
        max_turns=5,
        max_budget_usd=0.15,
        cwd=os.path.dirname(os.path.abspath(__file__)),
        env={
            "CLAUDE_CODE_USE_BEDROCK": "1",
            "AWS_REGION": "us-east-1",
        },
    )

    collector = TraceCollector()

    async for message in query(
        prompt=(
            "I need to sole source a $985K Illumina NovaSeq X Plus genome sequencer. "
            "Only Illumina makes this instrument. Assess the protest risk and "
            "tell me what FAR authority applies. What case precedents support this? "
            "Answer entirely from your knowledge — do not search files or use tools."
        ),
        options=options,
    ):
        collector.process(message, indent=2)

    print()
    summary = collector.summary()
    print(f"  --- Results ---")
    print(f"  Messages: {summary['total_messages']}")
    print(f"  Tokens: {summary['total_input_tokens']} in / {summary['total_output_tokens']} out")
    print(f"  Cost: ${summary['total_cost_usd']:.6f}")

    all_text = " ".join(collector.text_blocks).lower()
    for msg_entry in collector.messages:
        msg = msg_entry["message"]
        if hasattr(msg, "result") and msg.result:
            all_text += " " + msg.result.lower()

    indicators = {
        "far_citation": any(w in all_text for w in ["far 6.302", "6.302-1", "one responsible source"]),
        "protest_risk": any(w in all_text for w in ["protest", "risk", "gao", "vulnerability"]),
        "case_law": any(w in all_text for w in ["b-4", "decision", "precedent", "sustained", "denied"]),
        "proprietary": any(w in all_text for w in ["proprietary", "sole source", "only one", "sole vendor"]),
        "recommendation": any(w in all_text for w in ["recommend", "document", "justif", "market research"]),
    }

    print(f"  Skill indicators:")
    for indicator, found in indicators.items():
        print(f"    {indicator}: {found}")

    indicators_found = sum(1 for v in indicators.values() if v)
    passed = indicators_found >= 3 and summary["total_messages"] > 0
    print(f"\n  Skill indicators: {indicators_found}/5")
    print(f"  {'PASS' if passed else 'FAIL'} - Legal Counsel skill applied")
    return passed


# ============================================================
# Test 11: Market Intelligence Skill (Vendor Research)
# ============================================================

async def test_11_market_intelligence_skill():
    """Test Market Intelligence skill loaded from legacy prompt 04-market.txt.
    Validates vendor analysis, GSA pricing, and small business advocacy.
    """
    print("\n" + "=" * 70)
    print("TEST 11: Market Intelligence Skill (Vendor Research)")
    print("=" * 70)

    skill_content, skill_path = load_skill_or_prompt(prompt_file="04-market.txt")
    if not skill_content:
        print(f"  SKIP - Market prompt not found")
        return None

    print(f"  Skill loaded: {skill_path}")
    print(f"  Scenario: IT services $500K market research")
    print()

    tenant_context = (
        "Tenant: nci-oa | User: market-analyst-001 | Tier: premium\n"
        "You are the Market Intelligence skill for the EAGLE Supervisor Agent.\n\n"
    )

    options = ClaudeAgentOptions(
        model=MODEL,
        system_prompt=tenant_context + skill_content,
        allowed_tools=[],
        permission_mode="bypassPermissions",
        max_turns=3,
        max_budget_usd=0.15,
        cwd=os.path.dirname(os.path.abspath(__file__)),
        env={
            "CLAUDE_CODE_USE_BEDROCK": "1",
            "AWS_REGION": "us-east-1",
        },
    )

    collector = TraceCollector()

    async for message in query(
        prompt=(
            "We need IT modernization services for approximately $500K over 3 years. "
            "Cloud migration and agile development. What does the market look like? "
            "Any small business set-aside opportunities? What about GSA vehicles?"
        ),
        options=options,
    ):
        collector.process(message, indent=2)

    print()
    summary = collector.summary()
    print(f"  --- Results ---")
    print(f"  Messages: {summary['total_messages']}")
    print(f"  Tokens: {summary['total_input_tokens']} in / {summary['total_output_tokens']} out")
    print(f"  Cost: ${summary['total_cost_usd']:.6f}")

    all_text = " ".join(collector.text_blocks).lower()
    for msg_entry in collector.messages:
        msg = msg_entry["message"]
        if hasattr(msg, "result") and msg.result:
            all_text += " " + msg.result.lower()

    indicators = {
        "small_business": any(w in all_text for w in ["small business", "8(a)", "hubzone", "wosb", "sdvosb", "set-aside"]),
        "gsa_vehicles": any(w in all_text for w in ["gsa", "schedule", "gwac", "alliant", "cio-sp", "it schedule"]),
        "pricing": any(w in all_text for w in ["rate", "pricing", "cost", "benchmark", "$", "labor"]),
        "vendor_analysis": any(w in all_text for w in ["vendor", "contractor", "provider", "firm", "company"]),
        "competition": any(w in all_text for w in ["competit", "market", "availab", "capabil"]),
    }

    print(f"  Skill indicators:")
    for indicator, found in indicators.items():
        print(f"    {indicator}: {found}")

    indicators_found = sum(1 for v in indicators.values() if v)
    passed = indicators_found >= 3 and summary["total_messages"] > 0
    print(f"\n  Skill indicators: {indicators_found}/5")
    print(f"  {'PASS' if passed else 'FAIL'} - Market Intelligence skill applied")
    return passed


# ============================================================
# Test 12: Tech Review Skill (SOW Requirements Translation)
# ============================================================

async def test_12_tech_review_skill():
    """Test Tech Review skill loaded from legacy prompt 03-tech.txt.
    Validates technical-to-contract language translation and eval criteria.
    """
    print("\n" + "=" * 70)
    print("TEST 12: Tech Review Skill (SOW Requirements Translation)")
    print("=" * 70)

    skill_content, skill_path = load_skill_or_prompt(prompt_file="03-tech.txt")
    if not skill_content:
        print(f"  SKIP - Tech prompt not found")
        return None

    print(f"  Skill loaded: {skill_path}")
    print(f"  Scenario: Agile development SOW requirements")
    print()

    tenant_context = (
        "Tenant: nci-oa | User: cor-williams-001 | Tier: premium\n"
        "You are the Tech Review skill for the EAGLE Supervisor Agent.\n\n"
    )

    options = ClaudeAgentOptions(
        model=MODEL,
        system_prompt=tenant_context + skill_content,
        allowed_tools=[],
        permission_mode="bypassPermissions",
        max_turns=3,
        max_budget_usd=0.15,
        cwd=os.path.dirname(os.path.abspath(__file__)),
        env={
            "CLAUDE_CODE_USE_BEDROCK": "1",
            "AWS_REGION": "us-east-1",
        },
    )

    collector = TraceCollector()

    async for message in query(
        prompt=(
            "I need to write SOW requirements for an agile cloud migration project. "
            "The team will use 2-week sprints, AWS GovCloud, and need FedRAMP compliance. "
            "How should I express these technical requirements in contract language? "
            "What evaluation criteria would you recommend?"
        ),
        options=options,
    ):
        collector.process(message, indent=2)

    print()
    summary = collector.summary()
    print(f"  --- Results ---")
    print(f"  Messages: {summary['total_messages']}")
    print(f"  Tokens: {summary['total_input_tokens']} in / {summary['total_output_tokens']} out")
    print(f"  Cost: ${summary['total_cost_usd']:.6f}")

    all_text = " ".join(collector.text_blocks).lower()
    for msg_entry in collector.messages:
        msg = msg_entry["message"]
        if hasattr(msg, "result") and msg.result:
            all_text += " " + msg.result.lower()

    indicators = {
        "sow_language": any(w in all_text for w in ["sow", "statement of work", "deliverable", "performance"]),
        "agile_terms": any(w in all_text for w in ["sprint", "agile", "iteration", "scrum", "backlog"]),
        "evaluation": any(w in all_text for w in ["evaluat", "criteria", "factor", "technical approach", "past performance"]),
        "compliance": any(w in all_text for w in ["fedramp", "508", "security", "compliance", "govcloud"]),
        "measurable": any(w in all_text for w in ["measur", "accept", "milestone", "definition of done", "metric"]),
    }

    print(f"  Skill indicators:")
    for indicator, found in indicators.items():
        print(f"    {indicator}: {found}")

    indicators_found = sum(1 for v in indicators.values() if v)
    passed = indicators_found >= 3 and summary["total_messages"] > 0
    print(f"\n  Skill indicators: {indicators_found}/5")
    print(f"  {'PASS' if passed else 'FAIL'} - Tech Review skill applied")
    return passed


# ============================================================
# Test 13: Public Interest Skill (Fairness & Transparency)
# ============================================================

async def test_13_public_interest_skill():
    """Test Public Interest skill loaded from legacy prompt 05-public.txt.
    Validates fairness assessment, transparency check, and protest prevention.
    """
    print("\n" + "=" * 70)
    print("TEST 13: Public Interest Skill (Fairness & Transparency)")
    print("=" * 70)

    skill_content, skill_path = load_skill_or_prompt(prompt_file="05-public.txt")
    if not skill_content:
        print(f"  SKIP - Public Interest prompt not found")
        return None

    print(f"  Skill loaded: {skill_path}")
    print(f"  Scenario: $2.1M sole source IT services review")
    print()

    tenant_context = (
        "Tenant: nci-oa | User: co-davis-001 | Tier: premium\n"
        "You are the Public Interest skill for the EAGLE Supervisor Agent.\n\n"
    )

    options = ClaudeAgentOptions(
        model=MODEL,
        system_prompt=tenant_context + skill_content,
        allowed_tools=[],
        permission_mode="bypassPermissions",
        max_turns=3,
        max_budget_usd=0.15,
        cwd=os.path.dirname(os.path.abspath(__file__)),
        env={
            "CLAUDE_CODE_USE_BEDROCK": "1",
            "AWS_REGION": "us-east-1",
        },
    )

    collector = TraceCollector()

    async for message in query(
        prompt=(
            "Review this for public interest concerns: We're doing a sole source "
            "award for $2.1M in IT services to the same vendor who had the previous "
            "contract. No sources sought was posted on SAM.gov. Only 2 vendors were "
            "contacted during market research. This is a congressional interest area."
        ),
        options=options,
    ):
        collector.process(message, indent=2)

    print()
    summary = collector.summary()
    print(f"  --- Results ---")
    print(f"  Messages: {summary['total_messages']}")
    print(f"  Tokens: {summary['total_input_tokens']} in / {summary['total_output_tokens']} out")
    print(f"  Cost: ${summary['total_cost_usd']:.6f}")

    all_text = " ".join(collector.text_blocks).lower()
    for msg_entry in collector.messages:
        msg = msg_entry["message"]
        if hasattr(msg, "result") and msg.result:
            all_text += " " + msg.result.lower()

    indicators = {
        "fairness": any(w in all_text for w in ["fair", "equit", "appearance", "vendor lock", "incumbent"]),
        "transparency": any(w in all_text for w in ["transparen", "sam.gov", "sources sought", "public", "notice"]),
        "protest_risk": any(w in all_text for w in ["protest", "risk", "vulnerab", "challenge", "gao"]),
        "congressional": any(w in all_text for w in ["congress", "oversight", "media", "scrutin", "political"]),
        "recommendation": any(w in all_text for w in ["recommend", "mitigat", "broader", "expand", "post"]),
    }

    print(f"  Skill indicators:")
    for indicator, found in indicators.items():
        print(f"    {indicator}: {found}")

    indicators_found = sum(1 for v in indicators.values() if v)
    passed = indicators_found >= 3 and summary["total_messages"] > 0
    print(f"\n  Skill indicators: {indicators_found}/5")
    print(f"  {'PASS' if passed else 'FAIL'} - Public Interest skill applied")
    return passed


# ============================================================
# Test 14: Document Generator Skill (AP Generation)
# ============================================================

async def test_14_document_generator_skill():
    """Test Document Generator skill loaded from SKILL.md.
    Validates AP structure, FAR references, and signature blocks.
    """
    print("\n" + "=" * 70)
    print("TEST 14: Document Generator Skill (Acquisition Plan)")
    print("=" * 70)

    skill_content, skill_path = load_skill_or_prompt(skill_name="document-generator")
    if not skill_content:
        print(f"  SKIP - Document Generator skill not found")
        return None

    print(f"  Skill loaded: {skill_path}")
    print(f"  Scenario: Generate AP for $300K lab equipment")
    print()

    tenant_context = (
        "Tenant: nci-oa | User: co-martinez-001 | Tier: premium\n"
        "You are the Document Generator skill for the EAGLE Supervisor Agent.\n\n"
    )

    options = ClaudeAgentOptions(
        model=MODEL,
        system_prompt=tenant_context + skill_content,
        allowed_tools=[],
        permission_mode="bypassPermissions",
        max_turns=3,
        max_budget_usd=0.15,
        cwd=os.path.dirname(os.path.abspath(__file__)),
        env={
            "CLAUDE_CODE_USE_BEDROCK": "1",
            "AWS_REGION": "us-east-1",
        },
    )

    collector = TraceCollector()

    async for message in query(
        prompt=(
            "Generate an Acquisition Plan (AP) for the following: "
            "$300K laboratory centrifuge equipment purchase, new, competitive, "
            "simplified acquisition procedures (FAR Part 13), small business set-aside, "
            "delivery within 90 days, FY2026 funding. Include all required sections. "
            "IMPORTANT: Return the full document as text in your response. "
            "Do NOT write to a file."
        ),
        options=options,
    ):
        collector.process(message, indent=2)

    print()
    summary = collector.summary()
    print(f"  --- Results ---")
    print(f"  Messages: {summary['total_messages']}")
    print(f"  Tokens: {summary['total_input_tokens']} in / {summary['total_output_tokens']} out")
    print(f"  Cost: ${summary['total_cost_usd']:.6f}")

    # Collect text from text_blocks, result messages, AND Write tool inputs (fallback)
    all_text = " ".join(collector.text_blocks).lower()
    for msg_entry in collector.messages:
        msg = msg_entry["message"]
        if hasattr(msg, "result") and msg.result:
            all_text += " " + msg.result.lower()
    # If agent wrote to file via Write tool, include that content too
    for tu in collector.tool_use_blocks:
        if tu["tool"] == "Write" and "content" in tu.get("input", {}):
            all_text += " " + tu["input"]["content"].lower()

    indicators = {
        "ap_sections": any(w in all_text for w in ["section 1", "statement of need", "background", "objective"]),
        "far_reference": any(w in all_text for w in ["far", "part 13", "simplified", "52."]),
        "cost_info": any(w in all_text for w in ["$300", "fy2026", "funding", "cost"]),
        "competition": any(w in all_text for w in ["competit", "set-aside", "small business", "source selection"]),
        "signature": any(w in all_text for w in ["signature", "approv", "contracting officer", "program"]),
    }

    print(f"  Skill indicators:")
    for indicator, found in indicators.items():
        print(f"    {indicator}: {found}")

    indicators_found = sum(1 for v in indicators.values() if v)
    passed = indicators_found >= 3 and summary["total_messages"] > 0
    print(f"\n  Skill indicators: {indicators_found}/5")
    print(f"  {'PASS' if passed else 'FAIL'} - Document Generator skill applied")
    return passed


# ============================================================
# Test 15: Supervisor Multi-Skill Chain (UC-01 End-to-End)
# ============================================================

async def test_15_supervisor_multi_skill_chain():
    """Test the Supervisor Agent invoking multiple skills as subagents.
    Simulates the UC-01 full skill chain: Intake -> Market -> Legal -> DocGen.
    Each skill is a subagent with its own system_prompt from legacy prompts.
    """
    print("\n" + "=" * 70)
    print("TEST 15: Supervisor Multi-Skill Chain (UC-01 End-to-End)")
    print("=" * 70)

    # Load skill prompts for subagents
    legal_content, _ = load_skill_or_prompt(prompt_file="02-legal.txt")
    market_content, _ = load_skill_or_prompt(prompt_file="04-market.txt")
    intake_content, _ = load_skill_or_prompt(skill_name="oa-intake")

    missing = []
    if not legal_content:
        missing.append("02-legal.txt")
    if not market_content:
        missing.append("04-market.txt")
    if not intake_content:
        missing.append("oa-intake SKILL.md")

    if missing:
        print(f"  SKIP - Missing skill files: {missing}")
        return None

    print(f"  Skill chain: OA Intake -> Market Intelligence -> Legal Counsel")
    print(f"  Scenario: $500K IT services, competitive, 3-year PoP")
    print()

    supervisor_prompt = (
        "You are the EAGLE Supervisor Agent for NCI Office of Acquisitions.\n"
        "You orchestrate acquisition workflows by delegating to specialized skill subagents.\n\n"
        "Available subagents:\n"
        "- oa-intake: Gathers initial requirements and determines acquisition type\n"
        "- market-intelligence: Researches vendors, pricing, small business opportunities\n"
        "- legal-counsel: Assesses legal risks, protest vulnerabilities, FAR compliance\n\n"
        "For this request, invoke each subagent in sequence:\n"
        "1. First use oa-intake to classify the acquisition\n"
        "2. Then use market-intelligence to assess the market\n"
        "3. Then use legal-counsel to check legal risks\n"
        "4. Synthesize all findings into a brief summary\n\n"
        "IMPORTANT: You MUST use the Task tool to delegate to subagents. Do not answer directly."
    )

    options = ClaudeAgentOptions(
        model=MODEL,
        system_prompt=supervisor_prompt,
        allowed_tools=["Task"],
        permission_mode="bypassPermissions",
        max_turns=15,
        max_budget_usd=0.50,
        cwd=os.path.dirname(os.path.abspath(__file__)),
        env={
            "CLAUDE_CODE_USE_BEDROCK": "1",
            "AWS_REGION": "us-east-1",
        },
        agents={
            "oa-intake": AgentDefinition(
                description="Gathers acquisition requirements and determines type/threshold. Use for initial intake.",
                prompt=intake_content[:3000],  # Truncate to fit
                tools=[],
                model=MODEL,
            ),
            "market-intelligence": AgentDefinition(
                description="Researches market conditions, vendors, and pricing. Use for market research.",
                prompt=market_content,
                tools=[],
                model=MODEL,
            ),
            "legal-counsel": AgentDefinition(
                description="Assesses legal risks, protest vulnerabilities, FAR compliance. Use for legal review.",
                prompt=legal_content,
                tools=[],
                model=MODEL,
            ),
        },
    )

    collector = TraceCollector()

    async for message in query(
        prompt=(
            "New acquisition request: We need IT modernization services for $500K "
            "over 3 years. Includes cloud migration and agile development. "
            "Run the full skill chain to assess this acquisition."
        ),
        options=options,
    ):
        collector.process(message, indent=2)

    print()
    summary = collector.summary()
    print(f"  --- Results ---")
    print(f"  Messages: {summary['total_messages']}")
    print(f"  Tool use blocks: {summary['tool_use_blocks']}")
    print(f"  Tokens: {summary['total_input_tokens']} in / {summary['total_output_tokens']} out")
    print(f"  Cost: ${summary['total_cost_usd']:.6f}")

    # Check for subagent invocations
    subagent_calls = [t for t in collector.tool_use_blocks if t["tool"] == "Task"]
    subagent_types = [t["input"].get("subagent_type", t["input"].get("description", "?"))
                      for t in subagent_calls]

    print(f"  Subagent invocations: {len(subagent_calls)}")
    for st in subagent_types:
        print(f"    -> {st}")

    # Check response content
    all_text = " ".join(collector.text_blocks).lower()
    for msg_entry in collector.messages:
        msg = msg_entry["message"]
        if hasattr(msg, "result") and msg.result:
            all_text += " " + msg.result.lower()

    indicators = {
        "multiple_subagents": len(subagent_calls) >= 2,
        "intake_invoked": any("intake" in st.lower() for st in subagent_types),
        "market_invoked": any("market" in st.lower() for st in subagent_types),
        "legal_invoked": any("legal" in st.lower() or "counsel" in st.lower() for st in subagent_types),
        "synthesis": any(w in all_text for w in ["summary", "recommend", "finding", "assessment", "result"]),
    }

    print(f"  Skill chain indicators:")
    for indicator, found in indicators.items():
        print(f"    {indicator}: {found}")

    indicators_found = sum(1 for v in indicators.values() if v)
    passed = indicators_found >= 3 and summary["total_messages"] > 2
    print(f"\n  Skill chain indicators: {indicators_found}/5")
    print(f"  {'PASS' if passed else 'FAIL'} - Supervisor multi-skill chain")
    return passed


# ============================================================
# Test 21: UC-02 Micro-Purchase Workflow (<$15K Fast Path)
# ============================================================

async def test_21_uc02_micro_purchase():
    """UC-02: Micro-purchase fast path — threshold detection, streamlined intake,
    purchase request generation. Validates sub-$15K streamlined workflow.
    """
    print("\n" + "=" * 70)
    print("TEST 21: UC-02 Micro-Purchase Workflow (<$15K Fast Path)")
    print("=" * 70)

    intake_content, _ = load_skill_or_prompt(skill_name="oa-intake")
    if not intake_content:
        print(f"  SKIP - OA Intake skill not found")
        return None

    print(f"  Scenario: $13,800 lab supplies — Fisher Scientific quote")
    print()

    tenant_context = (
        "Tenant: nci-oa | User: cor-adams-001 | Tier: premium\n"
        "You are the OA Intake skill for the EAGLE Supervisor Agent.\n"
        "Handle micro-purchase requests efficiently with minimal questions.\n\n"
    )

    options = ClaudeAgentOptions(
        model=MODEL,
        system_prompt=tenant_context + intake_content,
        allowed_tools=[],
        permission_mode="bypassPermissions",
        max_turns=3,
        max_budget_usd=0.15,
        cwd=os.path.dirname(os.path.abspath(__file__)),
        env={
            "CLAUDE_CODE_USE_BEDROCK": "1",
            "AWS_REGION": "us-east-1",
        },
    )

    collector = TraceCollector()

    async for message in query(
        prompt=(
            "I have a quote for $13,800 from Fisher Scientific for lab supplies — "
            "centrifuge tubes, pipette tips, and reagents. Grant-funded, deliver to "
            "Building 37 Room 204. I want to use the purchase card. "
            "What's the fastest way to process this?"
        ),
        options=options,
    ):
        collector.process(message, indent=2)

    print()
    summary = collector.summary()
    print(f"  --- Results ---")
    print(f"  Messages: {summary['total_messages']}")
    print(f"  Tokens: {summary['total_input_tokens']} in / {summary['total_output_tokens']} out")
    print(f"  Cost: ${summary['total_cost_usd']:.6f}")

    all_text = " ".join(collector.text_blocks).lower()
    for msg_entry in collector.messages:
        msg = msg_entry["message"]
        if hasattr(msg, "result") and msg.result:
            all_text += " " + msg.result.lower()

    indicators = {
        "micro_purchase": any(w in all_text for w in ["micro-purchase", "micro purchase", "micropurchase", "simplified"]),
        "threshold": any(w in all_text for w in ["$15,000", "15k", "threshold", "below", "under"]),
        "purchase_card": any(w in all_text for w in ["purchase card", "p-card", "card holder", "government purchase"]),
        "streamlined": any(w in all_text for w in ["streamlined", "fast", "quick", "expedit", "minimal"]),
        "far_reference": any(w in all_text for w in ["far 13", "part 13", "far part", "simplified acquisition"]),
    }

    print(f"  UC-02 indicators:")
    for indicator, found in indicators.items():
        print(f"    {indicator}: {found}")

    indicators_found = sum(1 for v in indicators.values() if v)
    passed = indicators_found >= 3 and summary["total_messages"] > 0
    print(f"\n  UC-02 indicators: {indicators_found}/5")
    print(f"  {'PASS' if passed else 'FAIL'} - UC-02 Micro-Purchase workflow")
    return passed


# ============================================================
# Test 22: UC-03 Option Exercise Package Preparation
# ============================================================

async def test_22_uc03_option_exercise():
    """UC-03: Option exercise — previous package ingestion, tuning questions,
    compliance validation, updated package generation with cost escalation.
    """
    print("\n" + "=" * 70)
    print("TEST 22: UC-03 Option Exercise Package Preparation")
    print("=" * 70)

    intake_content, _ = load_skill_or_prompt(skill_name="oa-intake")
    if not intake_content:
        print(f"  SKIP - OA Intake skill not found")
        return None

    print(f"  Scenario: Exercise Option Year 3, same scope, 3% escalation")
    print()

    tenant_context = (
        "Tenant: nci-oa | User: co-chen-001 | Tier: premium\n"
        "You are the OA Intake skill for the EAGLE Supervisor Agent.\n"
        "Handle option exercise requests by reviewing prior packages and asking tuning questions.\n\n"
    )

    options = ClaudeAgentOptions(
        model=MODEL,
        system_prompt=tenant_context + intake_content,
        allowed_tools=[],
        permission_mode="bypassPermissions",
        max_turns=3,
        max_budget_usd=0.15,
        cwd=os.path.dirname(os.path.abspath(__file__)),
        env={
            "CLAUDE_CODE_USE_BEDROCK": "1",
            "AWS_REGION": "us-east-1",
        },
    )

    collector = TraceCollector()

    async for message in query(
        prompt=(
            "I need to exercise Option Year 3 on contract HHSN261201500003I. "
            "The base value was $1.2M, same scope continuing, new COR replacing "
            "Dr. Smith, 3% cost escalation per the contract terms, no performance "
            "issues. Option period would be 10/1/2028 through 9/30/2029. "
            "What documents do I need to prepare?"
        ),
        options=options,
    ):
        collector.process(message, indent=2)

    print()
    summary = collector.summary()
    print(f"  --- Results ---")
    print(f"  Messages: {summary['total_messages']}")
    print(f"  Tokens: {summary['total_input_tokens']} in / {summary['total_output_tokens']} out")
    print(f"  Cost: ${summary['total_cost_usd']:.6f}")

    all_text = " ".join(collector.text_blocks).lower()
    for msg_entry in collector.messages:
        msg = msg_entry["message"]
        if hasattr(msg, "result") and msg.result:
            all_text += " " + msg.result.lower()

    indicators = {
        "option_exercise": any(w in all_text for w in ["option", "exercise", "option year", "option period"]),
        "escalation": any(w in all_text for w in ["escalat", "3%", "cost increase", "price adjust"]),
        "cor_change": any(w in all_text for w in ["cor", "contracting officer representative", "nomination", "new cor"]),
        "package_docs": any(w in all_text for w in ["acquisition plan", "sow", "igce", "statement of work"]),
        "option_letter": any(w in all_text for w in ["option letter", "exercise letter", "modification", "bilateral"]),
    }

    print(f"  UC-03 indicators:")
    for indicator, found in indicators.items():
        print(f"    {indicator}: {found}")

    indicators_found = sum(1 for v in indicators.values() if v)
    passed = indicators_found >= 3 and summary["total_messages"] > 0
    print(f"\n  UC-03 indicators: {indicators_found}/5")
    print(f"  {'PASS' if passed else 'FAIL'} - UC-03 Option Exercise workflow")
    return passed


# ============================================================
# Test 23: UC-04 Contract Modification Request
# ============================================================

async def test_23_uc04_contract_modification():
    """UC-04: Contract modification — add funding + extend PoP, determine mod type,
    compliance check, generate SF-30 and supporting documents.
    """
    print("\n" + "=" * 70)
    print("TEST 23: UC-04 Contract Modification Request")
    print("=" * 70)

    intake_content, _ = load_skill_or_prompt(skill_name="oa-intake")
    if not intake_content:
        print(f"  SKIP - OA Intake skill not found")
        return None

    print(f"  Scenario: Add $150K funding + extend PoP 6 months")
    print()

    tenant_context = (
        "Tenant: nci-oa | User: co-garcia-001 | Tier: premium\n"
        "You are the OA Intake skill for the EAGLE Supervisor Agent.\n"
        "Handle contract modification requests by classifying mod type and identifying required documents.\n\n"
    )

    options = ClaudeAgentOptions(
        model=MODEL,
        system_prompt=tenant_context + intake_content,
        allowed_tools=[],
        permission_mode="bypassPermissions",
        max_turns=3,
        max_budget_usd=0.15,
        cwd=os.path.dirname(os.path.abspath(__file__)),
        env={
            "CLAUDE_CODE_USE_BEDROCK": "1",
            "AWS_REGION": "us-east-1",
        },
    )

    collector = TraceCollector()

    async for message in query(
        prompt=(
            "I need to modify contract HHSN261201500003I. Adding $150K in FY2026 "
            "funding and extending the period of performance by 6 months to September 30, 2027. "
            "Same scope of work, just continuing the existing effort. "
            "Is this within scope? What type of modification is this? What documents do I need?"
        ),
        options=options,
    ):
        collector.process(message, indent=2)

    print()
    summary = collector.summary()
    print(f"  --- Results ---")
    print(f"  Messages: {summary['total_messages']}")
    print(f"  Tokens: {summary['total_input_tokens']} in / {summary['total_output_tokens']} out")
    print(f"  Cost: ${summary['total_cost_usd']:.6f}")

    all_text = " ".join(collector.text_blocks).lower()
    for msg_entry in collector.messages:
        msg = msg_entry["message"]
        if hasattr(msg, "result") and msg.result:
            all_text += " " + msg.result.lower()

    indicators = {
        "modification": any(w in all_text for w in ["modif", "mod ", "sf-30", "amendment"]),
        "funding": any(w in all_text for w in ["fund", "$150", "fy2026", "incremental", "additional"]),
        "pop_extension": any(w in all_text for w in ["period of performance", "pop", "extend", "extension", "september"]),
        "within_scope": any(w in all_text for w in ["within scope", "in-scope", "no j&a", "same work", "bilateral"]),
        "far_compliance": any(w in all_text for w in ["far", "compliance", "justif", "clause", "unilateral"]),
    }

    print(f"  UC-04 indicators:")
    for indicator, found in indicators.items():
        print(f"    {indicator}: {found}")

    indicators_found = sum(1 for v in indicators.values() if v)
    passed = indicators_found >= 3 and summary["total_messages"] > 0
    print(f"\n  UC-04 indicators: {indicators_found}/5")
    print(f"  {'PASS' if passed else 'FAIL'} - UC-04 Contract Modification workflow")
    return passed


# ============================================================
# Test 24: UC-05 CO Package Review & Findings
# ============================================================

async def test_24_uc05_co_package_review():
    """UC-05: CO package review — compliance checks across AP/SOW/IGCE,
    cross-reference consistency, findings report with severity levels.
    """
    print("\n" + "=" * 70)
    print("TEST 24: UC-05 CO Package Review & Findings Generation")
    print("=" * 70)

    # This UC uses compliance + tech review skills
    comp_content, _ = load_skill_or_prompt(prompt_file="02-legal.txt")
    if not comp_content:
        print(f"  SKIP - Compliance/legal prompt not found")
        return None

    print(f"  Scenario: CO reviews acquisition package for $487K IT services")
    print()

    tenant_context = (
        "Tenant: nci-oa | User: co-patel-001 | Tier: premium\n"
        "You are the Compliance skill for the EAGLE Supervisor Agent.\n"
        "Review acquisition packages for FAR compliance, cross-reference consistency, "
        "and generate findings organized by severity.\n\n"
    )

    options = ClaudeAgentOptions(
        model=MODEL,
        system_prompt=tenant_context + comp_content,
        allowed_tools=[],
        permission_mode="bypassPermissions",
        max_turns=3,
        max_budget_usd=0.15,
        cwd=os.path.dirname(os.path.abspath(__file__)),
        env={
            "CLAUDE_CODE_USE_BEDROCK": "1",
            "AWS_REGION": "us-east-1",
        },
    )

    collector = TraceCollector()

    async for message in query(
        prompt=(
            "Review this acquisition package for a $487,500 IT services contract: "
            "The AP says competitive full and open, but the IGCE total is $495,000 — "
            "cost mismatch. The SOW mentions a 3-year PoP but the AP says 2 years. "
            "Market research is 14 months old. No FAR 52.219 small business clause. "
            "Task 3 deliverable in the SOW has no acceptance criteria. "
            "Identify all findings and categorize by severity (critical/moderate/minor)."
        ),
        options=options,
    ):
        collector.process(message, indent=2)

    print()
    summary = collector.summary()
    print(f"  --- Results ---")
    print(f"  Messages: {summary['total_messages']}")
    print(f"  Tokens: {summary['total_input_tokens']} in / {summary['total_output_tokens']} out")
    print(f"  Cost: ${summary['total_cost_usd']:.6f}")

    all_text = " ".join(collector.text_blocks).lower()
    for msg_entry in collector.messages:
        msg = msg_entry["message"]
        if hasattr(msg, "result") and msg.result:
            all_text += " " + msg.result.lower()

    indicators = {
        "cost_mismatch": any(w in all_text for w in ["cost mismatch", "igce", "inconsisten", "$487", "$495"]),
        "pop_inconsistency": any(w in all_text for w in ["period of performance", "pop", "mismatch", "3-year", "2-year"]),
        "far_clause": any(w in all_text for w in ["far 52", "clause", "52.219", "small business"]),
        "severity": any(w in all_text for w in ["critical", "moderate", "minor", "severity", "finding"]),
        "market_research": any(w in all_text for w in ["market research", "outdated", "14 month", "stale"]),
    }

    print(f"  UC-05 indicators:")
    for indicator, found in indicators.items():
        print(f"    {indicator}: {found}")

    indicators_found = sum(1 for v in indicators.values() if v)
    passed = indicators_found >= 3 and summary["total_messages"] > 0
    print(f"\n  UC-05 indicators: {indicators_found}/5")
    print(f"  {'PASS' if passed else 'FAIL'} - UC-05 CO Package Review workflow")
    return passed


# ============================================================
# Test 25: UC-07 Contract Close-Out
# ============================================================

async def test_25_uc07_contract_closeout():
    """UC-07: Contract close-out — FAR 4.804 checklist, release of claims,
    final patent/property reports, COR final assessment.
    """
    print("\n" + "=" * 70)
    print("TEST 25: UC-07 Contract Close-Out")
    print("=" * 70)

    comp_content, _ = load_skill_or_prompt(prompt_file="02-legal.txt")
    if not comp_content:
        print(f"  SKIP - Compliance/legal prompt not found")
        return None

    print(f"  Scenario: Close out FFP contract HHSN261200900045C")
    print()

    tenant_context = (
        "Tenant: nci-oa | User: co-brown-001 | Tier: premium\n"
        "You are the Compliance skill for the EAGLE Supervisor Agent.\n"
        "Handle contract close-out by generating FAR 4.804 checklists and identifying required actions.\n\n"
    )

    options = ClaudeAgentOptions(
        model=MODEL,
        system_prompt=tenant_context + comp_content,
        allowed_tools=[],
        permission_mode="bypassPermissions",
        max_turns=3,
        max_budget_usd=0.15,
        cwd=os.path.dirname(os.path.abspath(__file__)),
        env={
            "CLAUDE_CODE_USE_BEDROCK": "1",
            "AWS_REGION": "us-east-1",
        },
    )

    collector = TraceCollector()

    async for message in query(
        prompt=(
            "I need to close out contract HHSN261200900045C. It's a firm-fixed-price "
            "contract, all options were exercised, final invoice has been paid, "
            "and all deliverables have been accepted. What's the FAR 4.804 close-out "
            "checklist? What documents do I still need — release of claims letter, "
            "patent report, property report? Draft a COR final assessment outline."
        ),
        options=options,
    ):
        collector.process(message, indent=2)

    print()
    summary = collector.summary()
    print(f"  --- Results ---")
    print(f"  Messages: {summary['total_messages']}")
    print(f"  Tokens: {summary['total_input_tokens']} in / {summary['total_output_tokens']} out")
    print(f"  Cost: ${summary['total_cost_usd']:.6f}")

    all_text = " ".join(collector.text_blocks).lower()
    for msg_entry in collector.messages:
        msg = msg_entry["message"]
        if hasattr(msg, "result") and msg.result:
            all_text += " " + msg.result.lower()

    indicators = {
        "far_4804": any(w in all_text for w in ["far 4.804", "4.804", "close-out", "closeout"]),
        "release_claims": any(w in all_text for w in ["release of claims", "release", "claims letter"]),
        "patent_report": any(w in all_text for w in ["patent", "intellectual property", "invention"]),
        "property_report": any(w in all_text for w in ["property", "gfp", "government furnished", "disposition"]),
        "cor_assessment": any(w in all_text for w in ["cor", "final assessment", "performance assessment", "completion"]),
    }

    print(f"  UC-07 indicators:")
    for indicator, found in indicators.items():
        print(f"    {indicator}: {found}")

    indicators_found = sum(1 for v in indicators.values() if v)
    passed = indicators_found >= 3 and summary["total_messages"] > 0
    print(f"\n  UC-07 indicators: {indicators_found}/5")
    print(f"  {'PASS' if passed else 'FAIL'} - UC-07 Contract Close-Out workflow")
    return passed


# ============================================================
# Test 26: UC-08 Government Shutdown Notification
# ============================================================

async def test_26_uc08_shutdown_notification():
    """UC-08: Shutdown notification — contract classification (continue/stop/excepted),
    batch email generation, time-critical processing.
    """
    print("\n" + "=" * 70)
    print("TEST 26: UC-08 Government Shutdown Notification")
    print("=" * 70)

    comp_content, _ = load_skill_or_prompt(prompt_file="02-legal.txt")
    if not comp_content:
        print(f"  SKIP - Compliance/legal prompt not found")
        return None

    print(f"  Scenario: Government shutdown in 4 hours, classify 200+ contracts")
    print()

    tenant_context = (
        "Tenant: nci-oa | User: co-wilson-001 | Tier: premium\n"
        "You are the Compliance skill for the EAGLE Supervisor Agent.\n"
        "Handle government shutdown notifications by classifying contracts and generating notifications.\n\n"
    )

    options = ClaudeAgentOptions(
        model=MODEL,
        system_prompt=tenant_context + comp_content,
        allowed_tools=[],
        permission_mode="bypassPermissions",
        max_turns=3,
        max_budget_usd=0.15,
        cwd=os.path.dirname(os.path.abspath(__file__)),
        env={
            "CLAUDE_CODE_USE_BEDROCK": "1",
            "AWS_REGION": "us-east-1",
        },
    )

    collector = TraceCollector()

    async for message in query(
        prompt=(
            "Government shutdown is imminent — 4 hours away. I have 200+ active contracts. "
            "How should I classify them? I know some are fully funded FFP (should continue), "
            "some are incrementally funded (stop at limit), some are cost-reimbursement "
            "(stop work immediately), and some support excepted life/safety activities. "
            "What notification categories do I need? What should each email say? "
            "Draft the four notification templates."
        ),
        options=options,
    ):
        collector.process(message, indent=2)

    print()
    summary = collector.summary()
    print(f"  --- Results ---")
    print(f"  Messages: {summary['total_messages']}")
    print(f"  Tokens: {summary['total_input_tokens']} in / {summary['total_output_tokens']} out")
    print(f"  Cost: ${summary['total_cost_usd']:.6f}")

    all_text = " ".join(collector.text_blocks).lower()
    for msg_entry in collector.messages:
        msg = msg_entry["message"]
        if hasattr(msg, "result") and msg.result:
            all_text += " " + msg.result.lower()

    indicators = {
        "shutdown": any(w in all_text for w in ["shutdown", "lapse", "appropriation", "continuing resolution"]),
        "ffp_continue": any(w in all_text for w in ["firm-fixed", "ffp", "continue", "fully funded"]),
        "stop_work": any(w in all_text for w in ["stop work", "cease", "stop-work", "suspend"]),
        "excepted": any(w in all_text for w in ["excepted", "life", "safety", "essential", "emergency"]),
        "notification": any(w in all_text for w in ["notif", "email", "letter", "template", "contractor"]),
    }

    print(f"  UC-08 indicators:")
    for indicator, found in indicators.items():
        print(f"    {indicator}: {found}")

    indicators_found = sum(1 for v in indicators.values() if v)
    passed = indicators_found >= 3 and summary["total_messages"] > 0
    print(f"\n  UC-08 indicators: {indicators_found}/5")
    print(f"  {'PASS' if passed else 'FAIL'} - UC-08 Shutdown Notification workflow")
    return passed


# ============================================================
# Test 27: UC-09 Technical Score Sheet Consolidation
# ============================================================

async def test_27_uc09_score_consolidation():
    """UC-09: Score consolidation — parse score sheets from multiple reviewers,
    cross-reviewer variance analysis, question deduplication, evaluation report.
    """
    print("\n" + "=" * 70)
    print("TEST 27: UC-09 Technical Score Sheet Consolidation")
    print("=" * 70)

    tech_content, _ = load_skill_or_prompt(prompt_file="03-tech.txt")
    if not tech_content:
        print(f"  SKIP - Tech Review prompt not found")
        return None

    print(f"  Scenario: Consolidate 180 score sheets from 9 reviewers on 20 proposals")
    print()

    tenant_context = (
        "Tenant: nci-oa | User: co-taylor-001 | Tier: premium\n"
        "You are the Tech Review skill for the EAGLE Supervisor Agent.\n"
        "Handle technical evaluation score consolidation and question deduplication.\n\n"
    )

    options = ClaudeAgentOptions(
        model=MODEL,
        system_prompt=tenant_context + tech_content,
        allowed_tools=[],
        permission_mode="bypassPermissions",
        max_turns=3,
        max_budget_usd=0.15,
        cwd=os.path.dirname(os.path.abspath(__file__)),
        env={
            "CLAUDE_CODE_USE_BEDROCK": "1",
            "AWS_REGION": "us-east-1",
        },
    )

    collector = TraceCollector()

    async for message in query(
        prompt=(
            "I have 180 score sheets from 9 technical reviewers evaluating 20 proposals. "
            "Each reviewer scored 5 evaluation factors: Technical Approach, Management Plan, "
            "Past Performance, Key Personnel, and Cost Realism. "
            "Three proposals have significant reviewer divergence. "
            "The reviewers also submitted 847 total questions — many are duplicates. "
            "How should I consolidate the scores? What analysis should I run for "
            "reviewer variance? How do I deduplicate and categorize the questions?"
        ),
        options=options,
    ):
        collector.process(message, indent=2)

    print()
    summary = collector.summary()
    print(f"  --- Results ---")
    print(f"  Messages: {summary['total_messages']}")
    print(f"  Tokens: {summary['total_input_tokens']} in / {summary['total_output_tokens']} out")
    print(f"  Cost: ${summary['total_cost_usd']:.6f}")

    all_text = " ".join(collector.text_blocks).lower()
    for msg_entry in collector.messages:
        msg = msg_entry["message"]
        if hasattr(msg, "result") and msg.result:
            all_text += " " + msg.result.lower()

    indicators = {
        "score_matrix": any(w in all_text for w in ["score", "matrix", "consensus", "consolidat"]),
        "eval_factors": any(w in all_text for w in ["technical approach", "management", "past performance", "key personnel"]),
        "variance_analysis": any(w in all_text for w in ["variance", "divergen", "outlier", "disagree", "spread"]),
        "deduplication": any(w in all_text for w in ["dedup", "duplicate", "unique", "cluster", "categoriz"]),
        "evaluation_report": any(w in all_text for w in ["report", "summary", "per-contractor", "question sheet"]),
    }

    print(f"  UC-09 indicators:")
    for indicator, found in indicators.items():
        print(f"    {indicator}: {found}")

    indicators_found = sum(1 for v in indicators.values() if v)
    passed = indicators_found >= 3 and summary["total_messages"] > 0
    print(f"\n  UC-09 indicators: {indicators_found}/5")
    print(f"  {'PASS' if passed else 'FAIL'} - UC-09 Score Consolidation workflow")
    return passed


# ============================================================
# Test 16: S3 Document Operations (Direct Tool Call + boto3)
# ============================================================

async def test_16_s3_document_ops():
    """Call execute_tool('s3_document_ops') directly, verify via boto3."""
    print("\n" + "=" * 70)
    print("TEST 16: S3 Document Operations (Direct Tool + boto3 Confirm)")
    print("=" * 70)

    import boto3 as _boto3

    tenant_id = "test-tenant"
    session_id = "test-session-001"
    test_key = f"test_doc_{uuid.uuid4().hex[:8]}.md"
    test_content = f"# Test Document\nGenerated at {datetime.now(timezone.utc).isoformat()}\nThis is test content for S3 verification."
    bucket = "nci-documents"

    steps_passed = []

    # Step 1: Write
    print(f"  Step 1: write key={test_key}")
    write_result = json.loads(execute_tool("s3_document_ops", {
        "operation": "write",
        "key": test_key,
        "content": test_content,
    }, session_id))
    write_ok = write_result.get("status") == "success"
    full_key = write_result.get("key", "")
    steps_passed.append(("write", write_ok))
    print(f"    status={write_result.get('status')} key={full_key} {'PASS' if write_ok else 'FAIL'}")

    # Step 2: List
    print(f"  Step 2: list")
    list_result = json.loads(execute_tool("s3_document_ops", {
        "operation": "list",
    }, session_id))
    list_ok = list_result.get("file_count", 0) >= 1
    file_keys = [f["key"] for f in list_result.get("files", [])]
    found_in_list = any(test_key in k for k in file_keys)
    steps_passed.append(("list", list_ok and found_in_list))
    print(f"    file_count={list_result.get('file_count')} found_in_list={found_in_list} {'PASS' if list_ok and found_in_list else 'FAIL'}")

    # Step 3: Read
    print(f"  Step 3: read key={test_key}")
    read_result = json.loads(execute_tool("s3_document_ops", {
        "operation": "read",
        "key": test_key,
    }, session_id))
    read_content = read_result.get("content", "")
    read_ok = test_content in read_content
    steps_passed.append(("read", read_ok))
    print(f"    content_match={read_ok} size={read_result.get('size_bytes', 0)} {'PASS' if read_ok else 'FAIL'}")

    # Step 4: boto3 confirm
    print(f"  Step 4: boto3 head_object confirm")
    s3 = _boto3.client("s3", region_name="us-east-1")
    boto3_ok = False
    try:
        head = s3.head_object(Bucket=bucket, Key=full_key)
        boto3_ok = head["ContentLength"] > 0
        print(f"    ContentLength={head['ContentLength']} exists=True PASS")
    except Exception as e:
        print(f"    boto3 error: {e} FAIL")
    steps_passed.append(("boto3_confirm", boto3_ok))

    # Step 5: Cleanup
    print(f"  Step 5: cleanup")
    try:
        s3.delete_object(Bucket=bucket, Key=full_key)
        print(f"    deleted {full_key}")
    except Exception as e:
        print(f"    cleanup error: {e}")

    # Summary
    passed = all(ok for _, ok in steps_passed)
    print(f"\n  Steps: {', '.join(f'{name}={'PASS' if ok else 'FAIL'}' for name, ok in steps_passed)}")
    print(f"  {'PASS' if passed else 'FAIL'} - S3 Document Operations (direct tool + boto3)")
    return passed


# ============================================================
# Test 17: DynamoDB Intake Operations (Direct Tool Call + boto3)
# ============================================================

async def test_17_dynamodb_intake_ops():
    """Call execute_tool('dynamodb_intake') directly, verify via boto3."""
    print("\n" + "=" * 70)
    print("TEST 17: DynamoDB Intake Operations (Direct Tool + boto3 Confirm)")
    print("=" * 70)

    import boto3 as _boto3

    tenant_id = "test-tenant"
    session_id = "test-session-001"
    item_id = f"test-item-{uuid.uuid4().hex[:8]}"
    test_data = {
        "title": "Test Acquisition Item",
        "value": "$50,000",
        "type": "equipment",
    }
    table_name = "eagle"

    steps_passed = []

    # Step 1: Create
    print(f"  Step 1: create item_id={item_id}")
    create_result = json.loads(execute_tool("dynamodb_intake", {
        "operation": "create",
        "item_id": item_id,
        "data": test_data,
    }, session_id))
    create_ok = create_result.get("item_id") == item_id and create_result.get("status") == "created"
    steps_passed.append(("create", create_ok))
    print(f"    item_id={create_result.get('item_id')} status={create_result.get('status')} {'PASS' if create_ok else 'FAIL'}")

    # Step 2: Read
    print(f"  Step 2: read item_id={item_id}")
    read_result = json.loads(execute_tool("dynamodb_intake", {
        "operation": "read",
        "item_id": item_id,
    }, session_id))
    read_item = read_result.get("item", {})
    read_ok = read_item.get("item_id") == item_id and read_item.get("title") == test_data["title"]
    steps_passed.append(("read", read_ok))
    print(f"    item_id={read_item.get('item_id')} title={read_item.get('title')} {'PASS' if read_ok else 'FAIL'}")

    # Step 3: Update
    print(f"  Step 3: update item_id={item_id}")
    update_result = json.loads(execute_tool("dynamodb_intake", {
        "operation": "update",
        "item_id": item_id,
        "data": {"status": "reviewed"},
    }, session_id))
    update_ok = update_result.get("status") == "updated"
    steps_passed.append(("update", update_ok))
    print(f"    status={update_result.get('status')} {'PASS' if update_ok else 'FAIL'}")

    # Step 4: List
    print(f"  Step 4: list")
    list_result = json.loads(execute_tool("dynamodb_intake", {
        "operation": "list",
    }, session_id))
    list_count = list_result.get("count", 0)
    list_items = list_result.get("items", [])
    found_in_list = any(i.get("item_id") == item_id for i in list_items)
    list_ok = list_count >= 1 and found_in_list
    steps_passed.append(("list", list_ok))
    print(f"    count={list_count} found_in_list={found_in_list} {'PASS' if list_ok else 'FAIL'}")

    # Step 5: boto3 confirm
    print(f"  Step 5: boto3 get_item confirm")
    # execute_tool uses _extract_tenant_id which returns "demo-tenant" for our session
    effective_tenant = "demo-tenant"
    ddb = _boto3.resource("dynamodb", region_name="us-east-1")
    table = ddb.Table(table_name)
    boto3_ok = False
    try:
        resp = table.get_item(Key={"PK": f"INTAKE#{effective_tenant}", "SK": f"INTAKE#{item_id}"})
        ddb_item = resp.get("Item", {})
        boto3_ok = ddb_item.get("item_id") == item_id and ddb_item.get("status") == "reviewed"
        print(f"    item_id={ddb_item.get('item_id')} status={ddb_item.get('status')} PASS" if boto3_ok else f"    item={ddb_item} FAIL")
    except Exception as e:
        print(f"    boto3 error: {e} FAIL")
    steps_passed.append(("boto3_confirm", boto3_ok))

    # Step 6: Cleanup
    print(f"  Step 6: cleanup")
    try:
        table.delete_item(Key={"PK": f"INTAKE#{effective_tenant}", "SK": f"INTAKE#{item_id}"})
        print(f"    deleted PK=INTAKE#{effective_tenant} SK=INTAKE#{item_id}")
    except Exception as e:
        print(f"    cleanup error: {e}")

    # Summary
    passed = all(ok for _, ok in steps_passed)
    print(f"\n  Steps: {', '.join(f'{name}={'PASS' if ok else 'FAIL'}' for name, ok in steps_passed)}")
    print(f"  {'PASS' if passed else 'FAIL'} - DynamoDB Intake Operations (direct tool + boto3)")
    return passed


# ============================================================
# Test 18: CloudWatch Logs Operations (Direct Tool Call + boto3)
# ============================================================

async def test_18_cloudwatch_logs_ops():
    """Call execute_tool('cloudwatch_logs') directly, verify via boto3."""
    print("\n" + "=" * 70)
    print("TEST 18: CloudWatch Logs Operations (Direct Tool + boto3 Confirm)")
    print("=" * 70)

    import boto3 as _boto3

    session_id = "test-session-001"
    log_group = "/eagle/test-runs"

    steps_passed = []

    # Step 1: get_stream
    print(f"  Step 1: get_stream log_group={log_group}")
    stream_result = json.loads(execute_tool("cloudwatch_logs", {
        "operation": "get_stream",
        "log_group": log_group,
    }, session_id))
    streams = stream_result.get("streams", [])
    stream_ok = "error" not in stream_result and isinstance(streams, list)
    steps_passed.append(("get_stream", stream_ok))
    print(f"    streams={len(streams)} {'PASS' if stream_ok else 'FAIL'}")
    if streams:
        print(f"    latest_stream={streams[0].get('logStreamName', '?')}")

    # Step 2: recent
    print(f"  Step 2: recent log_group={log_group} limit=10")
    recent_result = json.loads(execute_tool("cloudwatch_logs", {
        "operation": "recent",
        "log_group": log_group,
        "limit": 10,
    }, session_id))
    events = recent_result.get("events", [])
    recent_ok = "error" not in recent_result and isinstance(events, list)
    steps_passed.append(("recent", recent_ok))
    print(f"    event_count={recent_result.get('event_count', 0)} {'PASS' if recent_ok else 'FAIL'}")

    # Step 3: search
    print(f"  Step 3: search filter_pattern='run_summary' limit=5")
    search_result = json.loads(execute_tool("cloudwatch_logs", {
        "operation": "search",
        "log_group": log_group,
        "filter_pattern": "run_summary",
        "limit": 5,
    }, session_id))
    search_events = search_result.get("events", [])
    search_ok = "error" not in search_result and isinstance(search_events, list)
    steps_passed.append(("search", search_ok))
    print(f"    matching_events={search_result.get('event_count', 0)} {'PASS' if search_ok else 'FAIL'}")

    # Step 4: boto3 confirm log group exists
    print(f"  Step 4: boto3 describe_log_groups confirm")
    logs_client = _boto3.client("logs", region_name="us-east-1")
    boto3_ok = False
    try:
        resp = logs_client.describe_log_groups(logGroupNamePrefix="/eagle")
        group_names = [g["logGroupName"] for g in resp.get("logGroups", [])]
        boto3_ok = log_group in group_names
        print(f"    log_groups={group_names} found={boto3_ok} {'PASS' if boto3_ok else 'FAIL'}")
    except Exception as e:
        print(f"    boto3 error: {e} FAIL")
    steps_passed.append(("boto3_confirm", boto3_ok))

    # Summary
    passed = all(ok for _, ok in steps_passed)
    print(f"\n  Steps: {', '.join(f'{name}={'PASS' if ok else 'FAIL'}' for name, ok in steps_passed)}")
    print(f"  {'PASS' if passed else 'FAIL'} - CloudWatch Logs Operations (direct tool + boto3)")
    return passed


# ============================================================
# Test 19: Document Generation (Direct Tool Call + boto3)
# ============================================================

async def test_19_document_generation():
    """Call execute_tool('create_document') for 3 doc types, verify via boto3."""
    print("\n" + "=" * 70)
    print("TEST 19: Document Generation (3 Doc Types + boto3 Confirm)")
    print("=" * 70)

    import boto3 as _boto3

    session_id = "test-session-001"
    bucket = "nci-documents"

    doc_tests = [
        {
            "doc_type": "sow",
            "title": "Test SOW - Lab Equipment",
            "data": {
                "description": "laboratory centrifuge equipment and installation services",
                "deliverables": ["Equipment delivery", "Installation report", "Training completion"],
            },
            "expect_in_content": "STATEMENT OF WORK",
            "min_word_count": 200,
        },
        {
            "doc_type": "igce",
            "title": "Test IGCE - Lab Equipment",
            "data": {
                "line_items": [
                    {"description": "Centrifuge Model A", "quantity": 2, "unit_price": 15000},
                    {"description": "Installation Service", "quantity": 1, "unit_price": 5000},
                    {"description": "Training Package", "quantity": 1, "unit_price": 3000},
                ],
            },
            "expect_in_content": "COST ESTIMATE",
            "expect_dollar": True,
        },
        {
            "doc_type": "acquisition_plan",
            "title": "Test AP - Lab Equipment",
            "data": {
                "estimated_value": "$300,000",
                "competition": "Full and Open Competition",
                "contract_type": "Firm-Fixed-Price",
                "description": "Laboratory centrifuge procurement for NCI research programs",
            },
            "expect_in_content": "ACQUISITION PLAN",
            "expect_far": True,
        },
    ]

    steps_passed = []
    s3_keys_to_cleanup = []

    for i, dt in enumerate(doc_tests, 1):
        print(f"\n  Step {i}: create_document doc_type={dt['doc_type']}")
        result = json.loads(execute_tool("create_document", {
            "doc_type": dt["doc_type"],
            "title": dt["title"],
            "data": dt["data"],
        }, session_id))

        content = result.get("content", "")
        word_count = result.get("word_count", 0)
        s3_key = result.get("s3_key", "")
        status = result.get("status", "")

        if s3_key:
            s3_keys_to_cleanup.append(s3_key)

        # Check expected content
        has_header = dt["expect_in_content"].upper() in content.upper()
        has_dollar = "$" in content if dt.get("expect_dollar") else True
        has_far = "far" in content.lower() or "FAR" in content if dt.get("expect_far") else True
        meets_word_count = word_count >= dt.get("min_word_count", 100)

        doc_ok = has_header and has_dollar and has_far and meets_word_count
        steps_passed.append((dt["doc_type"], doc_ok))
        print(f"    header={has_header} words={word_count} s3_status={status} {'PASS' if doc_ok else 'FAIL'}")

    # Step 4: boto3 confirm documents in S3
    print(f"\n  Step 4: boto3 list_objects_v2 confirm")
    s3 = _boto3.client("s3", region_name="us-east-1")
    boto3_ok = False
    try:
        # List documents under the test user's documents prefix
        # execute_tool uses _extract_user_id("test-session-001") which returns "demo-user"
        prefix = "eagle/demo-tenant/demo-user/documents/"
        resp = s3.list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=100)
        s3_objects = [o["Key"] for o in resp.get("Contents", [])]
        found_count = sum(1 for cleanup_key in s3_keys_to_cleanup if cleanup_key in s3_objects)
        boto3_ok = found_count == len(doc_tests)
        print(f"    expected={len(doc_tests)} found={found_count} {'PASS' if boto3_ok else 'FAIL'}")
    except Exception as e:
        print(f"    boto3 error: {e} FAIL")
    steps_passed.append(("boto3_confirm", boto3_ok))

    # Step 5: Cleanup
    print(f"\n  Step 5: cleanup {len(s3_keys_to_cleanup)} documents")
    for s3_key in s3_keys_to_cleanup:
        try:
            s3.delete_object(Bucket=bucket, Key=s3_key)
            print(f"    deleted {s3_key}")
        except Exception as e:
            print(f"    cleanup error for {s3_key}: {e}")

    # Summary
    passed = all(ok for _, ok in steps_passed)
    print(f"\n  Steps: {', '.join(f'{name}={'PASS' if ok else 'FAIL'}' for name, ok in steps_passed)}")
    print(f"  {'PASS' if passed else 'FAIL'} - Document Generation (3 doc types + boto3)")
    return passed


# ============================================================
# Test 20: CloudWatch End-to-End Verification
# ============================================================

async def test_20_cloudwatch_e2e_verification():
    """Query CloudWatch to confirm test events from this run exist."""
    print("\n" + "=" * 70)
    print("TEST 20: CloudWatch End-to-End Verification")
    print("=" * 70)

    import boto3 as _boto3

    log_group = "/eagle/test-runs"
    logs_client = _boto3.client("logs", region_name="us-east-1")

    steps_passed = []

    # Step 1: Describe log streams for this run
    print(f"  Step 1: describe_log_streams for {log_group}")
    try:
        resp = logs_client.describe_log_streams(
            logGroupName=log_group,
            orderBy="LastEventTime",
            descending=True,
            limit=5,
        )
        streams = resp.get("logStreams", [])
        has_streams = len(streams) > 0
        steps_passed.append(("describe_streams", has_streams))
        print(f"    streams_found={len(streams)} {'PASS' if has_streams else 'FAIL'}")
        for s in streams[:3]:
            print(f"      {s['logStreamName']}")
    except Exception as e:
        print(f"    error: {e} FAIL")
        steps_passed.append(("describe_streams", False))

    # Step 2: Get log events from the most recent stream
    print(f"  Step 2: get_log_events from latest stream")
    events = []
    if streams:
        latest_stream = streams[0]["logStreamName"]
        try:
            resp = logs_client.get_log_events(
                logGroupName=log_group,
                logStreamName=latest_stream,
                startFromHead=True,
            )
            events = resp.get("events", [])
            has_events = len(events) > 0
            steps_passed.append(("get_events", has_events))
            print(f"    stream={latest_stream} events={len(events)} {'PASS' if has_events else 'FAIL'}")
        except Exception as e:
            print(f"    error: {e} FAIL")
            steps_passed.append(("get_events", False))
    else:
        print(f"    no streams to query FAIL")
        steps_passed.append(("get_events", False))

    # Step 3: Parse events — check for proper structure
    print(f"  Step 3: parse events for structure")
    structured_count = 0
    for ev in events:
        try:
            payload = json.loads(ev.get("message", "{}"))
            if "type" in payload and "test_id" in payload and "status" in payload:
                structured_count += 1
            elif "type" in payload and payload["type"] == "run_summary":
                structured_count += 1
        except (json.JSONDecodeError, TypeError):
            pass
    parse_ok = structured_count > 0
    steps_passed.append(("parse_events", parse_ok))
    print(f"    structured_events={structured_count}/{len(events)} {'PASS' if parse_ok else 'FAIL'}")

    # Step 4: Check run_summary event tallies
    print(f"  Step 4: check run_summary event")
    summary_ok = False
    for ev in events:
        try:
            payload = json.loads(ev.get("message", "{}"))
            if payload.get("type") == "run_summary":
                total = payload.get("total_tests", 0)
                p = payload.get("passed", 0)
                s = payload.get("skipped", 0)
                f = payload.get("failed", 0)
                tally_match = (p + s + f) == total
                summary_ok = tally_match and total > 0
                print(f"    total={total} passed={p} skipped={s} failed={f} tally_match={tally_match} {'PASS' if summary_ok else 'FAIL'}")
                break
        except (json.JSONDecodeError, TypeError):
            pass
    if not summary_ok and not any(True for ev in events if "run_summary" in ev.get("message", "")):
        print(f"    no run_summary event found in latest stream FAIL")
    steps_passed.append(("run_summary", summary_ok))

    # Summary
    passed = all(ok for _, ok in steps_passed)
    print(f"\n  Steps: {', '.join(f'{name}={'PASS' if ok else 'FAIL'}' for name, ok in steps_passed)}")
    print(f"  {'PASS' if passed else 'FAIL'} - CloudWatch End-to-End Verification")
    return passed


# ============================================================
# Test 28: SDK Skill→Subagent Orchestration
# ============================================================

async def test_28_sdk_skill_subagent_orchestration():
    """Test the sdk_agentic_service skill→subagent pattern.

    Validates:
    1. build_skill_agents() builds AgentDefinitions from SKILL_CONSTANTS
    2. build_supervisor_prompt() generates proper routing prompt
    3. sdk_query() supervisor delegates to subagents via Task tool
    4. Each subagent runs in its own context window (parent_tool_use_id)
    """
    print("\n" + "=" * 70)
    print("TEST 28: SDK Skill→Subagent Orchestration")
    print("=" * 70)

    from sdk_agentic_service import (
        build_skill_agents,
        build_supervisor_prompt,
        sdk_query,
        SKILL_AGENT_REGISTRY,
    )

    # Step 1: Validate build_skill_agents()
    print("  Step 1: build_skill_agents()")
    agents = build_skill_agents(model=MODEL, tier="advanced")
    agent_names = list(agents.keys())
    print(f"    Built {len(agents)} agents: {agent_names}")

    expected_agents = {"oa-intake", "legal-counsel", "market-intelligence",
                       "tech-translator", "public-interest", "document-generator"}
    agents_ok = set(agent_names) == expected_agents
    print(f"    All 6 skills mapped: {agents_ok}")

    # Verify each AgentDefinition has prompt content
    for name, agent in agents.items():
        has_prompt = len(agent.prompt) > 50
        print(f"    {name}: prompt_len={len(agent.prompt)}, has_content={has_prompt}")

    # Step 2: Validate build_supervisor_prompt()
    print("\n  Step 2: build_supervisor_prompt()")
    sup_prompt = build_supervisor_prompt(
        tenant_id="test-tenant", user_id="test-user", tier="premium"
    )
    print(f"    Supervisor prompt length: {len(sup_prompt)} chars")

    # Check supervisor prompt references all subagent names
    sup_references = all(name in sup_prompt for name in agent_names)
    print(f"    References all agents: {sup_references}")

    # Check supervisor prompt does NOT contain skill content
    # (skill content should only be in subagent prompts, not supervisor)
    skill_content_leaked = any(
        "Five-Phase" in sup_prompt or
        "Think Like Trish" in sup_prompt or
        "GAO protest" in sup_prompt
        for _ in [1]
    )
    print(f"    Skill content isolated (not in supervisor): {not skill_content_leaked}")

    # Step 3: Run sdk_query() with limited skills for cost control
    print("\n  Step 3: sdk_query() — supervisor → subagent delegation")
    print(f"    Model: {MODEL}")
    print(f"    Skills: oa-intake, legal-counsel (2 of 6 for cost control)")

    collector = TraceCollector()

    try:
        async for message in sdk_query(
            prompt=(
                "We need to procure IT modernization services for $350K. "
                "Run intake analysis and then check legal risks."
            ),
            tenant_id="test-tenant",
            user_id="test-user",
            tier="advanced",
            model=MODEL,
            skill_names=["oa-intake", "legal-counsel"],
            max_turns=10,
        ):
            collector.process(message, indent=2)
    except ExceptionGroup as eg:
        # Handle MCP cleanup race on Windows
        real_errors = [e for e in eg.exceptions
                       if "CLIConnection" not in type(e).__name__]
        if real_errors:
            raise ExceptionGroup("SDK errors", real_errors)
        print("    (MCP cleanup race on Windows — non-fatal)")
    except Exception as e:
        print(f"    sdk_query() error: {type(e).__name__}: {e}")

    print()
    summary = collector.summary()
    print(f"  --- Results ---")
    print(f"  Messages: {summary['total_messages']}")
    print(f"  Tool use blocks: {summary['tool_use_blocks']}")
    print(f"  Tokens: {summary['total_input_tokens']} in / {summary['total_output_tokens']} out")
    print(f"  Cost: ${summary['total_cost_usd']:.6f}")

    # Check for subagent invocations via Task tool
    subagent_calls = [t for t in collector.tool_use_blocks if t["tool"] == "Task"]
    subagent_types = [
        t["input"].get("subagent_type", t["input"].get("description", "?"))
        for t in subagent_calls
    ]

    print(f"\n  Subagent invocations: {len(subagent_calls)}")
    for st in subagent_types:
        print(f"    -> {st}")

    # Check response content for skill-specific knowledge
    all_text = " ".join(collector.text_blocks).lower()
    for msg_entry in collector.messages:
        msg = msg_entry["message"]
        if hasattr(msg, "result") and msg.result:
            all_text += " " + msg.result.lower()

    indicators = {
        "agents_built": agents_ok,
        "supervisor_prompt_valid": sup_references and not skill_content_leaked,
        "subagent_delegation": len(subagent_calls) >= 1,
        "intake_or_legal_invoked": any(
            "intake" in st.lower() or "legal" in st.lower()
            for st in subagent_types
        ),
        "response_has_content": summary["total_messages"] > 2,
    }

    print(f"\n  Indicators:")
    for indicator, found in indicators.items():
        print(f"    {indicator}: {found}")

    indicators_found = sum(1 for v in indicators.values() if v)
    passed = indicators_found >= 3
    print(f"\n  Indicators: {indicators_found}/5")
    print(f"  {'PASS' if passed else 'FAIL'} - SDK Skill→Subagent Orchestration")
    return passed


# ============================================================
# Main
# ============================================================

class CapturingStream:
    """Captures stdout while still printing."""

    def __init__(self, original):
        self.original = original
        self.lines = []
        self._current_test = None
        self.per_test_logs = {}

    def write(self, text):
        self.original.write(text)
        if text.strip():
            self.lines.append(text.rstrip())
            if self._current_test:
                if self._current_test not in self.per_test_logs:
                    self.per_test_logs[self._current_test] = []
                self.per_test_logs[self._current_test].append(text.rstrip())

    def flush(self):
        self.original.flush()

    def start_test(self, test_id):
        self._current_test = test_id

    def end_test(self):
        self._current_test = None


# ============================================================
# CloudWatch Telemetry Emission
# ============================================================

LOG_GROUP = "/eagle/test-runs"

def emit_to_cloudwatch(trace_output: dict, results: dict):
    """Emit structured test results to CloudWatch Logs.

    Non-fatal: catches all exceptions so local trace files are always the fallback.
    Uses /eagle/test-runs log group with a per-run log stream.
    """
    try:
        import boto3
        client = boto3.client("logs", region_name=os.environ.get("AWS_REGION", "us-east-1"))

        # Ensure log group exists
        try:
            client.create_log_group(logGroupName=LOG_GROUP)
        except client.exceptions.ResourceAlreadyExistsException:
            pass

        # Create a per-run log stream: run-<timestamp>
        run_ts = trace_output.get("timestamp", datetime.now(timezone.utc).isoformat())
        stream_name = f"run-{run_ts.replace(':', '-').replace('+', 'Z')}"
        try:
            client.create_log_stream(logGroupName=LOG_GROUP, logStreamName=stream_name)
        except client.exceptions.ResourceAlreadyExistsException:
            pass

        # Build log events: one per test + one summary
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        events = []

        test_names = {
            1: "1_session_creation", 2: "2_session_resume",
            3: "3_trace_observation", 4: "4_subagent_orchestration",
            5: "5_cost_tracking", 6: "6_tier_gated_tools",
            7: "7_skill_loading", 8: "8_subagent_tool_tracking",
            9: "9_oa_intake_workflow", 10: "10_legal_counsel_skill",
            11: "11_market_intelligence_skill", 12: "12_tech_review_skill",
            13: "13_public_interest_skill", 14: "14_document_generator_skill",
            15: "15_supervisor_multi_skill_chain",
            16: "16_s3_document_ops", 17: "17_dynamodb_intake_ops",
            18: "18_cloudwatch_logs_ops", 19: "19_document_generation",
            20: "20_cloudwatch_e2e_verification",
            21: "21_uc02_micro_purchase",
            22: "22_uc03_option_exercise",
            23: "23_uc04_contract_modification",
            24: "24_uc05_co_package_review",
            25: "25_uc07_contract_closeout",
            26: "26_uc08_shutdown_notification",
            27: "27_uc09_score_consolidation",
            28: "28_sdk_skill_subagent_orchestration",
        }

        for test_id_str, test_data in trace_output.get("results", {}).items():
            test_id = int(test_id_str)
            event = {
                "type": "test_result",
                "test_id": test_id,
                "test_name": test_names.get(test_id, f"test_{test_id}"),
                "status": test_data.get("status", "unknown"),
                "log_lines": len(test_data.get("logs", [])),
                "run_timestamp": run_ts,
            }
            events.append({
                "timestamp": now_ms + test_id,
                "message": json.dumps(event),
            })

        # Summary event
        passed = sum(1 for r in results.values() if r is True)
        skipped = sum(1 for r in results.values() if r is None)
        failed = sum(1 for r in results.values() if r is not True and r is not None)

        summary = {
            "type": "run_summary",
            "run_timestamp": run_ts,
            "total_tests": len(results),
            "passed": passed,
            "skipped": skipped,
            "failed": failed,
            "pass_rate": round(passed / max(len(results), 1) * 100, 1),
        }
        events.append({
            "timestamp": now_ms + 100,
            "message": json.dumps(summary),
        })

        # Sort events by timestamp (required by CloudWatch)
        events.sort(key=lambda e: e["timestamp"])

        client.put_log_events(
            logGroupName=LOG_GROUP,
            logStreamName=stream_name,
            logEvents=events,
        )
        print(f"CloudWatch: emitted {len(events)} events to {LOG_GROUP}/{stream_name}")

        # Local telemetry mirror
        _repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        telemetry_dir = os.path.join(_repo_root, "data", "eval", "telemetry")
        os.makedirs(telemetry_dir, exist_ok=True)
        local_ts = run_ts.replace(":", "-").replace("+", "Z")
        with open(os.path.join(telemetry_dir, f"cw-{local_ts}.json"), "w") as f:
            json.dump(events, f, indent=2)

    except Exception as e:
        print(f"CloudWatch: emission failed (non-fatal): {type(e).__name__}: {e}")


async def _run_test(test_id: int, capture: "CapturingStream", session_id: str = None,
                    recorder: "BrowserRecorder | None" = None):
    """Run a single test by ID, with capture, error handling, and optional video.

    Returns (result_key, result_value, session_id_or_None).
    """
    TEST_REGISTRY = {
        1: ("1_session_creation", test_1_session_creation),
        2: ("2_session_resume", None),  # special: needs session_id
        3: ("3_trace_observation", test_3_trace_observation),
        4: ("4_subagent_orchestration", test_4_subagent_orchestration),
        5: ("5_cost_tracking", test_5_cost_tracking),
        6: ("6_tier_gated_tools", test_6_tier_gated_tools),
        7: ("7_skill_loading", test_7_skill_loading),
        8: ("8_subagent_tool_tracking", test_8_subagent_tool_tracking),
        9: ("9_oa_intake_workflow", test_9_oa_intake_workflow),
        10: ("10_legal_counsel_skill", test_10_legal_counsel_skill),
        11: ("11_market_intelligence_skill", test_11_market_intelligence_skill),
        12: ("12_tech_review_skill", test_12_tech_review_skill),
        13: ("13_public_interest_skill", test_13_public_interest_skill),
        14: ("14_document_generator_skill", test_14_document_generator_skill),
        15: ("15_supervisor_multi_skill_chain", test_15_supervisor_multi_skill_chain),
        16: ("16_s3_document_ops", test_16_s3_document_ops),
        17: ("17_dynamodb_intake_ops", test_17_dynamodb_intake_ops),
        18: ("18_cloudwatch_logs_ops", test_18_cloudwatch_logs_ops),
        19: ("19_document_generation", test_19_document_generation),
        20: ("20_cloudwatch_e2e_verification", test_20_cloudwatch_e2e_verification),
        21: ("21_uc02_micro_purchase", test_21_uc02_micro_purchase),
        22: ("22_uc03_option_exercise", test_22_uc03_option_exercise),
        23: ("23_uc04_contract_modification", test_23_uc04_contract_modification),
        24: ("24_uc05_co_package_review", test_24_uc05_co_package_review),
        25: ("25_uc07_contract_closeout", test_25_uc07_contract_closeout),
        26: ("26_uc08_shutdown_notification", test_26_uc08_shutdown_notification),
        27: ("27_uc09_score_consolidation", test_27_uc09_score_consolidation),
        28: ("28_sdk_skill_subagent_orchestration", test_28_sdk_skill_subagent_orchestration),
    }

    result_key, test_fn = TEST_REGISTRY[test_id]
    capture.start_test(test_id)
    new_session_id = None

    # Start video recording if recorder is active and test has a prompt
    rec_ctx = None
    if recorder and recorder.has_recording(test_id):
        try:
            rec_ctx = await recorder.begin_test(test_id)
        except Exception as e:
            print(f"  [recorder] Failed to start recording for test {test_id}: {e}")

    try:
        if test_id == 1:
            passed, new_session_id = await test_fn()
            result_val = passed
        elif test_id == 2:
            result_val = await test_2_session_resume(session_id)
        else:
            result_val = await test_fn()
    except Exception as e:
        print(f"  ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        result_val = False

    # Wait for chat response and finalize video after test completes
    if rec_ctx:
        try:
            await recorder.wait_for_response(rec_ctx)
            await recorder.end_test(rec_ctx)
        except Exception as e:
            print(f"  [recorder] Failed to finalize recording for test {test_id}: {e}")

    capture.end_test()
    return result_key, result_val, new_session_id


async def main():
    # Parse which tests to run
    if _args.tests:
        selected_tests = sorted(set(int(t.strip()) for t in _args.tests.split(",")))
    else:
        selected_tests = list(range(1, 29))

    # Set up video recorder (if --record-video)
    recorder = None
    if _args.record_video:
        from browser_recorder import BrowserRecorder
        recorder = BrowserRecorder(
            video_dir=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "eval", "videos"),
            base_url=_args.base_url,
            headless=not _args.headed,
            auth_email=_args.auth_email,
            auth_password=_args.auth_password,
        )
        await recorder.start()

    # Set up capturing stream
    capture = CapturingStream(sys.stdout)
    sys.stdout = capture

    print("=" * 70)
    print("EAGLE SDK Evaluation: Multi-Tenant Orchestrator")
    print(f"Time: {datetime.now(timezone.utc).isoformat()}")
    print(f"Model: {MODEL}   {'(--async)' if _args.run_async else '(sequential)'}")
    print(f"Tests: {','.join(str(t) for t in selected_tests)}")
    if recorder:
        print(f"Video: recording UC diagrams → data/eval/videos/")
    print(f"Backend: AWS Bedrock (CLAUDE_CODE_USE_BEDROCK=1)")
    print(f"SDK: claude-agent-sdk >= 0.1.29")
    print("=" * 70)

    results = {}
    session_id = None

    # --- Phase A: sequential tests (1, 2 depend on each other) ---
    sequential_tests = [t for t in selected_tests if t <= 2]
    parallel_tests = [t for t in selected_tests if t > 2]

    for tid in sequential_tests:
        key, val, sid = await _run_test(tid, capture, session_id=session_id, recorder=recorder)
        results[key] = val
        if sid:
            session_id = sid

    # --- Phase B: independent tests (3-27) ---
    if _args.run_async and len(parallel_tests) > 1:
        print(f"\n  Running {len(parallel_tests)} tests concurrently (--async)...")

        async def _wrapped(tid):
            return await _run_test(tid, capture, session_id=session_id, recorder=recorder)

        tasks = [asyncio.create_task(_wrapped(tid)) for tid in parallel_tests]
        completed = await asyncio.gather(*tasks, return_exceptions=True)

        for item in completed:
            if isinstance(item, Exception):
                print(f"  ASYNC ERROR: {type(item).__name__}: {item}")
            else:
                key, val, _ = item
                results[key] = val
    else:
        for tid in parallel_tests:
            key, val, _ = await _run_test(tid, capture, session_id=session_id, recorder=recorder)
            results[key] = val

    # Tear down recorder
    if recorder:
        sys.stdout = capture.original
        await recorder.stop()
        sys.stdout = capture

    # Summary
    print("\n" + "=" * 70)
    print("EAGLE SDK EVALUATION SUMMARY")
    print("=" * 70)

    print("\n  Architecture: Claude SDK → Bedrock Layer 1 (stateless multi-turn)")
    print(f"  Session resume pattern: query(resume=session_id)")
    print()

    for name, result in results.items():
        if result is True:
            status = "PASS"
        elif result is None:
            status = "SKIP"
        else:
            status = "FAIL"
        print(f"  {name}: {status}")

    passed = sum(1 for r in results.values() if r is True)
    skipped = sum(1 for r in results.values() if r is None)
    failed = sum(1 for r in results.values() if r is not True and r is not None)
    print(f"\n  {passed} passed, {skipped} skipped, {failed} failed")

    print("\n  Frontend integration readiness:")
    print(f"    Session management (create/resume): {'Ready' if results.get('1_session_creation') and results.get('2_session_resume') else 'Needs work'}")
    print(f"    Trace events (ThinkingBlock/ToolUseBlock): {'Ready' if results.get('3_trace_observation') else 'Needs work'}")
    print(f"    Subagent traces (agent_log events): {'Ready' if results.get('4_subagent_orchestration') else 'Needs work'}")
    print(f"    Cost ticker (ResultMessage.usage): {'Ready' if results.get('5_cost_tracking') else 'Needs work'}")
    print(f"    Tier-gated tools (MCP): {'Ready' if results.get('6_tier_gated_tools') else 'Needs work'}")
    print(f"    Skill loading (system_prompt): {'Ready' if results.get('7_skill_loading') else 'Needs work'}")
    print(f"    Subagent tool tracking: {'Ready' if results.get('8_subagent_tool_tracking') else 'Needs work'}")
    print(f"    OA Intake workflow: {'Ready' if results.get('9_oa_intake_workflow') else 'Needs work'}")
    print(f"\n  EAGLE Skill Validation:")
    print(f"    Legal Counsel skill: {'Ready' if results.get('10_legal_counsel_skill') else 'Needs work'}")
    print(f"    Market Intelligence skill: {'Ready' if results.get('11_market_intelligence_skill') else 'Needs work'}")
    print(f"    Tech Review skill: {'Ready' if results.get('12_tech_review_skill') else 'Needs work'}")
    print(f"    Public Interest skill: {'Ready' if results.get('13_public_interest_skill') else 'Needs work'}")
    print(f"    Document Generator skill: {'Ready' if results.get('14_document_generator_skill') else 'Needs work'}")
    print(f"    Supervisor Multi-Skill Chain: {'Ready' if results.get('15_supervisor_multi_skill_chain') else 'Needs work'}")
    print(f"\n  AWS Tool Integration:")
    print(f"    S3 Document Operations: {'Ready' if results.get('16_s3_document_ops') else 'Needs work'}")
    print(f"    DynamoDB Intake Operations: {'Ready' if results.get('17_dynamodb_intake_ops') else 'Needs work'}")
    print(f"    CloudWatch Logs Operations: {'Ready' if results.get('18_cloudwatch_logs_ops') else 'Needs work'}")
    print(f"    Document Generation (3 types): {'Ready' if results.get('19_document_generation') else 'Needs work'}")
    print(f"    CloudWatch E2E Verification: {'Ready' if results.get('20_cloudwatch_e2e_verification') else 'Needs work'}")
    print(f"\n  UC Workflow Validation:")
    print(f"    UC-02 Micro-Purchase (<$15K): {'Ready' if results.get('21_uc02_micro_purchase') else 'Needs work'}")
    print(f"    UC-03 Option Exercise: {'Ready' if results.get('22_uc03_option_exercise') else 'Needs work'}")
    print(f"    UC-04 Contract Modification: {'Ready' if results.get('23_uc04_contract_modification') else 'Needs work'}")
    print(f"    UC-05 CO Package Review: {'Ready' if results.get('24_uc05_co_package_review') else 'Needs work'}")
    print(f"    UC-07 Contract Close-Out: {'Ready' if results.get('25_uc07_contract_closeout') else 'Needs work'}")
    print(f"    UC-08 Shutdown Notification: {'Ready' if results.get('26_uc08_shutdown_notification') else 'Needs work'}")
    print(f"    UC-09 Score Consolidation: {'Ready' if results.get('27_uc09_score_consolidation') else 'Needs work'}")
    print(f"\n  SDK Architecture:")
    print(f"    Skill→Subagent Orchestration: {'Ready' if results.get('28_sdk_skill_subagent_orchestration') else 'Needs work'}")

    # Restore stdout
    sys.stdout = capture.original

    # Write per-test trace logs to JSON for the dashboard
    run_ts = datetime.now(timezone.utc).isoformat()
    trace_output = {
        "timestamp": run_ts,
        "run_id": f"run-{run_ts.replace(':', '-').replace('+', 'Z')}",
        "total_tests": len(results),
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "results": {},
    }
    for test_id, log_lines in capture.per_test_logs.items():
        result_key = {
            1: "1_session_creation",
            2: "2_session_resume",
            3: "3_trace_observation",
            4: "4_subagent_orchestration",
            5: "5_cost_tracking",
            6: "6_tier_gated_tools",
            7: "7_skill_loading",
            8: "8_subagent_tool_tracking",
            9: "9_oa_intake_workflow",
            10: "10_legal_counsel_skill",
            11: "11_market_intelligence_skill",
            12: "12_tech_review_skill",
            13: "13_public_interest_skill",
            14: "14_document_generator_skill",
            15: "15_supervisor_multi_skill_chain",
            16: "16_s3_document_ops",
            17: "17_dynamodb_intake_ops",
            18: "18_cloudwatch_logs_ops",
            19: "19_document_generation",
            20: "20_cloudwatch_e2e_verification",
            21: "21_uc02_micro_purchase",
            22: "22_uc03_option_exercise",
            23: "23_uc04_contract_modification",
            24: "24_uc05_co_package_review",
            25: "25_uc07_contract_closeout",
            26: "26_uc08_shutdown_notification",
            27: "27_uc09_score_consolidation",
            28: "28_sdk_skill_subagent_orchestration",
        }.get(test_id, str(test_id))

        result_val = results.get(result_key)
        status = "pass" if result_val is True else ("skip" if result_val is None else "fail")

        trace_output["results"][str(test_id)] = {
            "status": status,
            "logs": log_lines,
        }

    _repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    _eval_results_dir = os.path.join(_repo_root, "data", "eval", "results")
    os.makedirs(_eval_results_dir, exist_ok=True)
    run_ts_file = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    trace_file = os.path.join(_eval_results_dir, f"run-{run_ts_file}.json")
    with open(trace_file, "w", encoding="utf-8") as f:
        json.dump(trace_output, f, indent=2)
    latest_file = os.path.join(_eval_results_dir, "latest.json")
    shutil.copy2(trace_file, latest_file)
    print(f"\nTrace logs written to: {trace_file}")
    print(f"Latest copy: {latest_file}")

    # Emit to CloudWatch (non-fatal)
    emit_to_cloudwatch(trace_output, results)

    # Publish metrics + archive to S3 (non-fatal, no-op without boto3)
    if _HAS_AWS_PUBLISHER:
        publish_eval_metrics(results, run_ts_file)
        archive_results_to_s3(trace_file, run_ts_file)
        archive_videos_to_s3(
            os.path.join(_repo_root, "data", "eval", "videos"), run_ts_file
        )

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
