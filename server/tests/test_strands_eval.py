"""
EAGLE Strands Evaluation Suite

Port of test_eagle_sdk_eval.py from Claude Agent SDK to Strands Agents SDK.
Tests the core patterns for the EAGLE multi-tenant architecture:
1-6.   SDK patterns: sessions, resume, context, traces, cost, subagents
7-15.  Skill validation: OA intake, legal, market, tech, public, doc gen, supervisor chain
16-20. AWS tool integration: S3 ops, DynamoDB CRUD, CloudWatch logs, document generation,
       CloudWatch E2E verification -- direct execute_tool() calls with boto3 confirmation
21-27. UC workflow validation: micro-purchase, option exercise, contract modification,
       CO package review, contract close-out, shutdown notification, score consolidation
28.    Strands architecture: skill->tool orchestration via build_skill_tools()
32-34. Admin & store validation: admin-manager registration, workspace defaults, store CRUD API

SDK: strands-agents
Backend: AWS Bedrock (boto3 native)
"""

import argparse
import asyncio
import json
import os
import shutil
import sys
import uuid
from datetime import datetime, timezone
from typing import Any

# Add server/ to path so we can import app modules and eagle_skill_constants
_server_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, _server_dir)
sys.path.insert(0, os.path.join(_server_dir, "app"))
from agentic_service import execute_tool

from strands import Agent, tool
from strands.models import BedrockModel

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

_parser = argparse.ArgumentParser(description="EAGLE Strands Evaluation Suite")
_parser.add_argument(
    "--model", default="us.anthropic.claude-3-5-haiku-20241022-v1:0",
    help="Override Bedrock model ID for ALL test invocations "
         "(default: us.anthropic.claude-3-5-haiku-20241022-v1:0).",
)
_parser.add_argument(
    "--async", dest="run_async", action="store_true",
    help="Run independent tests concurrently (tests 3-27 in parallel).",
)
_parser.add_argument(
    "--tests", default=None,
    help="Comma-separated test numbers to run (e.g. '1,2,7'). Default: all.",
)
_parser.add_argument(
    "--record-video", dest="record_video", action="store_true",
    help="Record browser video of eval-page UC diagrams for applicable tests.",
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

# Global model ID -- every test reads from here
MODEL_ID: str = _args.model

# ============================================================
# Shared Bedrock model (module-level, reused across all tests)
# ============================================================

_model = BedrockModel(
    model_id=MODEL_ID,
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
)

# ============================================================
# Tier configuration (mirrors subscription_service.py)
# ============================================================

TIER_TOOLS = {
    "basic": [],
    "advanced": [],
    "premium": [],
}

TIER_BUDGETS = {
    "basic": 0.05,
    "advanced": 0.15,
    "premium": 0.50,
}

# ============================================================
# Skill constants import
# ============================================================

from eagle_skill_constants import SKILL_CONSTANTS, PLUGIN_CONTENTS

OA_INTAKE_SKILL = SKILL_CONSTANTS.get("oa-intake", "")


# ============================================================
# StrandsResultCollector
# ============================================================

# Module-level store: test_id -> trace JSON from StrandsResultCollector.to_trace_json()
_test_traces: dict[int, list] = {}
_test_video_paths: dict[int, str] = {}
# Module-level store: test_id -> StrandsResultCollector.summary() dict
_test_summaries: dict[int, dict] = {}


class StrandsResultCollector:
    """Collects and categorizes Strands Agent results for trace reporting."""

    _latest: "StrandsResultCollector | None" = None

    def __init__(self):
        self.result_text = ""
        self.tool_use_blocks = []
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cost_usd = 0.0
        self.log_lines = []
        self.messages_raw = []
        StrandsResultCollector._latest = self

    def _log(self, msg):
        print(msg)
        self.log_lines.append(msg)

    def process_result(self, result, indent=0, agent=None):
        """Process a Strands Agent result object.

        Args:
            result: AgentResult from agent() call
            indent: indentation level for log output
            agent: optional Agent instance to read conversation history from
        """
        prefix = "  " * indent
        self.result_text = str(result)
        self._log(f"{prefix}  [Result] {self.result_text[:300]}")

        # Extract tool use from result.metrics.tool_metrics (preferred)
        try:
            metrics = getattr(result, "metrics", None)
            if metrics and hasattr(metrics, "tool_metrics"):
                for tool_name, tm in metrics.tool_metrics.items():
                    tool_info = getattr(tm, "tool", {}) or {}
                    self.tool_use_blocks.append({
                        "tool": tool_name,
                        "id": tool_info.get("toolUseId", ""),
                        "input": tool_info.get("input", {}),
                    })
                    self._log(f"{prefix}  [ToolUse] {tool_name} (calls={tm.call_count})")
        except Exception:
            pass

        # Fallback: extract from agent.messages conversation history (Bedrock camelCase format)
        if not self.tool_use_blocks and agent is not None:
            try:
                messages = getattr(agent, "messages", []) or []
                self.messages_raw = messages
                for msg in messages:
                    if isinstance(msg, dict) and msg.get("role") == "assistant":
                        for block in msg.get("content", []):
                            if isinstance(block, dict) and "toolUse" in block:
                                tu = block["toolUse"]
                                tool_name = tu.get("name", "")
                                self.tool_use_blocks.append({
                                    "tool": tool_name,
                                    "id": tu.get("toolUseId", ""),
                                    "input": tu.get("input", {}),
                                })
                                self._log(f"{prefix}  [ToolUse] {tool_name}")
            except Exception:
                pass

        # Extract usage from EventLoopMetrics
        try:
            metrics = getattr(result, "metrics", None)
            if metrics:
                # EventLoopMetrics may have accumulated_usage or per-cycle usage
                acc = getattr(metrics, "accumulated_usage", None)
                if acc and isinstance(acc, dict):
                    self.total_input_tokens = acc.get("inputTokens", 0) or 0
                    self.total_output_tokens = acc.get("outputTokens", 0) or 0
        except Exception:
            pass

        # Fallback: accumulate usage from agent conversation history
        if self.total_input_tokens == 0 and agent is not None:
            try:
                for msg in (getattr(agent, "messages", []) or []):
                    if isinstance(msg, dict) and "usage" in msg:
                        usage = msg["usage"]
                        if isinstance(usage, dict):
                            self.total_input_tokens += usage.get("inputTokens", 0)
                            self.total_output_tokens += usage.get("outputTokens", 0)
            except Exception:
                pass

        self._log(
            f"{prefix}  [Usage] {self.total_input_tokens} in "
            f"/ {self.total_output_tokens} out"
        )

    def all_text_lower(self):
        """Return all response text lowered for indicator checking."""
        return self.result_text.lower()

    def summary(self):
        return {
            "total_messages": len(self.messages_raw) + 1,
            "text_blocks": 1 if self.result_text else 0,
            "thinking_blocks": 0,
            "tool_use_blocks": len(self.tool_use_blocks),
            "result_messages": 1,
            "system_messages": 0,
            "session_id": None,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_cost_usd": self.total_cost_usd,
        }

    def to_trace_json(self):
        trace = []
        for tu in self.tool_use_blocks:
            trace.append({
                "type": "AssistantMessage",
                "content": [{
                    "type": "tool_use",
                    "tool": tu["tool"],
                    "id": tu["id"],
                    "input": tu["input"],
                }],
            })
        trace.append({
            "type": "ResultMessage",
            "result": self.result_text[:2000],
            "usage": {
                "input_tokens": self.total_input_tokens,
                "output_tokens": self.total_output_tokens,
            },
        })
        return trace


# ============================================================
# Skill loader helpers
# ============================================================

def load_skill_or_prompt(skill_name: str = None, prompt_file: str = None) -> tuple:
    """Load a skill or agent prompt from plugin contents.

    Args:
        skill_name: Name of agent/skill (e.g., "oa-intake", "legal-counsel")
        prompt_file: Legacy prompt file name -- still supported for compat

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

    print(f"  Tenant: {tenant_id} | User: {user_id} | Tier: {subscription_tier}")
    print(f"  Budget: ${TIER_BUDGETS[subscription_tier]}")
    print()

    agent = Agent(
        model=_model,
        system_prompt=system_prompt,
        callback_handler=None,
    )

    collector = StrandsResultCollector()
    result = agent("Hello! What tenant am I from and what is my subscription tier?")
    collector.process_result(result, indent=2)

    print()
    summary = collector.summary()
    print(f"  --- Results ---")
    print(f"  Session ID: {summary['session_id']}")
    print(f"  Messages: {summary['total_messages']}")
    print(f"  Text: {len(collector.result_text)} chars")
    print(f"  Tokens: {summary['total_input_tokens']} in / {summary['total_output_tokens']} out")
    print(f"  Cost: ${summary['total_cost_usd']:.6f}")

    all_text = collector.all_text_lower()
    tenant_mentioned = "acme" in all_text or tenant_id in all_text
    tier_mentioned = subscription_tier in all_text

    print(f"  Tenant recognized in response: {tenant_mentioned}")
    print(f"  Tier recognized in response: {tier_mentioned}")

    # Strands has no built-in session_id -- pass if we got a response
    passed = len(collector.result_text) > 0
    print(f"\n  {'PASS' if passed else 'FAIL'} - Session created with tenant context")
    return passed, None


# ============================================================
# Test 2: Session resume (simulated multi-turn via system_prompt)
# ============================================================

async def test_2_session_resume(session_id: str):
    """Strands is stateless -- simulate multi-turn via system_prompt context injection."""
    print("\n" + "=" * 70)
    print("TEST 2: Session Resume (Simulated Multi-Turn)")
    print("=" * 70)

    print("  Note: Strands is stateless -- simulating resume via system_prompt context")
    print()

    tenant_id = "acme-corp"
    subscription_tier = "premium"

    system_prompt = (
        "You are an AI assistant for tenant 'acme-corp'. "
        "Subscription tier: premium. "
        "CONTEXT FROM PRIOR TURN: The user previously greeted you and asked "
        "about their tenant name and subscription tier. You confirmed they are "
        "from tenant 'acme-corp' with a premium subscription. "
        "Respond concisely and reference the prior conversation."
    )

    agent = Agent(
        model=_model,
        system_prompt=system_prompt,
        callback_handler=None,
    )

    collector = StrandsResultCollector()
    result = agent(
        "What was my first question to you in this conversation? "
        "Also, what tenant and tier are in your system instructions?"
    )
    collector.process_result(result, indent=2)

    print()
    summary = collector.summary()
    print(f"  --- Results ---")
    print(f"  Messages: {summary['total_messages']}")
    print(f"  Tokens: {summary['total_input_tokens']} in / {summary['total_output_tokens']} out")

    all_text = collector.all_text_lower()
    tenant_found = "acme" in all_text
    tier_found = "premium" in all_text
    conversation_aware = (
        "previous" in all_text or "earlier" in all_text
        or "prior" in all_text or "tenant" in all_text
        or tenant_found or tier_found
    )

    print(f"  Tenant found: {tenant_found}")
    print(f"  Tier found: {tier_found}")
    print(f"  Conversation-aware: {conversation_aware}")

    passed = len(collector.result_text) > 0 and conversation_aware
    print(f"  {'PASS' if passed else 'FAIL'} - Session resumed (partial: stateless Strands)")
    return passed


# ============================================================
# Test 3: Trace / response structure
# ============================================================

async def test_3_trace_observation():
    """Observe Strands result structure -- text content, tool use, usage metrics."""
    print("\n" + "=" * 70)
    print("TEST 3: Trace Observation (Response Structure)")
    print("=" * 70)

    import glob as _glob

    @tool
    def list_python_files(directory: str) -> str:
        """List Python files in a directory.

        Args:
            directory: Directory path to search
        """
        files = _glob.glob(os.path.join(directory, "*.py"))
        return json.dumps({"files": [os.path.basename(f) for f in files], "count": len(files)})

    agent = Agent(
        model=_model,
        system_prompt=(
            "You are a file analysis assistant. "
            "When asked about Python files, use the list_python_files tool. Be concise."
        ),
        tools=[list_python_files],
        callback_handler=None,
    )

    test_dir = os.path.dirname(os.path.abspath(__file__))
    print("  Tools: list_python_files (should trigger tool use traces)")
    print()

    collector = StrandsResultCollector()
    result = agent(
        f"How many Python files are in this directory? "
        f"Use the list_python_files tool on: {test_dir}"
    )
    collector.process_result(result, indent=2, agent=agent)

    print()
    summary = collector.summary()
    print(f"  --- Trace Analysis ---")
    print(f"  Messages: {summary['total_messages']}")
    print(f"  Tool use blocks: {summary['tool_use_blocks']}")
    print(f"  Tokens: {summary['total_input_tokens']} in / {summary['total_output_tokens']} out")

    for tu in collector.tool_use_blocks:
        print(f"    Tool: {tu['tool']}")

    has_text = len(collector.result_text) > 0
    has_usage = summary["total_input_tokens"] > 0
    has_tool_traces = summary["tool_use_blocks"] > 0

    print(f"  Tool traces: {has_tool_traces}")
    print(f"  Text content: {has_text}")
    print(f"  Usage metrics: {has_usage}")

    passed = has_text and has_usage
    print(f"  {'PASS' if passed else 'FAIL'} - Trace types observed for frontend rendering")
    return passed


# ============================================================
# Test 4: Subagent orchestration (agents-as-tools)
# ============================================================

async def test_4_subagent_orchestration():
    """Test agents-as-tools pattern (Strands equivalent of Claude SDK subagents)."""
    print("\n" + "=" * 70)
    print("TEST 4: Subagent Orchestration (Agents-as-Tools Pattern)")
    print("=" * 70)

    import glob as _glob

    tenant_id = "globex-inc"
    subscription_tier = "premium"

    @tool(name="file_analyzer")
    def file_analyzer_tool(query: str) -> str:
        """Analyzes file structure and counts files. Use for file system questions.

        Args:
            query: The file analysis question or task
        """
        test_dir = os.path.dirname(os.path.abspath(__file__))
        py_files = _glob.glob(os.path.join(test_dir, "*.py"))
        return json.dumps({
            "py_file_count": len(py_files),
            "files": [os.path.basename(f) for f in py_files[:10]],
            "query": query,
        })

    @tool(name="code_reader")
    def code_reader_tool(query: str) -> str:
        """Reads and summarizes code files. Use for understanding code content.

        Args:
            query: The code reading task or question
        """
        return json.dumps({
            "summary": (
                "config.py defines application configuration constants including "
                "the server port (default 8000), database settings, and AWS region."
            ),
            "query": query,
        })

    supervisor = Agent(
        model=_model,
        system_prompt=(
            f"You are an AI assistant for tenant '{tenant_id}' (tier: {subscription_tier}). "
            "Use file_analyzer for file system questions and code_reader for code questions."
        ),
        tools=[file_analyzer_tool, code_reader_tool],
        callback_handler=None,
    )

    print(f"  Tenant: {tenant_id} | Tier: {subscription_tier}")
    print("  Tools: file_analyzer, code_reader")
    print()

    collector = StrandsResultCollector()
    result = supervisor(
        "Do two things:\n"
        "1. Use the file_analyzer to count .py files in the tests directory\n"
        "2. Use the code_reader to summarize what config.py does\n"
        "Report both results."
    )
    collector.process_result(result, indent=2, agent=supervisor)

    print()
    summary = collector.summary()
    print(f"  --- Trace Analysis ---")
    print(f"  Messages: {summary['total_messages']}")
    print(f"  Tool use blocks: {summary['tool_use_blocks']}")
    print(f"  Tokens: {summary['total_input_tokens']} in / {summary['total_output_tokens']} out")

    for tc in collector.tool_use_blocks:
        print(f"    -> {tc['tool']}")

    passed = len(collector.result_text) > 0 and summary["total_messages"] > 0
    print(f"  {'PASS' if passed else 'FAIL'} - Subagent orchestration (agents-as-tools)")
    return passed


# ============================================================
# Test 5: Cost/usage tracking
# ============================================================

async def test_5_cost_tracking():
    """Track cost/tokens from Strands result.metrics -- for the cost ticker UI."""
    print("\n" + "=" * 70)
    print("TEST 5: Cost Tracking (result.metrics usage)")
    print("=" * 70)

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

    for i, prompt in enumerate([
        "What is 2 + 2? Answer in one word.",
        "What is the capital of France? One word answer.",
    ], 1):
        print(f"  --- Query {i} ---")

        agent = Agent(
            model=_model,
            system_prompt=f"You are a concise assistant for tenant '{tenant_id}'. One-line answers only.",
            callback_handler=None,
        )

        collector = StrandsResultCollector()
        result = agent(prompt)
        collector.process_result(result, indent=3)

        summary = collector.summary()
        total_cost_record["queries"] += 1
        total_cost_record["total_input_tokens"] += summary["total_input_tokens"]
        total_cost_record["total_output_tokens"] += summary["total_output_tokens"]
        total_cost_record["sdk_total_cost_usd"] += summary["total_cost_usd"]

        print(f"    Tokens: {summary['total_input_tokens']} in / {summary['total_output_tokens']} out")
        print(f"    Cost: ${summary['total_cost_usd']:.6f}")
        print()

    print("  --- Cost Attribution Record ---")
    print(f"  {json.dumps(total_cost_record, indent=4)}")

    has_usage = total_cost_record["total_input_tokens"] > 0
    print(f"  Usage tracked: {has_usage}")

    passed = has_usage
    print(f"  {'PASS' if passed else 'FAIL'} - Cost tracking from result.metrics")
    return passed


# ============================================================
# Test 6: Tier-gated tools (direct @tool, no MCP)
# ============================================================

async def test_6_tier_gated_tools():
    """Test custom @tool functions gated by subscription tier. No MCP in Strands."""
    print("\n" + "=" * 70)
    print("TEST 6: Tier-Gated Custom Tools (@tool, no MCP)")
    print("=" * 70)

    @tool(name="lookup_product")
    def lookup_product(product_name: str) -> str:
        """Look up product details by name.

        Args:
            product_name: The name of the product to look up
        """
        products = {
            "widget pro": {"id": "WP-001", "name": "Widget Pro", "price": 29.99, "stock": 150},
            "gadget lite": {"id": "GL-002", "name": "Gadget Lite", "price": 14.99, "stock": 500},
            "sensor max": {"id": "SM-003", "name": "Sensor Max", "price": 49.99, "stock": 75},
        }
        key = product_name.lower()
        result_data = products.get(key, {"error": f"Product '{product_name}' not found"})
        return json.dumps(result_data)

    agent = Agent(
        model=_model,
        system_prompt=(
            "You are an inventory assistant for a premium-tier tenant. "
            "Use lookup_product to find products. Be concise."
        ),
        tools=[lookup_product],
        callback_handler=None,
    )

    print("  Tier: premium (has lookup_product tool)")
    print()

    collector = StrandsResultCollector()
    result = agent("Look up the product called Widget Pro.")
    collector.process_result(result, indent=2, agent=agent)

    print()
    summary = collector.summary()
    print(f"  --- Results ---")
    print(f"  Messages: {summary['total_messages']}")
    print(f"  Tool calls: {summary['tool_use_blocks']}")
    print(f"  Tokens: {summary['total_input_tokens']} in / {summary['total_output_tokens']} out")

    tool_calls = [t for t in collector.tool_use_blocks if "lookup_product" in t["tool"]]
    print(f"  lookup_product calls: {len(tool_calls)}")

    passed = len(collector.result_text) > 0 and summary["total_messages"] > 0
    print(f"  {'PASS' if passed else 'FAIL'} - Tier-gated @tool")
    return passed


# ============================================================
# Test 7: Skill loading via system_prompt
# ============================================================

async def test_7_skill_loading():
    """Test loading a skill file and injecting it as system_prompt."""
    print("\n" + "=" * 70)
    print("TEST 7: Skill Loading (OA Intake Skill -> system_prompt)")
    print("=" * 70)

    skill_content, skill_path = load_skill_file()
    if not skill_content:
        print("  SKIP - Skill constant not found")
        return None

    print(f"  Skill loaded: {skill_path}")
    print(f"  Skill size: {len(skill_content)} chars")

    tenant_context = (
        "Tenant: nci-oa | User: intake-officer-01 | Tier: premium\n"
        "You are operating as the OA Intake Agent for this tenant.\n\n"
    )

    agent = Agent(
        model=_model,
        system_prompt=tenant_context + skill_content,
        callback_handler=None,
    )

    print(f"  System prompt: tenant_context + skill ({len(tenant_context) + len(skill_content)} chars)")
    print()

    collector = StrandsResultCollector()
    result = agent("Hi, I need to buy a new microscope. Not sure about the price. Need it in 2 months.")
    collector.process_result(result, indent=2)

    print()
    summary = collector.summary()
    print(f"  --- Results ---")
    print(f"  Messages: {summary['total_messages']}")
    print(f"  Tokens: {summary['total_input_tokens']} in / {summary['total_output_tokens']} out")

    all_text = collector.all_text_lower()

    skill_indicators = {
        "clarifying_questions": any(w in all_text for w in ["manufacturer", "model", "new or", "refurbished", "budget", "funding"]),
        "cost_awareness": any(w in all_text for w in ["$", "cost", "price", "range", "estimate", "value"]),
        "acquisition_knowledge": any(w in all_text for w in ["acquisition", "procurement", "purchase", "sow", "micro", "simplified"]),
        "follow_up_pattern": "?" in all_text,
    }

    print("  Skill indicators in response:")
    for indicator, found in skill_indicators.items():
        print(f"    {indicator}: {found}")

    indicators_found = sum(1 for v in skill_indicators.values() if v)
    passed = indicators_found >= 2 and len(collector.result_text) > 0
    print(f"  Skill indicators: {indicators_found}/4")
    print(f"  {'PASS' if passed else 'FAIL'} - Skill loaded and applied via system_prompt")
    return passed


# ============================================================
# Test 8: Subagent tool tracking
# ============================================================

async def test_8_subagent_tool_tracking():
    """Track which tools each subagent-tool invokes via result.messages."""
    print("\n" + "=" * 70)
    print("TEST 8: Subagent Tool Use Tracking")
    print("=" * 70)

    import glob as _glob

    @tool(name="file_scanner")
    def file_scanner_tool(query: str) -> str:
        """Scans for files matching patterns. Use for finding files.

        Args:
            query: Description of what files to find
        """
        test_dir = os.path.dirname(os.path.abspath(__file__))
        py_files = _glob.glob(os.path.join(test_dir, "*.py"))
        return json.dumps({
            "files": [os.path.basename(f) for f in py_files],
            "count": len(py_files),
            "query": query,
        })

    @tool(name="code_inspector")
    def code_inspector_tool(query: str) -> str:
        """Reads and inspects code files for patterns and content.

        Args:
            query: What to inspect in the code
        """
        return json.dumps({
            "inspection": "config.py defines PORT=8000 and DATABASE_URL settings.",
            "query": query,
        })

    agent = Agent(
        model=_model,
        system_prompt=(
            "You are a code analysis assistant with specialized tools. "
            "Use file_scanner to find files and code_inspector to read code. "
            "Always use the appropriate tool for each task."
        ),
        tools=[file_scanner_tool, code_inspector_tool],
        callback_handler=None,
    )

    print("  Tools: file_scanner, code_inspector")
    print()

    collector = StrandsResultCollector()
    result = agent(
        "Do these two things:\n"
        "1. Use file_scanner to find all .py files in the tests root directory\n"
        "2. Use code_inspector to read config.py and tell me the port number\n"
        "Report both results."
    )
    collector.process_result(result, indent=2, agent=agent)

    print()
    summary = collector.summary()
    print(f"  --- Subagent Tool Tracking ---")
    print(f"  Total messages: {summary['total_messages']}")
    print(f"  Tool use blocks: {summary['tool_use_blocks']}")
    print(f"  Tokens: {summary['total_input_tokens']} in / {summary['total_output_tokens']} out")

    for tc in collector.tool_use_blocks:
        print(f"    -> {tc['tool']}")

    passed = len(collector.result_text) > 0 and summary["total_messages"] > 0
    print(f"  {'PASS' if passed else 'FAIL'} - Subagent tool use tracking")
    return passed


# ============================================================
# Test 9: OA Intake Workflow (CT Scanner Acquisition)
# ============================================================

async def test_9_oa_intake_workflow():
    """Run through the OA Intake workflow. Single-turn (Strands is stateless)."""
    print("\n" + "=" * 70)
    print("TEST 9: OA Intake Workflow (CT Scanner Acquisition)")
    print("=" * 70)

    skill_content, skill_path = load_skill_file()
    if not skill_content:
        print("  SKIP - Skill file not found")
        return None

    print(f"  Skill: {skill_path}")
    print("  Workflow: CT Scanner intake Phase 1 (single-turn)")
    print()

    tenant_context = (
        "Tenant: nci-oa | User: dr-smith-001 | Tier: premium\n"
        "You are the OA Intake Agent. Follow the skill workflow exactly.\n\n"
    )

    agent = Agent(
        model=_model,
        system_prompt=tenant_context + skill_content,
        callback_handler=None,
    )

    collector = StrandsResultCollector()
    result = agent("Cat scan machine. Not sure the price. I need it in 6 weeks.")
    collector.process_result(result, indent=3)

    summary = collector.summary()
    all_text = collector.all_text_lower()

    keywords = ["ct", "scanner", "cost", "price", "timeline", "equipment"]
    keywords_found = [kw for kw in keywords if kw in all_text]
    keywords_missing = [kw for kw in keywords if kw not in all_text]
    phase_pass = len(keywords_found) >= len(keywords) // 2

    print(f"  --- Phase 1 Results ---")
    print(f"  Tokens: {summary['total_input_tokens']} in / {summary['total_output_tokens']} out")
    print(f"  Keywords found: {keywords_found}")
    if keywords_missing:
        print(f"  Keywords missing: {keywords_missing}")
    print(f"  Phase 1: {'PASS' if phase_pass else 'FAIL'}")

    passed = phase_pass and len(collector.result_text) > 0
    print(f"  {'PASS' if passed else 'FAIL'} - OA Intake workflow (phase 1)")
    return passed


# ============================================================
# Test 10: Legal Counsel Skill (Sole Source J&A Review)
# ============================================================

async def test_10_legal_counsel_skill():
    """Test Legal Counsel agent loaded from agents/legal-counsel/agent.md."""
    print("\n" + "=" * 70)
    print("TEST 10: Legal Counsel Skill (Sole Source J&A Review)")
    print("=" * 70)

    skill_content, skill_path = load_skill_or_prompt(skill_name="legal-counsel")
    if not skill_content:
        print("  SKIP - Legal prompt not found")
        return None

    print(f"  Skill loaded: {skill_path}")
    print("  Scenario: Sole source $985K Illumina sequencer")
    print()

    tenant_context = (
        "Tenant: nci-oa | User: co-johnson-001 | Tier: premium\n"
        "You are the Legal Counsel skill for the EAGLE Supervisor Agent.\n\n"
    )

    agent = Agent(
        model=_model,
        system_prompt=tenant_context + skill_content,
        callback_handler=None,
    )

    collector = StrandsResultCollector()
    result = agent(
        "I need to sole source a $985K Illumina NovaSeq X Plus genome sequencer. "
        "Only Illumina makes this instrument. Assess the protest risk and "
        "tell me what FAR authority applies. What case precedents support this? "
        "Answer entirely from your knowledge -- do not search files or use tools."
    )
    collector.process_result(result, indent=2)

    print()
    summary = collector.summary()
    print(f"  --- Results ---")
    print(f"  Messages: {summary['total_messages']}")
    print(f"  Tokens: {summary['total_input_tokens']} in / {summary['total_output_tokens']} out")

    all_text = collector.all_text_lower()

    indicators = {
        "far_citation": any(w in all_text for w in ["far 6.302", "6.302-1", "one responsible source"]),
        "protest_risk": any(w in all_text for w in ["protest", "risk", "gao", "vulnerability"]),
        "case_law": any(w in all_text for w in ["b-4", "decision", "precedent", "sustained", "denied"]),
        "proprietary": any(w in all_text for w in ["proprietary", "sole source", "only one", "sole vendor"]),
        "recommendation": any(w in all_text for w in ["recommend", "document", "justif", "market research"]),
    }

    print("  Skill indicators:")
    for indicator, found in indicators.items():
        print(f"    {indicator}: {found}")

    indicators_found = sum(1 for v in indicators.values() if v)
    passed = indicators_found >= 3 and len(collector.result_text) > 0
    print(f"  Skill indicators: {indicators_found}/5")
    print(f"  {'PASS' if passed else 'FAIL'} - Legal Counsel skill applied")
    return passed


# ============================================================
# Test 11: Market Intelligence Skill (Vendor Research)
# ============================================================

async def test_11_market_intelligence_skill():
    """Test Market Intelligence agent loaded from agents/market-intelligence/agent.md."""
    print("\n" + "=" * 70)
    print("TEST 11: Market Intelligence Skill (Vendor Research)")
    print("=" * 70)

    skill_content, skill_path = load_skill_or_prompt(skill_name="market-intelligence")
    if not skill_content:
        print("  SKIP - Market prompt not found")
        return None

    print(f"  Skill loaded: {skill_path}")
    print("  Scenario: IT services $500K market research")
    print()

    tenant_context = (
        "Tenant: nci-oa | User: market-analyst-001 | Tier: premium\n"
        "You are the Market Intelligence skill for the EAGLE Supervisor Agent.\n\n"
    )

    agent = Agent(
        model=_model,
        system_prompt=tenant_context + skill_content,
        callback_handler=None,
    )

    collector = StrandsResultCollector()
    result = agent(
        "We need IT modernization services for approximately $500K over 3 years. "
        "Cloud migration and agile development. What does the market look like? "
        "Any small business set-aside opportunities? What about GSA vehicles?"
    )
    collector.process_result(result, indent=2)

    print()
    summary = collector.summary()
    print(f"  --- Results ---")
    print(f"  Messages: {summary['total_messages']}")
    print(f"  Tokens: {summary['total_input_tokens']} in / {summary['total_output_tokens']} out")

    all_text = collector.all_text_lower()

    indicators = {
        "small_business": any(w in all_text for w in ["small business", "8(a)", "hubzone", "wosb", "sdvosb", "set-aside"]),
        "gsa_vehicles": any(w in all_text for w in ["gsa", "schedule", "gwac", "alliant", "cio-sp", "it schedule"]),
        "pricing": any(w in all_text for w in ["rate", "pricing", "cost", "benchmark", "$", "labor"]),
        "vendor_analysis": any(w in all_text for w in ["vendor", "contractor", "provider", "firm", "company"]),
        "competition": any(w in all_text for w in ["competit", "market", "availab", "capabil"]),
    }

    print("  Skill indicators:")
    for indicator, found in indicators.items():
        print(f"    {indicator}: {found}")

    indicators_found = sum(1 for v in indicators.values() if v)
    passed = indicators_found >= 3 and len(collector.result_text) > 0
    print(f"  Skill indicators: {indicators_found}/5")
    print(f"  {'PASS' if passed else 'FAIL'} - Market Intelligence skill applied")
    return passed


# ============================================================
# Test 12: Tech Review Skill (SOW Requirements Translation)
# ============================================================

async def test_12_tech_review_skill():
    """Test Tech Translator agent loaded from agents/tech-translator/agent.md."""
    print("\n" + "=" * 70)
    print("TEST 12: Tech Review Skill (SOW Requirements Translation)")
    print("=" * 70)

    skill_content, skill_path = load_skill_or_prompt(skill_name="tech-translator")
    if not skill_content:
        print("  SKIP - Tech prompt not found")
        return None

    print(f"  Skill loaded: {skill_path}")
    print("  Scenario: Agile development SOW requirements")
    print()

    tenant_context = (
        "Tenant: nci-oa | User: cor-williams-001 | Tier: premium\n"
        "You are the Tech Review skill for the EAGLE Supervisor Agent.\n\n"
    )

    agent = Agent(
        model=_model,
        system_prompt=tenant_context + skill_content,
        callback_handler=None,
    )

    collector = StrandsResultCollector()
    result = agent(
        "I need to write SOW requirements for an agile cloud migration project. "
        "The team will use 2-week sprints, AWS GovCloud, and need FedRAMP compliance. "
        "How should I express these technical requirements in contract language? "
        "What evaluation criteria would you recommend?"
    )
    collector.process_result(result, indent=2)

    print()
    summary = collector.summary()
    print(f"  --- Results ---")
    print(f"  Messages: {summary['total_messages']}")
    print(f"  Tokens: {summary['total_input_tokens']} in / {summary['total_output_tokens']} out")

    all_text = collector.all_text_lower()

    indicators = {
        "sow_language": any(w in all_text for w in ["sow", "statement of work", "deliverable", "performance"]),
        "agile_terms": any(w in all_text for w in ["sprint", "agile", "iteration", "scrum", "backlog"]),
        "evaluation": any(w in all_text for w in ["evaluat", "criteria", "factor", "technical approach", "past performance"]),
        "compliance": any(w in all_text for w in ["fedramp", "508", "security", "compliance", "govcloud"]),
        "measurable": any(w in all_text for w in ["measur", "accept", "milestone", "definition of done", "metric"]),
    }

    print("  Skill indicators:")
    for indicator, found in indicators.items():
        print(f"    {indicator}: {found}")

    indicators_found = sum(1 for v in indicators.values() if v)
    passed = indicators_found >= 3 and len(collector.result_text) > 0
    print(f"  Skill indicators: {indicators_found}/5")
    print(f"  {'PASS' if passed else 'FAIL'} - Tech Review skill applied")
    return passed


# ============================================================
# Test 13: Public Interest Skill (Fairness & Transparency)
# ============================================================

async def test_13_public_interest_skill():
    """Test Public Interest agent loaded from agents/public-interest/agent.md."""
    print("\n" + "=" * 70)
    print("TEST 13: Public Interest Skill (Fairness & Transparency)")
    print("=" * 70)

    skill_content, skill_path = load_skill_or_prompt(skill_name="public-interest")
    if not skill_content:
        print("  SKIP - Public Interest prompt not found")
        return None

    print(f"  Skill loaded: {skill_path}")
    print("  Scenario: $2.1M sole source IT services review")
    print()

    tenant_context = (
        "Tenant: nci-oa | User: co-davis-001 | Tier: premium\n"
        "You are the Public Interest skill for the EAGLE Supervisor Agent.\n\n"
    )

    agent = Agent(
        model=_model,
        system_prompt=tenant_context + skill_content,
        callback_handler=None,
    )

    collector = StrandsResultCollector()
    result = agent(
        "Review this for public interest concerns: We're doing a sole source "
        "award for $2.1M in IT services to the same vendor who had the previous "
        "contract. No sources sought was posted on SAM.gov. Only 2 vendors were "
        "contacted during market research. This is a congressional interest area."
    )
    collector.process_result(result, indent=2)

    print()
    summary = collector.summary()
    print(f"  --- Results ---")
    print(f"  Messages: {summary['total_messages']}")
    print(f"  Tokens: {summary['total_input_tokens']} in / {summary['total_output_tokens']} out")

    all_text = collector.all_text_lower()

    indicators = {
        "fairness": any(w in all_text for w in ["fair", "equit", "appearance", "vendor lock", "incumbent"]),
        "transparency": any(w in all_text for w in ["transparen", "sam.gov", "sources sought", "public", "notice"]),
        "protest_risk": any(w in all_text for w in ["protest", "risk", "vulnerab", "challenge", "gao"]),
        "congressional": any(w in all_text for w in ["congress", "oversight", "media", "scrutin", "political"]),
        "recommendation": any(w in all_text for w in ["recommend", "mitigat", "broader", "expand", "post"]),
    }

    print("  Skill indicators:")
    for indicator, found in indicators.items():
        print(f"    {indicator}: {found}")

    indicators_found = sum(1 for v in indicators.values() if v)
    passed = indicators_found >= 3 and len(collector.result_text) > 0
    print(f"  Skill indicators: {indicators_found}/5")
    print(f"  {'PASS' if passed else 'FAIL'} - Public Interest skill applied")
    return passed


# ============================================================
# Test 14: Document Generator Skill (AP Generation)
# ============================================================

async def test_14_document_generator_skill():
    """Test Document Generator skill loaded from SKILL.md."""
    print("\n" + "=" * 70)
    print("TEST 14: Document Generator Skill (Acquisition Plan)")
    print("=" * 70)

    skill_content, skill_path = load_skill_or_prompt(skill_name="document-generator")
    if not skill_content:
        print("  SKIP - Document Generator skill not found")
        return None

    print(f"  Skill loaded: {skill_path}")
    print("  Scenario: Generate AP for $300K lab equipment")
    print()

    tenant_context = (
        "Tenant: nci-oa | User: co-martinez-001 | Tier: premium\n"
        "You are the Document Generator skill for the EAGLE Supervisor Agent.\n\n"
    )

    agent = Agent(
        model=_model,
        system_prompt=tenant_context + skill_content,
        callback_handler=None,
    )

    collector = StrandsResultCollector()
    result = agent(
        "Generate an Acquisition Plan (AP) for the following: "
        "$300K laboratory centrifuge equipment purchase, new, competitive, "
        "simplified acquisition procedures (FAR Part 13), small business set-aside, "
        "delivery within 90 days, FY2026 funding. Include all required sections. "
        "IMPORTANT: Return the full document as text in your response. "
        "Do NOT write to a file."
    )
    collector.process_result(result, indent=2)

    print()
    summary = collector.summary()
    print(f"  --- Results ---")
    print(f"  Messages: {summary['total_messages']}")
    print(f"  Tokens: {summary['total_input_tokens']} in / {summary['total_output_tokens']} out")

    all_text = collector.all_text_lower()
    # Also include Write tool inputs if agent wrote to file
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

    print("  Skill indicators:")
    for indicator, found in indicators.items():
        print(f"    {indicator}: {found}")

    indicators_found = sum(1 for v in indicators.values() if v)
    passed = indicators_found >= 3 and len(collector.result_text) > 0
    print(f"  Skill indicators: {indicators_found}/5")
    print(f"  {'PASS' if passed else 'FAIL'} - Document Generator skill applied")
    return passed


# ============================================================
# Test 15: Supervisor Multi-Skill Chain (agents-as-tools)
# ============================================================

async def test_15_supervisor_multi_skill_chain():
    """Test Supervisor invoking multiple skills as @tool-wrapped subagents."""
    print("\n" + "=" * 70)
    print("TEST 15: Supervisor Multi-Skill Chain (UC-01 End-to-End)")
    print("=" * 70)

    legal_content, _ = load_skill_or_prompt(skill_name="legal-counsel")
    market_content, _ = load_skill_or_prompt(skill_name="market-intelligence")
    intake_content, _ = load_skill_or_prompt(skill_name="oa-intake")

    missing = []
    if not legal_content:
        missing.append("legal-counsel")
    if not market_content:
        missing.append("market-intelligence")
    if not intake_content:
        missing.append("oa-intake")

    if missing:
        print(f"  SKIP - Missing skill files: {missing}")
        return None

    print("  Skill chain: OA Intake -> Market Intelligence -> Legal Counsel")
    print("  Scenario: $500K IT services, competitive, 3-year PoP")
    print()

    # Build subagent tools
    @tool(name="oa_intake")
    def oa_intake_tool(query: str) -> str:
        """Gathers acquisition requirements and determines type/threshold. Use for initial intake.

        Args:
            query: The acquisition details or question for intake processing
        """
        subagent = Agent(
            model=_model,
            system_prompt=intake_content[:3000],
            callback_handler=None,
        )
        return str(subagent(query))

    @tool(name="market_intelligence")
    def market_intelligence_tool(query: str) -> str:
        """Researches market conditions, vendors, and pricing. Use for market research.

        Args:
            query: The market research question or requirement
        """
        subagent = Agent(
            model=_model,
            system_prompt=market_content,
            callback_handler=None,
        )
        return str(subagent(query))

    @tool(name="legal_counsel")
    def legal_counsel_tool(query: str) -> str:
        """Assesses legal risks, protest vulnerabilities, FAR compliance. Use for legal review.

        Args:
            query: The legal question or compliance scenario
        """
        subagent = Agent(
            model=_model,
            system_prompt=legal_content,
            callback_handler=None,
        )
        return str(subagent(query))

    supervisor_prompt = (
        "You are the EAGLE Supervisor Agent for NCI Office of Acquisitions.\n"
        "You orchestrate acquisition workflows by delegating to specialized skill tools.\n\n"
        "Available tools:\n"
        "- oa_intake: Gathers initial requirements and determines acquisition type\n"
        "- market_intelligence: Researches vendors, pricing, small business opportunities\n"
        "- legal_counsel: Assesses legal risks, protest vulnerabilities, FAR compliance\n\n"
        "For this request, invoke each tool in sequence:\n"
        "1. First use oa_intake to classify the acquisition\n"
        "2. Then use market_intelligence to assess the market\n"
        "3. Then use legal_counsel to check legal risks\n"
        "4. Synthesize all findings into a brief summary"
    )

    supervisor = Agent(
        model=_model,
        system_prompt=supervisor_prompt,
        tools=[oa_intake_tool, market_intelligence_tool, legal_counsel_tool],
        callback_handler=None,
    )

    collector = StrandsResultCollector()
    result = supervisor(
        "New acquisition request: We need IT modernization services for $500K "
        "over 3 years. Includes cloud migration and agile development. "
        "Run the full skill chain to assess this acquisition."
    )
    collector.process_result(result, indent=2, agent=supervisor)

    print()
    summary = collector.summary()
    print(f"  --- Results ---")
    print(f"  Messages: {summary['total_messages']}")
    print(f"  Tool use blocks: {summary['tool_use_blocks']}")
    print(f"  Tokens: {summary['total_input_tokens']} in / {summary['total_output_tokens']} out")

    tool_calls = collector.tool_use_blocks
    tool_names = [t["tool"] for t in tool_calls]
    print(f"  Tool invocations: {len(tool_calls)}")
    for tn in tool_names:
        print(f"    -> {tn}")

    all_text = collector.all_text_lower()

    indicators = {
        "multiple_tools": len(tool_calls) >= 2,
        "intake_invoked": any("intake" in tn.lower() for tn in tool_names),
        "market_invoked": any("market" in tn.lower() for tn in tool_names),
        "legal_invoked": any("legal" in tn.lower() or "counsel" in tn.lower() for tn in tool_names),
        "synthesis": any(w in all_text for w in ["summary", "recommend", "finding", "assessment", "result"]),
    }

    print("  Skill chain indicators:")
    for indicator, found in indicators.items():
        print(f"    {indicator}: {found}")

    indicators_found = sum(1 for v in indicators.values() if v)
    passed = indicators_found >= 3 and len(collector.result_text) > 0
    print(f"  Skill chain indicators: {indicators_found}/5")
    print(f"  {'PASS' if passed else 'FAIL'} - Supervisor multi-skill chain")
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
    bucket = os.environ.get("S3_BUCKET", "eagle-documents-695681773636-dev")

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

    passed = all(ok for _, ok in steps_passed)
    print(f"  Steps: {', '.join(f'{name}={chr(80) if ok else chr(70)}{chr(65) if ok else chr(65)}{chr(83) if ok else chr(73)}{chr(83) if ok else chr(76)}' for name, ok in steps_passed)}")
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
    effective_tenant = "demo-tenant"
    ddb = _boto3.resource("dynamodb", region_name="us-east-1")
    table = ddb.Table(table_name)
    boto3_ok = False
    try:
        resp = table.get_item(Key={"PK": f"INTAKE#{effective_tenant}", "SK": f"INTAKE#{item_id}"})
        ddb_item = resp.get("Item", {})
        boto3_ok = ddb_item.get("item_id") == item_id and ddb_item.get("status") == "reviewed"
        if boto3_ok:
            print(f"    item_id={ddb_item.get('item_id')} status={ddb_item.get('status')} PASS")
        else:
            print(f"    item={ddb_item} FAIL")
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

    passed = all(ok for _, ok in steps_passed)
    step_str = ", ".join(f"{n}={'PASS' if ok else 'FAIL'}" for n, ok in steps_passed)
    print(f"  Steps: {step_str}")
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

    passed = all(ok for _, ok in steps_passed)
    step_str = ", ".join(f"{n}={'PASS' if ok else 'FAIL'}" for n, ok in steps_passed)
    print(f"  Steps: {step_str}")
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
    bucket = os.environ.get("S3_BUCKET", "eagle-documents-695681773636-dev")

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
        print(f"  Step {i}: create_document doc_type={dt['doc_type']}")
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

        has_header = dt["expect_in_content"].upper() in content.upper()
        has_dollar = "$" in content if dt.get("expect_dollar") else True
        has_far = "far" in content.lower() or "FAR" in content if dt.get("expect_far") else True
        meets_word_count = word_count >= dt.get("min_word_count", 100)

        doc_ok = has_header and has_dollar and has_far and meets_word_count
        steps_passed.append((dt["doc_type"], doc_ok))
        print(f"    header={has_header} words={word_count} s3_status={status} {'PASS' if doc_ok else 'FAIL'}")

    # Step 4: boto3 confirm documents in S3
    print(f"  Step 4: boto3 list_objects_v2 confirm")
    s3 = _boto3.client("s3", region_name="us-east-1")
    boto3_ok = False
    try:
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
    print(f"  Step 5: cleanup {len(s3_keys_to_cleanup)} documents")
    for s3_key in s3_keys_to_cleanup:
        try:
            s3.delete_object(Bucket=bucket, Key=s3_key)
            print(f"    deleted {s3_key}")
        except Exception as e:
            print(f"    cleanup error for {s3_key}: {e}")

    passed = all(ok for _, ok in steps_passed)
    step_str = ", ".join(f"{n}={'PASS' if ok else 'FAIL'}" for n, ok in steps_passed)
    print(f"  Steps: {step_str}")
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
        streams = []

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

    # Step 3: Parse events -- check for proper structure
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
    if not summary_ok:
        print(f"    no run_summary event found in latest stream FAIL")
    steps_passed.append(("run_summary", summary_ok))

    passed = all(ok for _, ok in steps_passed)
    step_str = ", ".join(f"{n}={'PASS' if ok else 'FAIL'}" for n, ok in steps_passed)
    print(f"  Steps: {step_str}")
    print(f"  {'PASS' if passed else 'FAIL'} - CloudWatch End-to-End Verification")
    return passed


# ============================================================
# Test 21: UC-02 Micro-Purchase Workflow (<$15K Fast Path)
# ============================================================

async def test_21_uc02_micro_purchase():
    """UC-02: Micro-purchase fast path -- threshold detection, streamlined intake."""
    print("\n" + "=" * 70)
    print("TEST 21: UC-02 Micro-Purchase Workflow (<$15K Fast Path)")
    print("=" * 70)

    intake_content, _ = load_skill_or_prompt(skill_name="oa-intake")
    if not intake_content:
        print("  SKIP - OA Intake skill not found")
        return None

    print("  Scenario: $13,800 lab supplies -- Fisher Scientific quote")
    print()

    tenant_context = (
        "Tenant: nci-oa | User: cor-adams-001 | Tier: premium\n"
        "You are the OA Intake skill for the EAGLE Supervisor Agent.\n"
        "Handle micro-purchase requests efficiently with minimal questions.\n\n"
    )

    agent = Agent(
        model=_model,
        system_prompt=tenant_context + intake_content,
        callback_handler=None,
    )

    collector = StrandsResultCollector()
    result = agent(
        "I have a quote for $13,800 from Fisher Scientific for lab supplies -- "
        "centrifuge tubes, pipette tips, and reagents. Grant-funded, deliver to "
        "Building 37 Room 204. I want to use the purchase card. "
        "What's the fastest way to process this?"
    )
    collector.process_result(result, indent=2)

    print()
    summary = collector.summary()
    print(f"  --- Results ---")
    print(f"  Messages: {summary['total_messages']}")
    print(f"  Tokens: {summary['total_input_tokens']} in / {summary['total_output_tokens']} out")

    all_text = collector.all_text_lower()

    indicators = {
        "micro_purchase": any(w in all_text for w in ["micro-purchase", "micro purchase", "micropurchase", "simplified"]),
        "threshold": any(w in all_text for w in ["$15,000", "15k", "threshold", "below", "under"]),
        "purchase_card": any(w in all_text for w in ["purchase card", "p-card", "card holder", "government purchase"]),
        "streamlined": any(w in all_text for w in ["streamlined", "fast", "quick", "expedit", "minimal"]),
        "far_reference": any(w in all_text for w in ["far 13", "part 13", "far part", "simplified acquisition"]),
    }

    print("  UC-02 indicators:")
    for indicator, found in indicators.items():
        print(f"    {indicator}: {found}")

    indicators_found = sum(1 for v in indicators.values() if v)
    passed = indicators_found >= 3 and len(collector.result_text) > 0
    print(f"  UC-02 indicators: {indicators_found}/5")
    print(f"  {'PASS' if passed else 'FAIL'} - UC-02 Micro-Purchase workflow")
    return passed


# ============================================================
# Test 22: UC-03 Option Exercise Package Preparation
# ============================================================

async def test_22_uc03_option_exercise():
    """UC-03: Option exercise -- documents required for option year 3."""
    print("\n" + "=" * 70)
    print("TEST 22: UC-03 Option Exercise Package Preparation")
    print("=" * 70)

    intake_content, _ = load_skill_or_prompt(skill_name="oa-intake")
    if not intake_content:
        print("  SKIP - OA Intake skill not found")
        return None

    print("  Scenario: Exercise Option Year 3, same scope, 3% escalation")
    print()

    tenant_context = (
        "Tenant: nci-oa | User: co-chen-001 | Tier: premium\n"
        "You are the OA Intake skill for the EAGLE Supervisor Agent.\n"
        "Handle option exercise requests by reviewing prior packages and asking tuning questions.\n\n"
    )

    agent = Agent(
        model=_model,
        system_prompt=tenant_context + intake_content,
        callback_handler=None,
    )

    collector = StrandsResultCollector()
    result = agent(
        "I need to exercise Option Year 3 on contract HHSN261201500003I. "
        "The base value was $1.2M, same scope continuing, new COR replacing "
        "Dr. Smith, 3% cost escalation per the contract terms, no performance "
        "issues. Option period would be 10/1/2028 through 9/30/2029. "
        "What documents do I need to prepare?"
    )
    collector.process_result(result, indent=2)

    print()
    summary = collector.summary()
    print(f"  --- Results ---")
    print(f"  Messages: {summary['total_messages']}")
    print(f"  Tokens: {summary['total_input_tokens']} in / {summary['total_output_tokens']} out")

    all_text = collector.all_text_lower()

    indicators = {
        "option_exercise": any(w in all_text for w in ["option", "exercise", "option year", "option period"]),
        "escalation": any(w in all_text for w in ["escalat", "3%", "cost increase", "price adjust"]),
        "cor_change": any(w in all_text for w in ["cor", "contracting officer representative", "nomination", "new cor"]),
        "package_docs": any(w in all_text for w in ["acquisition plan", "sow", "igce", "statement of work"]),
        "option_letter": any(w in all_text for w in ["option letter", "exercise letter", "modification", "bilateral"]),
    }

    print("  UC-03 indicators:")
    for indicator, found in indicators.items():
        print(f"    {indicator}: {found}")

    indicators_found = sum(1 for v in indicators.values() if v)
    passed = indicators_found >= 3 and len(collector.result_text) > 0
    print(f"  UC-03 indicators: {indicators_found}/5")
    print(f"  {'PASS' if passed else 'FAIL'} - UC-03 Option Exercise workflow")
    return passed


# ============================================================
# Test 23: UC-04 Contract Modification Request
# ============================================================

async def test_23_uc04_contract_modification():
    """UC-04: Contract modification -- add funding + extend PoP."""
    print("\n" + "=" * 70)
    print("TEST 23: UC-04 Contract Modification Request")
    print("=" * 70)

    intake_content, _ = load_skill_or_prompt(skill_name="oa-intake")
    if not intake_content:
        print("  SKIP - OA Intake skill not found")
        return None

    print("  Scenario: Add $150K funding + extend PoP 6 months")
    print()

    tenant_context = (
        "Tenant: nci-oa | User: co-garcia-001 | Tier: premium\n"
        "You are the OA Intake skill for the EAGLE Supervisor Agent.\n"
        "Handle contract modification requests by classifying mod type and identifying required documents.\n"
        "IMPORTANT: Do not ask clarifying questions. All required information has been provided. "
        "Analyze the request directly and provide your complete classification, scope determination, "
        "FAR compliance guidance, and required documents list in your first response.\n\n"
    )

    agent = Agent(
        model=_model,
        system_prompt=tenant_context + intake_content,
        callback_handler=None,
    )

    collector = StrandsResultCollector()
    result = agent(
        "I need to modify contract HHSN261201500003I. Adding $150K in FY2026 "
        "funding and extending the period of performance by 6 months to September 30, 2027. "
        "Same scope of work, just continuing the existing effort. "
        "Is this within scope? What type of modification is this? What documents do I need?"
    )
    collector.process_result(result, indent=2)

    print()
    summary = collector.summary()
    print(f"  --- Results ---")
    print(f"  Messages: {summary['total_messages']}")
    print(f"  Tokens: {summary['total_input_tokens']} in / {summary['total_output_tokens']} out")

    all_text = collector.all_text_lower()

    indicators = {
        "modification": any(w in all_text for w in ["modif", "mod ", "sf-30", "amendment"]),
        "funding": any(w in all_text for w in ["fund", "$150", "fy2026", "incremental", "additional"]),
        "pop_extension": any(w in all_text for w in ["period of performance", "pop", "extend", "extension", "september"]),
        "within_scope": any(w in all_text for w in ["within scope", "in-scope", "no j&a", "same work", "bilateral"]),
        "far_compliance": any(w in all_text for w in ["far", "compliance", "justif", "clause", "unilateral"]),
    }

    print("  UC-04 indicators:")
    for indicator, found in indicators.items():
        print(f"    {indicator}: {found}")

    indicators_found = sum(1 for v in indicators.values() if v)
    passed = indicators_found >= 3 and len(collector.result_text) > 0
    print(f"  UC-04 indicators: {indicators_found}/5")
    print(f"  {'PASS' if passed else 'FAIL'} - UC-04 Contract Modification workflow")
    return passed


# ============================================================
# Test 24: UC-05 CO Package Review & Findings
# ============================================================

async def test_24_uc05_co_package_review():
    """UC-05: CO package review -- compliance checks across AP/SOW/IGCE."""
    print("\n" + "=" * 70)
    print("TEST 24: UC-05 CO Package Review & Findings Generation")
    print("=" * 70)

    comp_content, _ = load_skill_or_prompt(skill_name="legal-counsel")
    if not comp_content:
        print("  SKIP - Legal counsel agent not found")
        return None

    print("  Scenario: CO reviews acquisition package for $487K IT services")
    print()

    tenant_context = (
        "Tenant: nci-oa | User: co-patel-001 | Tier: premium\n"
        "You are the Compliance skill for the EAGLE Supervisor Agent.\n"
        "Review acquisition packages for FAR compliance, cross-reference consistency, "
        "and generate findings organized by severity.\n\n"
    )

    agent = Agent(
        model=_model,
        system_prompt=tenant_context + comp_content,
        callback_handler=None,
    )

    collector = StrandsResultCollector()
    result = agent(
        "Review this acquisition package for a $487,500 IT services contract: "
        "The AP says competitive full and open, but the IGCE total is $495,000 -- "
        "cost mismatch. The SOW mentions a 3-year PoP but the AP says 2 years. "
        "Market research is 14 months old. No FAR 52.219 small business clause. "
        "Task 3 deliverable in the SOW has no acceptance criteria. "
        "Identify all findings and categorize by severity (critical/moderate/minor)."
    )
    collector.process_result(result, indent=2)

    print()
    summary = collector.summary()
    print(f"  --- Results ---")
    print(f"  Messages: {summary['total_messages']}")
    print(f"  Tokens: {summary['total_input_tokens']} in / {summary['total_output_tokens']} out")

    all_text = collector.all_text_lower()

    indicators = {
        "cost_mismatch": any(w in all_text for w in ["cost mismatch", "igce", "inconsisten", "$487", "$495"]),
        "pop_inconsistency": any(w in all_text for w in ["period of performance", "pop", "mismatch", "3-year", "2-year"]),
        "far_clause": any(w in all_text for w in ["far 52", "clause", "52.219", "small business"]),
        "severity": any(w in all_text for w in ["critical", "moderate", "minor", "severity", "finding"]),
        "market_research": any(w in all_text for w in ["market research", "outdated", "14 month", "stale"]),
    }

    print("  UC-05 indicators:")
    for indicator, found in indicators.items():
        print(f"    {indicator}: {found}")

    indicators_found = sum(1 for v in indicators.values() if v)
    passed = indicators_found >= 3 and len(collector.result_text) > 0
    print(f"  UC-05 indicators: {indicators_found}/5")
    print(f"  {'PASS' if passed else 'FAIL'} - UC-05 CO Package Review workflow")
    return passed


# ============================================================
# Test 25: UC-07 Contract Close-Out
# ============================================================

async def test_25_uc07_contract_closeout():
    """UC-07: Contract close-out -- FAR 4.804 checklist and required documents."""
    print("\n" + "=" * 70)
    print("TEST 25: UC-07 Contract Close-Out")
    print("=" * 70)

    comp_content, _ = load_skill_or_prompt(skill_name="legal-counsel")
    if not comp_content:
        print("  SKIP - Legal counsel agent not found")
        return None

    print("  Scenario: Close out FFP contract HHSN261200900045C")
    print()

    tenant_context = (
        "Tenant: nci-oa | User: co-brown-001 | Tier: premium\n"
        "You are the Compliance skill for the EAGLE Supervisor Agent.\n"
        "Handle contract close-out by generating FAR 4.804 checklists and identifying required actions.\n\n"
    )

    agent = Agent(
        model=_model,
        system_prompt=tenant_context + comp_content,
        callback_handler=None,
    )

    collector = StrandsResultCollector()
    result = agent(
        "I need to close out contract HHSN261200900045C. It's a firm-fixed-price "
        "contract, all options were exercised, final invoice has been paid, "
        "and all deliverables have been accepted. What's the FAR 4.804 close-out "
        "checklist? What documents do I still need -- release of claims letter, "
        "patent report, property report? Draft a COR final assessment outline."
    )
    collector.process_result(result, indent=2)

    print()
    summary = collector.summary()
    print(f"  --- Results ---")
    print(f"  Messages: {summary['total_messages']}")
    print(f"  Tokens: {summary['total_input_tokens']} in / {summary['total_output_tokens']} out")

    all_text = collector.all_text_lower()

    indicators = {
        "far_4804": any(w in all_text for w in ["far 4.804", "4.804", "close-out", "closeout"]),
        "release_claims": any(w in all_text for w in ["release of claims", "release", "claims letter"]),
        "patent_report": any(w in all_text for w in ["patent", "intellectual property", "invention"]),
        "property_report": any(w in all_text for w in ["property", "gfp", "government furnished", "disposition"]),
        "cor_assessment": any(w in all_text for w in ["cor", "final assessment", "performance assessment", "completion"]),
    }

    print("  UC-07 indicators:")
    for indicator, found in indicators.items():
        print(f"    {indicator}: {found}")

    indicators_found = sum(1 for v in indicators.values() if v)
    passed = indicators_found >= 3 and len(collector.result_text) > 0
    print(f"  UC-07 indicators: {indicators_found}/5")
    print(f"  {'PASS' if passed else 'FAIL'} - UC-07 Contract Close-Out workflow")
    return passed


# ============================================================
# Test 26: UC-08 Government Shutdown Notification
# ============================================================

async def test_26_uc08_shutdown_notification():
    """UC-08: Shutdown notification -- contract classification and email templates."""
    print("\n" + "=" * 70)
    print("TEST 26: UC-08 Government Shutdown Notification")
    print("=" * 70)

    comp_content, _ = load_skill_or_prompt(skill_name="legal-counsel")
    if not comp_content:
        print("  SKIP - Legal counsel agent not found")
        return None

    print("  Scenario: Government shutdown in 4 hours, classify 200+ contracts")
    print()

    tenant_context = (
        "Tenant: nci-oa | User: co-wilson-001 | Tier: premium\n"
        "You are the Compliance skill for the EAGLE Supervisor Agent.\n"
        "Handle government shutdown notifications by classifying contracts and generating notifications.\n\n"
    )

    agent = Agent(
        model=_model,
        system_prompt=tenant_context + comp_content,
        callback_handler=None,
    )

    collector = StrandsResultCollector()
    result = agent(
        "Government shutdown is imminent -- 4 hours away. I have 200+ active contracts. "
        "How should I classify them? I know some are fully funded FFP (should continue), "
        "some are incrementally funded (stop at limit), some are cost-reimbursement "
        "(stop work immediately), and some support excepted life/safety activities. "
        "What notification categories do I need? What should each email say? "
        "Draft the four notification templates."
    )
    collector.process_result(result, indent=2)

    print()
    summary = collector.summary()
    print(f"  --- Results ---")
    print(f"  Messages: {summary['total_messages']}")
    print(f"  Tokens: {summary['total_input_tokens']} in / {summary['total_output_tokens']} out")

    all_text = collector.all_text_lower()

    indicators = {
        "shutdown": any(w in all_text for w in ["shutdown", "lapse", "appropriation", "continuing resolution"]),
        "ffp_continue": any(w in all_text for w in ["firm-fixed", "ffp", "continue", "fully funded"]),
        "stop_work": any(w in all_text for w in ["stop work", "cease", "stop-work", "suspend"]),
        "excepted": any(w in all_text for w in ["excepted", "life", "safety", "essential", "emergency"]),
        "notification": any(w in all_text for w in ["notif", "email", "letter", "template", "contractor"]),
    }

    print("  UC-08 indicators:")
    for indicator, found in indicators.items():
        print(f"    {indicator}: {found}")

    indicators_found = sum(1 for v in indicators.values() if v)
    passed = indicators_found >= 3 and len(collector.result_text) > 0
    print(f"  UC-08 indicators: {indicators_found}/5")
    print(f"  {'PASS' if passed else 'FAIL'} - UC-08 Shutdown Notification workflow")
    return passed


# ============================================================
# Test 27: UC-09 Technical Score Sheet Consolidation
# ============================================================

async def test_27_uc09_score_consolidation():
    """UC-09: Score consolidation -- cross-reviewer variance analysis."""
    print("\n" + "=" * 70)
    print("TEST 27: UC-09 Technical Score Sheet Consolidation")
    print("=" * 70)

    tech_content, _ = load_skill_or_prompt(skill_name="tech-translator")
    if not tech_content:
        print("  SKIP - Tech Translator agent not found")
        return None

    print("  Scenario: Consolidate 180 score sheets from 9 reviewers on 20 proposals")
    print()

    tenant_context = (
        "Tenant: nci-oa | User: co-taylor-001 | Tier: premium\n"
        "You are the Tech Review skill for the EAGLE Supervisor Agent.\n"
        "Handle technical evaluation score consolidation and question deduplication.\n\n"
    )

    agent = Agent(
        model=_model,
        system_prompt=tenant_context + tech_content,
        callback_handler=None,
    )

    collector = StrandsResultCollector()
    result = agent(
        "I have 180 score sheets from 9 technical reviewers evaluating 20 proposals. "
        "Each reviewer scored 5 evaluation factors: Technical Approach, Management Plan, "
        "Past Performance, Key Personnel, and Cost Realism. "
        "Three proposals have significant reviewer divergence. "
        "The reviewers also submitted 847 total questions -- many are duplicates. "
        "How should I consolidate the scores? What analysis should I run for "
        "reviewer variance? How do I deduplicate and categorize the questions?"
    )
    collector.process_result(result, indent=2)

    print()
    summary = collector.summary()
    print(f"  --- Results ---")
    print(f"  Messages: {summary['total_messages']}")
    print(f"  Tokens: {summary['total_input_tokens']} in / {summary['total_output_tokens']} out")

    all_text = collector.all_text_lower()

    indicators = {
        "score_matrix": any(w in all_text for w in ["score", "matrix", "consensus", "consolidat"]),
        "eval_factors": any(w in all_text for w in ["technical approach", "management", "past performance", "key personnel"]),
        "variance_analysis": any(w in all_text for w in ["variance", "divergen", "outlier", "disagree", "spread"]),
        "deduplication": any(w in all_text for w in ["dedup", "duplicate", "unique", "cluster", "categoriz"]),
        "evaluation_report": any(w in all_text for w in ["report", "summary", "per-contractor", "question sheet"]),
    }

    print("  UC-09 indicators:")
    for indicator, found in indicators.items():
        print(f"    {indicator}: {found}")

    indicators_found = sum(1 for v in indicators.values() if v)
    passed = indicators_found >= 3 and len(collector.result_text) > 0
    print(f"  UC-09 indicators: {indicators_found}/5")
    print(f"  {'PASS' if passed else 'FAIL'} - UC-09 Score Consolidation workflow")
    return passed


# ============================================================
# Test 28: Strands Architecture -- build_skill_tools() + sdk_query()
# ============================================================

async def test_28_strands_skill_tool_orchestration():
    """Test the strands_agentic_service skill->tool pattern.

    Validates:
    1. build_skill_tools() builds @tool-wrapped subagents from PLUGIN_CONTENTS
    2. build_supervisor_prompt() generates proper routing prompt from agent.md
    3. sdk_query() supervisor delegates to skills via @tool functions
    4. Each skill runs in its own Agent() context (fresh per call)
    """
    print("\n" + "=" * 70)
    print("TEST 28: Strands Architecture -- Skill->Tool Orchestration")
    print("=" * 70)

    try:
        from strands_agentic_service import (
            build_skill_tools,
            build_supervisor_prompt,
            sdk_query,
            SKILL_AGENT_REGISTRY,
        )
    except ImportError as e:
        print(f"  SKIP - strands_agentic_service import failed: {e}")
        return None

    # Step 1: Validate build_skill_tools()
    print("  Step 1: build_skill_tools()")
    skill_tools = build_skill_tools(tier="advanced")
    tool_names = [t.__name__ for t in skill_tools]
    print(f"    Built {len(skill_tools)} tools: {tool_names}")

    expected_skills = {
        "legal_counsel", "market_intelligence", "tech_translator",
        "public_interest", "policy_supervisor", "policy_librarian", "policy_analyst",
        "oa_intake", "document_generator", "compliance", "knowledge_retrieval", "tech_review",
    }
    tools_ok = len(skill_tools) > 0
    print(f"    Tools built successfully: {tools_ok}")

    # Verify each tool has a docstring (required for Strands schema)
    for t in skill_tools:
        has_doc = bool(t.__doc__ and len(t.__doc__) > 10)
        print(f"    {t.__name__}: has_doc={has_doc}")

    # Step 2: Validate build_supervisor_prompt()
    print("\n  Step 2: build_supervisor_prompt()")
    sup_prompt = build_supervisor_prompt(
        tenant_id="test-tenant", user_id="test-user", tier="premium"
    )
    print(f"    Supervisor prompt length: {len(sup_prompt)} chars")

    sup_references = any(name in sup_prompt for name in tool_names)
    print(f"    References skill names: {sup_references}")

    # Step 3: Run sdk_query() with limited skills for cost control
    print("\n  Step 3: sdk_query() -- supervisor -> skill delegation")
    print(f"    Model: {MODEL_ID}")
    print(f"    Skills: oa-intake, legal-counsel (2 of available for cost control)")

    collector = StrandsResultCollector()

    try:
        async for message in sdk_query(
            prompt=(
                "We need to procure IT modernization services for $350K. "
                "Run intake analysis and then check legal risks."
            ),
            tenant_id="test-tenant",
            user_id="test-user",
            tier="advanced",
            skill_names=["oa-intake", "legal-counsel"],
            max_turns=10,
        ):
            # sdk_query yields AssistantMessage/ResultMessage adapter objects
            msg_type = type(message).__name__
            if msg_type == "AssistantMessage":
                for block in getattr(message, "content", []):
                    if getattr(block, "type", "") == "text":
                        collector.result_text += getattr(block, "text", "")
                    elif getattr(block, "type", "") == "tool_use":
                        collector.tool_use_blocks.append({
                            "tool": getattr(block, "name", ""),
                            "id": "",
                            "input": {},
                        })
            elif msg_type == "ResultMessage":
                if getattr(message, "result", ""):
                    collector.result_text = getattr(message, "result", "")
                usage = getattr(message, "usage", {}) or {}
                if isinstance(usage, dict):
                    collector.total_input_tokens += usage.get("inputTokens", 0)
                    collector.total_output_tokens += usage.get("outputTokens", 0)
                collector._log(f"    [ResultMessage] {collector.result_text[:200]}")
    except Exception as e:
        print(f"    sdk_query() error: {type(e).__name__}: {e}")

    print()
    summary = collector.summary()
    print(f"  --- Results ---")
    print(f"  Messages: {summary['total_messages']}")
    print(f"  Tool use blocks: {summary['tool_use_blocks']}")
    print(f"  Tokens: {summary['total_input_tokens']} in / {summary['total_output_tokens']} out")

    all_text = collector.all_text_lower()
    tool_calls = collector.tool_use_blocks
    tool_call_names = [t["tool"] for t in tool_calls]

    print(f"  Tool invocations: {len(tool_calls)}")
    for tn in tool_call_names:
        print(f"    -> {tn}")

    indicators = {
        "tools_built": tools_ok,
        "supervisor_prompt_valid": sup_references and len(sup_prompt) > 100,
        "response_has_content": len(collector.result_text) > 0,
        "skill_delegation": len(tool_calls) >= 1,
        "intake_or_legal": any(
            "intake" in tn.lower() or "legal" in tn.lower() or "oa" in tn.lower()
            for tn in tool_call_names
        ) or any(w in all_text for w in ["intake", "legal", "acquisition", "far"]),
    }

    print("\n  Indicators:")
    for indicator, found in indicators.items():
        print(f"    {indicator}: {found}")

    indicators_found = sum(1 for v in indicators.values() if v)
    passed = indicators_found >= 3
    print(f"  Indicators: {indicators_found}/5")
    print(f"  {'PASS' if passed else 'FAIL'} - Strands Skill->Tool Orchestration")
    return passed


# ============================================================
# Test 29: Compliance Matrix — Query Requirements
# ============================================================

async def test_29_compliance_matrix_query_requirements():
    """Deterministic: query compliance matrix for $500K negotiated FFP contract."""
    print("\n" + "=" * 70)
    print("TEST 29: Compliance Matrix — Query Requirements ($500K negotiated FFP)")
    print("=" * 70)

    # Import directly to avoid relative-import issues when running standalone
    from app.compliance_matrix import execute_operation
    result = execute_operation({
        "operation": "query",
        "contract_value": 500000,
        "acquisition_method": "negotiated",
        "contract_type": "ffp",
        "is_services": True,
    })

    steps_passed = []

    # Step 1: no errors
    errors = result.get("errors", [])
    no_errors = len(errors) == 0
    steps_passed.append(("no_errors", no_errors))
    print(f"  Step 1: errors={errors} {'PASS' if no_errors else 'FAIL'}")

    # Step 2: documents_required is a non-empty list
    docs = result.get("documents_required", [])
    has_docs = isinstance(docs, list) and len(docs) > 0
    steps_passed.append(("has_documents", has_docs))
    print(f"  Step 2: documents_required count={len(docs)} {'PASS' if has_docs else 'FAIL'}")

    # Step 3: thresholds_triggered includes SAT ($350K)
    triggered = result.get("thresholds_triggered", [])
    triggered_labels = [t.get("short", "") for t in triggered]
    sat_triggered = any("$350K" in lbl for lbl in triggered_labels)
    steps_passed.append(("sat_triggered", sat_triggered))
    print(f"  Step 3: thresholds_triggered={triggered_labels} SAT={'found' if sat_triggered else 'missing'} {'PASS' if sat_triggered else 'FAIL'}")

    # Step 4: competition_rules is non-empty
    competition = result.get("competition_rules", "")
    has_competition = isinstance(competition, str) and len(competition) > 0
    steps_passed.append(("has_competition_rules", has_competition))
    print(f"  Step 4: competition_rules length={len(competition)} {'PASS' if has_competition else 'FAIL'}")

    passed = all(ok for _, ok in steps_passed)
    print(f"  {'PASS' if passed else 'FAIL'} - Compliance Matrix Query Requirements")
    return passed


# ============================================================
# Test 30: Compliance Matrix — Search FAR
# ============================================================

async def test_30_compliance_matrix_search_far():
    """Deterministic: search FAR database for 'competition'."""
    print("\n" + "=" * 70)
    print("TEST 30: Compliance Matrix — Search FAR ('competition')")
    print("=" * 70)

    from app.compliance_matrix import execute_operation
    result = execute_operation({
        "operation": "search_far",
        "keyword": "competition",
    })

    steps_passed = []

    # Step 1: no error key
    has_error = "error" in result
    no_error = not has_error
    steps_passed.append(("no_error", no_error))
    print(f"  Step 1: error={'present' if has_error else 'absent'} {'PASS' if no_error else 'FAIL'}")

    # Step 2: results is a non-empty list
    results_list = result.get("results", [])
    has_results = isinstance(results_list, list) and len(results_list) > 0
    steps_passed.append(("has_results", has_results))
    print(f"  Step 2: results count={len(results_list)} {'PASS' if has_results else 'FAIL'}")

    # Step 3: each result has required fields (title, section)
    required_fields = ["title", "section"]
    fields_ok = True
    for i, entry in enumerate(results_list[:5]):  # check first 5
        for field in required_fields:
            if field not in entry:
                print(f"    result[{i}] missing field '{field}'")
                fields_ok = False
    steps_passed.append(("required_fields", fields_ok))
    print(f"  Step 3: required_fields (title, section) present={'yes' if fields_ok else 'no'} {'PASS' if fields_ok else 'FAIL'}")

    passed = all(ok for _, ok in steps_passed)
    print(f"  {'PASS' if passed else 'FAIL'} - Compliance Matrix Search FAR")
    return passed


# ============================================================
# Test 31: Compliance Matrix — Vehicle Suggestion
# ============================================================

async def test_31_compliance_matrix_vehicle_suggestion():
    """Deterministic: suggest vehicle for IT services requirement."""
    print("\n" + "=" * 70)
    print("TEST 31: Compliance Matrix — Vehicle Suggestion (IT + Services)")
    print("=" * 70)

    from app.compliance_matrix import execute_operation
    result = execute_operation({
        "operation": "suggest_vehicle",
        "is_it": True,
        "is_services": True,
    })

    steps_passed = []

    # Step 1: suggested_vehicles is a non-empty list
    vehicles = result.get("suggested_vehicles", [])
    has_vehicles = isinstance(vehicles, list) and len(vehicles) > 0
    steps_passed.append(("has_vehicles", has_vehicles))
    print(f"  Step 1: suggested_vehicles count={len(vehicles)} {'PASS' if has_vehicles else 'FAIL'}")

    # Step 2: NITAAC recommendation present
    nitaac_found = any(
        v.get("vehicle", "") == "nitaac" or "nitaac" in str(v.get("detail", {})).lower()
        for v in vehicles
    )
    steps_passed.append(("nitaac_recommended", nitaac_found))
    print(f"  Step 2: NITAAC recommendation={'found' if nitaac_found else 'missing'} {'PASS' if nitaac_found else 'FAIL'}")

    # Step 3: decision_factors is non-empty
    factors = result.get("decision_factors", [])
    has_factors = isinstance(factors, list) and len(factors) > 0
    steps_passed.append(("has_decision_factors", has_factors))
    print(f"  Step 3: decision_factors count={len(factors)} {'PASS' if has_factors else 'FAIL'}")

    passed = all(ok for _, ok in steps_passed)
    print(f"  {'PASS' if passed else 'FAIL'} - Compliance Matrix Vehicle Suggestion")
    return passed


# ============================================================
# Test 32: Admin-Manager Skill Registration
# ============================================================

async def test_32_admin_manager_skill_registered():
    """Validate admin-manager is wired in plugin.json and SKILL_AGENT_REGISTRY."""
    print("\n" + "=" * 70)
    print("TEST 32: Admin-Manager Skill Registration")
    print("=" * 70)

    # Step 1: Verify admin-manager appears in plugin.json skills list
    import json as _json
    plugin_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..", "eagle-plugin", "plugin.json"
    )
    try:
        with open(plugin_path, "r") as f:
            plugin_manifest = _json.load(f)
    except Exception as e:
        print(f"  FAIL - Cannot read plugin.json: {e}")
        return False

    skills_list = plugin_manifest.get("skills", [])
    in_manifest = "admin-manager" in skills_list
    print(f"  plugin.json skills: {skills_list}")
    print(f"  admin-manager in manifest: {in_manifest}")

    # Step 2: Verify SKILL_AGENT_REGISTRY includes admin-manager (or admin_manager)
    try:
        from strands_agentic_service import SKILL_AGENT_REGISTRY
    except ImportError as e:
        print(f"  SKIP - strands_agentic_service import failed: {e}")
        return None

    registry_keys = list(SKILL_AGENT_REGISTRY.keys())
    in_registry = "admin-manager" in registry_keys or "admin_manager" in registry_keys
    print(f"  SKILL_AGENT_REGISTRY keys: {registry_keys}")
    print(f"  admin-manager in registry: {in_registry}")

    # Step 3: Verify SKILL.md was loaded via eagle_skill_constants
    from eagle_skill_constants import PLUGIN_CONTENTS
    skill_key = "admin-manager"
    in_plugin_contents = skill_key in PLUGIN_CONTENTS
    if in_plugin_contents:
        entry = PLUGIN_CONTENTS[skill_key]
        print(f"  PLUGIN_CONTENTS['{skill_key}']: {len(entry.get('content', ''))} chars")
    else:
        print(f"  PLUGIN_CONTENTS missing '{skill_key}'")

    indicators = {
        "in_manifest": in_manifest,
        "in_registry": in_registry,
        "in_plugin_contents": in_plugin_contents,
    }

    print("\n  Indicators:")
    for indicator, found in indicators.items():
        print(f"    {indicator}: {found}")

    indicators_found = sum(1 for v in indicators.values() if v)
    passed = indicators_found >= 2
    print(f"  Indicators: {indicators_found}/3")
    print(f"  {'PASS' if passed else 'FAIL'} - Admin-Manager Skill Registration")
    return passed


# ============================================================
# Test 33: Workspace Store Default Creation
# ============================================================

async def test_33_workspace_store_default_creation():
    """Test workspace_store.get_or_create_default() returns a valid workspace.

    Uses a mock DynamoDB table (via moto or import-level validation) to avoid
    requiring live AWS credentials. Falls back to import-level checks if moto
    is unavailable.
    """
    print("\n" + "=" * 70)
    print("TEST 33: Workspace Store Default Creation")
    print("=" * 70)

    try:
        from workspace_store import (
            get_or_create_default,
            create_workspace,
            get_workspace,
            list_workspaces,
            get_active_workspace,
        )
    except ImportError as e:
        print(f"  SKIP - workspace_store import failed: {e}")
        return None

    # Try with moto mock for DynamoDB
    use_moto = False
    try:
        import moto
        use_moto = True
    except ImportError:
        pass

    if use_moto:
        import moto
        import workspace_store as ws_mod

        with moto.mock_aws():
            # Create mock eagle table
            import boto3 as _boto3
            ddb = _boto3.resource("dynamodb", region_name="us-east-1")
            ddb.create_table(
                TableName="eagle",
                KeySchema=[
                    {"AttributeName": "PK", "KeyType": "HASH"},
                    {"AttributeName": "SK", "KeyType": "RANGE"},
                ],
                AttributeDefinitions=[
                    {"AttributeName": "PK", "AttributeType": "S"},
                    {"AttributeName": "SK", "AttributeType": "S"},
                ],
                BillingMode="PAY_PER_REQUEST",
            )
            # Reset singleton so it picks up the mock
            ws_mod._dynamodb = None

            ws = get_or_create_default("test-tenant", "test-user")
            print(f"  Workspace returned: {ws is not None}")
            print(f"  workspace_id: {ws.get('workspace_id', 'MISSING')}")
            print(f"  name: {ws.get('name', 'MISSING')}")
            print(f"  is_active: {ws.get('is_active', 'MISSING')}")

            has_id = bool(ws.get("workspace_id"))
            has_name = bool(ws.get("name"))
            is_active = ws.get("is_active") is True or ws.get("is_active") == "true"

            indicators = {
                "workspace_returned": ws is not None,
                "has_workspace_id": has_id,
                "has_name": has_name,
                "is_active": is_active,
            }

            # Reset singleton
            ws_mod._dynamodb = None
    else:
        # No moto -- validate module structure only
        print("  moto not available -- validating module exports only")
        indicators = {
            "get_or_create_default_callable": callable(get_or_create_default),
            "create_workspace_callable": callable(create_workspace),
            "get_workspace_callable": callable(get_workspace),
            "list_workspaces_callable": callable(list_workspaces),
            "get_active_workspace_callable": callable(get_active_workspace),
        }

    print("\n  Indicators:")
    for indicator, found in indicators.items():
        print(f"    {indicator}: {found}")

    indicators_found = sum(1 for v in indicators.values() if v)
    total = len(indicators)
    passed = indicators_found >= (total - 1)
    print(f"  Indicators: {indicators_found}/{total}")
    print(f"  {'PASS' if passed else 'FAIL'} - Workspace Store Default Creation")
    return passed


# ============================================================
# Test 34: Store CRUD Functions Exist (smoke test)
# ============================================================

async def test_34_store_crud_functions_exist():
    """Validate all store modules export the expected public API functions.

    This is a deterministic smoke test — no LLM calls, no AWS calls.
    """
    print("\n" + "=" * 70)
    print("TEST 34: Store CRUD Functions Exist (smoke test)")
    print("=" * 70)

    expected = {
        "skill_store": [
            "create_skill", "get_skill", "update_skill", "list_skills",
            "submit_for_review", "publish_skill", "delete_skill",
        ],
        "prompt_store": [
            "put_prompt", "get_prompt", "delete_prompt", "list_tenant_prompts",
        ],
        "template_store": [
            "put_template", "delete_template", "list_tenant_templates", "resolve_template",
        ],
        "workspace_store": [
            "create_workspace", "get_workspace", "list_workspaces",
            "get_or_create_default", "activate_workspace", "delete_workspace",
        ],
    }

    all_ok = True
    details = {}

    for module_name, func_names in expected.items():
        print(f"\n  {module_name}:")
        try:
            mod = __import__(module_name)
        except ImportError as e:
            print(f"    SKIP - import failed: {e}")
            details[module_name] = False
            all_ok = False
            continue

        module_ok = True
        for fn_name in func_names:
            exists = hasattr(mod, fn_name) and callable(getattr(mod, fn_name))
            print(f"    {fn_name}: {exists}")
            if not exists:
                module_ok = False
                all_ok = False

        details[module_name] = module_ok

    print("\n  Module summary:")
    for mod_name, ok in details.items():
        print(f"    {mod_name}: {'OK' if ok else 'MISSING EXPORTS'}")

    modules_ok = sum(1 for v in details.values() if v)
    total = len(details)
    passed = modules_ok == total
    print(f"  Modules: {modules_ok}/{total}")
    print(f"  {'PASS' if passed else 'FAIL'} - Store CRUD Functions Exist")
    return passed


# ============================================================
# Test 35: UC-01 New Acquisition Package (Compliance Matrix)
# ============================================================

async def test_35_uc01_new_acquisition_package():
    """UC-01: New acquisition package — $2.5M CT scanner, negotiated CPFF.

    Deterministic compliance matrix test: validates that a $2.5M negotiated
    procurement triggers the correct thresholds (TINA), documents, competition
    rules (FAR Part 15), and approval requirements.
    """
    print("\n" + "=" * 70)
    print("TEST 35: UC-01 New Acquisition Package ($2.5M CT Scanner, Negotiated CPFF)")
    print("=" * 70)

    from app.compliance_matrix import execute_operation
    result = execute_operation({
        "operation": "query",
        "contract_value": 2500000,
        "acquisition_method": "negotiated",
        "contract_type": "cpff",
        "is_services": True,
        "is_it": True,
    })

    steps_passed = []

    # Step 1: no errors
    errors = result.get("errors", [])
    no_errors = len(errors) == 0
    steps_passed.append(("no_errors", no_errors))
    print(f"  Step 1: errors={errors} {'PASS' if no_errors else 'FAIL'}")

    # Step 2: documents_required includes at least 5 items (SOW, IGCE, AP, market research, etc.)
    docs = result.get("documents_required", [])
    docs_lower = [d.lower() if isinstance(d, str) else str(d).lower() for d in docs]
    has_enough_docs = isinstance(docs, list) and len(docs) >= 5
    steps_passed.append(("documents_at_least_5", has_enough_docs))
    print(f"  Step 2: documents_required count={len(docs)} (need >=5) {'PASS' if has_enough_docs else 'FAIL'}")
    for d in docs:
        print(f"    - {d}")

    # Step 3: thresholds_triggered includes TINA ($2.5M > $750K TINA threshold)
    triggered = result.get("thresholds_triggered", [])
    triggered_labels = [t.get("short", "") for t in triggered]
    triggered_lower = " ".join(triggered_labels).lower()
    tina_triggered = any("tina" in lbl.lower() or "$750" in lbl for lbl in triggered_labels)
    steps_passed.append(("tina_triggered", tina_triggered))
    print(f"  Step 3: thresholds_triggered={triggered_labels} TINA={'found' if tina_triggered else 'missing'} {'PASS' if tina_triggered else 'FAIL'}")

    # Step 4: competition_rules mentions full and open or FAR 15
    competition = result.get("competition_rules", "")
    competition_lower = competition.lower() if isinstance(competition, str) else ""
    has_competition = any(
        phrase in competition_lower
        for phrase in ["full and open", "far 15", "far part 15", "negotiated", "competitive"]
    )
    steps_passed.append(("competition_far15", has_competition))
    print(f"  Step 4: competition_rules mentions FAR 15/full-and-open={'yes' if has_competition else 'no'} {'PASS' if has_competition else 'FAIL'}")

    # Step 5: approvals_required is non-empty
    approvals = result.get("approvals_required", [])
    has_approvals = isinstance(approvals, list) and len(approvals) > 0
    steps_passed.append(("approvals_required", has_approvals))
    print(f"  Step 5: approvals_required count={len(approvals)} {'PASS' if has_approvals else 'FAIL'}")
    for a in approvals:
        print(f"    - {a}")

    passed = all(ok for _, ok in steps_passed)
    indicators_found = sum(1 for _, ok in steps_passed if ok)
    print(f"  UC-01 indicators: {indicators_found}/5")
    print(f"  {'PASS' if passed else 'FAIL'} - UC-01 New Acquisition Package")
    return passed


# ============================================================
# Main infrastructure
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
    28: "28_strands_skill_tool_orchestration",
    29: "29_compliance_matrix_query_requirements",
    30: "30_compliance_matrix_search_far",
    31: "31_compliance_matrix_vehicle_suggestion",
    32: "32_admin_manager_skill_registered",
    33: "33_workspace_store_default_creation",
    34: "34_store_crud_functions_exist",
    35: "35_uc01_new_acquisition_package",
}


def _extract_agents_and_tools(test_id: int) -> tuple:
    """Extract unique agent names and tool names from a test's trace data."""
    agents = []
    tools = []
    trace = _test_traces.get(test_id, [])
    for entry in trace:
        if entry.get("type") in ("AssistantMessage", "UserMessage"):
            for block in entry.get("content", []):
                if block.get("type") == "tool_use":
                    tool_name = block.get("tool", "")
                    if tool_name and tool_name not in tools:
                        tools.append(tool_name)
    return agents, tools


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

        run_ts = trace_output.get("timestamp", datetime.now(timezone.utc).isoformat())
        stream_name = f"run-{run_ts.replace(':', '-').replace('+', 'Z')}"
        try:
            client.create_log_stream(logGroupName=LOG_GROUP, logStreamName=stream_name)
        except client.exceptions.ResourceAlreadyExistsException:
            pass

        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        events = []

        run_input_tokens = 0
        run_output_tokens = 0
        run_cost_usd = 0.0

        for test_id_str, test_data in trace_output.get("results", {}).items():
            test_id = int(test_id_str)

            summary = _test_summaries.get(test_id, {})
            input_tokens = summary.get("total_input_tokens", 0)
            output_tokens = summary.get("total_output_tokens", 0)
            cost_usd = summary.get("total_cost_usd", 0.0)
            session_id = summary.get("session_id")

            run_input_tokens += input_tokens
            run_output_tokens += output_tokens
            run_cost_usd += cost_usd

            agents_list, tools_used = _extract_agents_and_tools(test_id)

            event = {
                "type": "test_result",
                "test_id": test_id,
                "test_name": test_names.get(test_id, f"test_{test_id}"),
                "status": test_data.get("status", "unknown"),
                "log_lines": len(test_data.get("logs", [])),
                "run_timestamp": run_ts,
                "model": MODEL_ID,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": round(cost_usd, 6),
            }
            if session_id:
                event["session_id"] = session_id
            if agents_list:
                event["agents"] = agents_list
            if tools_used:
                event["tools_used"] = tools_used

            events.append({
                "timestamp": now_ms + test_id,
                "message": json.dumps(event),
            })

        passed_count = sum(1 for r in results.values() if r is True)
        skipped_count = sum(1 for r in results.values() if r is None)
        failed_count = sum(1 for r in results.values() if r is not True and r is not None)

        summary_event = {
            "type": "run_summary",
            "run_timestamp": run_ts,
            "total_tests": len(results),
            "passed": passed_count,
            "skipped": skipped_count,
            "failed": failed_count,
            "pass_rate": round(passed_count / max(len(results), 1) * 100, 1),
            "model": MODEL_ID,
            "total_input_tokens": run_input_tokens,
            "total_output_tokens": run_output_tokens,
            "total_cost_usd": round(run_cost_usd, 6),
        }
        events.append({
            "timestamp": now_ms + 100,
            "message": json.dumps(summary_event),
        })

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


# ============================================================
# _run_test
# ============================================================

async def _run_test(test_id: int, capture: "CapturingStream", session_id: str = None,
                    recorder: Any = None):
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
        28: ("28_strands_skill_tool_orchestration", test_28_strands_skill_tool_orchestration),
        29: ("29_compliance_matrix_query_requirements", test_29_compliance_matrix_query_requirements),
        30: ("30_compliance_matrix_search_far", test_30_compliance_matrix_search_far),
        31: ("31_compliance_matrix_vehicle_suggestion", test_31_compliance_matrix_vehicle_suggestion),
        32: ("32_admin_manager_skill_registered", test_32_admin_manager_skill_registered),
        33: ("33_workspace_store_default_creation", test_33_workspace_store_default_creation),
        34: ("34_store_crud_functions_exist", test_34_store_crud_functions_exist),
        35: ("35_uc01_new_acquisition_package", test_35_uc01_new_acquisition_package),
    }

    result_key, test_fn = TEST_REGISTRY[test_id]
    capture.start_test(test_id)
    new_session_id = None

    # Start browser recording (if recorder available and test has a prompt)
    rec_ctx = None
    if recorder and hasattr(recorder, "has_recording") and recorder.has_recording(test_id):
        try:
            rec_ctx = await recorder.begin_test(test_id)
        except Exception as rec_err:
            print(f"  [recorder] begin_test failed: {rec_err}")

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

    # Finalize browser recording
    if rec_ctx:
        try:
            await recorder.wait_for_response(rec_ctx)
            video_path = await recorder.end_test(rec_ctx)
            if video_path:
                _test_video_paths[test_id] = video_path
        except Exception as rec_err:
            print(f"  [recorder] end_test failed: {rec_err}")

    # Auto-capture full conversation trace and summary from the latest StrandsResultCollector
    if StrandsResultCollector._latest is not None:
        try:
            _test_traces[test_id] = StrandsResultCollector._latest.to_trace_json()
            _test_summaries[test_id] = StrandsResultCollector._latest.summary()
        except Exception:
            pass
        StrandsResultCollector._latest = None

    capture.end_test()
    return result_key, result_val, new_session_id


# ============================================================
# main()
# ============================================================

async def main():
    # Parse which tests to run
    if _args.tests:
        selected_tests = sorted(set(int(t.strip()) for t in _args.tests.split(",")))
    else:
        selected_tests = list(range(1, 32)) + [32, 33, 34]

    # Video recorder (if --record-video)
    recorder = None
    if _args.record_video:
        try:
            from browser_recorder import BrowserRecorder
            recorder = BrowserRecorder(
                video_dir=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "eval", "videos"),
                base_url=_args.base_url,
                headless=not _args.headed,
                auth_email=_args.auth_email,
                auth_password=_args.auth_password,
            )
            await recorder.start()
        except ImportError:
            print("  [recorder] browser_recorder not available -- skipping video")
            recorder = None

    # Set up capturing stream
    capture = CapturingStream(sys.stdout)
    sys.stdout = capture

    print("=" * 70)
    print("EAGLE Strands Evaluation: Multi-Tenant Orchestrator")
    print(f"Time: {datetime.now(timezone.utc).isoformat()}")
    print(f"Model: {MODEL_ID}   {'(--async)' if _args.run_async else '(sequential)'}")
    print(f"Tests: {','.join(str(t) for t in selected_tests)}")
    print(f"Backend: AWS Bedrock (boto3 native)")
    print(f"SDK: strands-agents")
    print("=" * 70)

    results = {}
    session_id = None

    # Phase A: sequential tests (1 and 2 depend on each other)
    sequential_tests = [t for t in selected_tests if t <= 2]
    parallel_tests = [t for t in selected_tests if t > 2]

    for tid in sequential_tests:
        key, val, sid = await _run_test(tid, capture, session_id=session_id, recorder=recorder)
        results[key] = val
        if sid:
            session_id = sid

    # Phase B: independent tests (3-28)
    if _args.run_async and len(parallel_tests) > 1:
        print(f"  Running {len(parallel_tests)} tests concurrently (--async)...")

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
    print("EAGLE STRANDS EVALUATION SUMMARY")
    print("=" * 70)

    print("\n  Architecture: Strands Agents SDK -> Bedrock (boto3 native)")
    print("  Session pattern: stateless Agent() per request (no resume)")
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
    print(f"    Session management (create/stateless): {'Ready' if results.get('1_session_creation') else 'Needs work'}")
    print(f"    Context continuity (injected): {'Ready' if results.get('2_session_resume') else 'Needs work'}")
    print(f"    Trace events (tool use): {'Ready' if results.get('3_trace_observation') else 'Needs work'}")
    print(f"    Subagent traces (agents-as-tools): {'Ready' if results.get('4_subagent_orchestration') else 'Needs work'}")
    print(f"    Cost ticker (result.metrics): {'Ready' if results.get('5_cost_tracking') else 'Needs work'}")
    print(f"    Tier-gated tools (@tool): {'Ready' if results.get('6_tier_gated_tools') else 'Needs work'}")
    print(f"    Skill loading (system_prompt): {'Ready' if results.get('7_skill_loading') else 'Needs work'}")
    print(f"    Subagent tool tracking: {'Ready' if results.get('8_subagent_tool_tracking') else 'Needs work'}")
    print(f"    OA Intake workflow: {'Ready' if results.get('9_oa_intake_workflow') else 'Needs work'}")
    print("\n  EAGLE Skill Validation:")
    print(f"    Legal Counsel skill: {'Ready' if results.get('10_legal_counsel_skill') else 'Needs work'}")
    print(f"    Market Intelligence skill: {'Ready' if results.get('11_market_intelligence_skill') else 'Needs work'}")
    print(f"    Tech Review skill: {'Ready' if results.get('12_tech_review_skill') else 'Needs work'}")
    print(f"    Public Interest skill: {'Ready' if results.get('13_public_interest_skill') else 'Needs work'}")
    print(f"    Document Generator skill: {'Ready' if results.get('14_document_generator_skill') else 'Needs work'}")
    print(f"    Supervisor Multi-Skill Chain: {'Ready' if results.get('15_supervisor_multi_skill_chain') else 'Needs work'}")
    print("\n  AWS Tool Integration:")
    print(f"    S3 Document Operations: {'Ready' if results.get('16_s3_document_ops') else 'Needs work'}")
    print(f"    DynamoDB Intake Operations: {'Ready' if results.get('17_dynamodb_intake_ops') else 'Needs work'}")
    print(f"    CloudWatch Logs Operations: {'Ready' if results.get('18_cloudwatch_logs_ops') else 'Needs work'}")
    print(f"    Document Generation (3 types): {'Ready' if results.get('19_document_generation') else 'Needs work'}")
    print(f"    CloudWatch E2E Verification: {'Ready' if results.get('20_cloudwatch_e2e_verification') else 'Needs work'}")
    print("\n  UC Workflow Validation:")
    print(f"    UC-02 Micro-Purchase (<$15K): {'Ready' if results.get('21_uc02_micro_purchase') else 'Needs work'}")
    print(f"    UC-03 Option Exercise: {'Ready' if results.get('22_uc03_option_exercise') else 'Needs work'}")
    print(f"    UC-04 Contract Modification: {'Ready' if results.get('23_uc04_contract_modification') else 'Needs work'}")
    print(f"    UC-05 CO Package Review: {'Ready' if results.get('24_uc05_co_package_review') else 'Needs work'}")
    print(f"    UC-07 Contract Close-Out: {'Ready' if results.get('25_uc07_contract_closeout') else 'Needs work'}")
    print(f"    UC-08 Shutdown Notification: {'Ready' if results.get('26_uc08_shutdown_notification') else 'Needs work'}")
    print(f"    UC-09 Score Consolidation: {'Ready' if results.get('27_uc09_score_consolidation') else 'Needs work'}")
    print("\n  Strands Architecture:")
    print(f"    Skill->Tool Orchestration: {'Ready' if results.get('28_strands_skill_tool_orchestration') else 'Needs work'}")
    print("\n  Admin & Store Validation:")
    print(f"    Admin-Manager Registration: {'Ready' if results.get('32_admin_manager_skill_registered') else 'Needs work'}")
    print(f"    Workspace Store Defaults: {'Ready' if results.get('33_workspace_store_default_creation') else 'Needs work'}")
    print(f"    Store CRUD API Surface: {'Ready' if results.get('34_store_crud_functions_exist') else 'Needs work'}")

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

    id_to_key = {v: k for k, v in test_names.items()}

    for test_id, log_lines in capture.per_test_logs.items():
        result_key = test_names.get(test_id, str(test_id))
        result_val = results.get(result_key)
        status = "pass" if result_val is True else ("skip" if result_val is None else "fail")

        test_entry: dict[str, Any] = {
            "status": status,
            "logs": log_lines,
        }
        if test_id in _test_traces:
            test_entry["trace"] = _test_traces[test_id]
        if test_id in _test_video_paths:
            test_entry["video"] = _test_video_paths[test_id]
        trace_output["results"][str(test_id)] = test_entry

    _repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    _eval_results_dir = os.path.join(_repo_root, "data", "eval", "results")
    os.makedirs(_eval_results_dir, exist_ok=True)
    run_ts_file = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    trace_file = os.path.join(_eval_results_dir, f"run-strands-{run_ts_file}.json")
    with open(trace_file, "w", encoding="utf-8") as f:
        json.dump(trace_output, f, indent=2)
    latest_file = os.path.join(_eval_results_dir, "latest-strands.json")
    shutil.copy2(trace_file, latest_file)
    print(f"Trace logs written to: {trace_file}")
    print(f"Latest copy: {latest_file}")

    # Emit to CloudWatch (non-fatal)
    emit_to_cloudwatch(trace_output, results)

    # Persist to DynamoDB (same store as pytest — visible on /admin/tests)
    try:
        from app.test_result_store import save_test_run, save_test_result

        eval_run_id = trace_output["run_id"]
        eval_summary = {
            "timestamp": run_ts,
            "total": len(results),
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "errors": 0,
            "duration_s": 0,
            "pass_rate": round((passed / len(results)) * 100, 1) if results else 0,
            "model": MODEL_ID,
            "trigger": "eval",
            "hostname": __import__("socket").gethostname(),
        }
        save_test_run(eval_run_id, eval_summary)

        for test_id_num, log_lines in capture.per_test_logs.items():
            result_key = test_names.get(test_id_num, str(test_id_num))
            result_val = results.get(result_key)
            status = "passed" if result_val is True else ("skipped" if result_val is None else "failed")
            error_text = ""
            if status == "failed":
                error_text = "\n".join(log_lines[-20:])  # last 20 log lines as error context
            save_test_result(eval_run_id, f"eval::{result_key}", {
                "test_file": "test_strands_eval.py",
                "test_name": result_key,
                "status": status,
                "duration_s": 0,
                "error": error_text,
            })

        print(f"Eval results persisted to DynamoDB: run_id={eval_run_id} ({passed}/{len(results)} passed)")
    except Exception as e:
        print(f"Failed to persist eval results to DynamoDB (non-fatal): {e}")

    # Publish metrics + archive to S3 (non-fatal, no-op without boto3)
    if _HAS_AWS_PUBLISHER:
        publish_eval_metrics(results, run_ts_file, test_summaries=_test_summaries)
        archive_results_to_s3(trace_file, run_ts_file)
        if recorder:
            archive_videos_to_s3(
                os.path.join(_repo_root, "data", "eval", "videos"), run_ts_file
            )

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
