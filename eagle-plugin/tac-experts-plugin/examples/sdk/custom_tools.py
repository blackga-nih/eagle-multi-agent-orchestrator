#!/usr/bin/env python3
"""
Custom Tools + MCP Server — Claude Agent SDK

Demonstrates the @tool decorator and create_sdk_mcp_server() pattern
from TAC Lesson 20 (Beyond MCP). Shows how to:

1. Define custom tools with @dataclass inputs
2. Bundle tools into an MCP server
3. Register tools with correct mcp__{server}__{name} naming
4. Combine custom tools with built-in tools
5. Gate tools by subscription tier
6. Add SDK hooks for tool observability

Key TAC Patterns:
  - @tool decorator with @dataclass input schema
  - MCP tool naming: mcp__{server_name}__{tool_name}
  - Tier-gated tool access control
  - Hook-based tool call logging

Usage:
    python examples/sdk/custom_tools.py

Requires:
    pip install claude-agent-sdk
"""

import asyncio
import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from claude_agent_sdk import (
    ClaudeAgentOptions,
    HookMatcher,
    PostToolUseHookInput,
    PreToolUseHookInput,
    HookContext,
    create_sdk_mcp_server,
    query,
    tool,
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Custom Tools — @tool decorator pattern
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Step 1: Define input schemas as @dataclass
# Each field becomes a tool parameter with its type.

@dataclass
class ProductLookupInput:
    """Look up a product by name."""
    product_name: str


@dataclass
class CalculateTotalInput:
    """Calculate order total with tax."""
    product_name: str
    quantity: int
    tax_rate: float


@dataclass
class CreateOrderInput:
    """Create a new order."""
    customer_name: str
    product_name: str
    quantity: int


# Step 2: Define tool functions with @tool decorator
# Signature: @tool(name, description, InputDataclass)
# Return: {"content": [{"type": "text", "text": "..."}]}

PRODUCT_CATALOG = {
    "widget pro": {"id": "WP-001", "name": "Widget Pro", "price": 29.99, "stock": 150},
    "widget lite": {"id": "WL-002", "name": "Widget Lite", "price": 9.99, "stock": 500},
    "mega widget": {"id": "MW-003", "name": "Mega Widget", "price": 99.99, "stock": 25},
}


@tool("lookup_product", "Look up product details by name", ProductLookupInput)
async def lookup_product_tool(input: ProductLookupInput) -> dict:
    """Look up a product from the catalog."""
    key = input.product_name.lower()
    result = PRODUCT_CATALOG.get(key)
    if result:
        return {"content": [{"type": "text", "text": json.dumps(result)}]}
    return {"content": [{"type": "text", "text": json.dumps({
        "error": f"Product '{input.product_name}' not found",
        "available": list(PRODUCT_CATALOG.keys()),
    })}]}


@tool("calculate_total", "Calculate order total with tax", CalculateTotalInput)
async def calculate_total_tool(input: CalculateTotalInput) -> dict:
    """Calculate order total including tax."""
    key = input.product_name.lower()
    product = PRODUCT_CATALOG.get(key)
    if not product:
        return {"content": [{"type": "text", "text": json.dumps({
            "error": f"Product '{input.product_name}' not found"
        })}]}

    subtotal = product["price"] * input.quantity
    tax = subtotal * input.tax_rate
    total = subtotal + tax

    return {"content": [{"type": "text", "text": json.dumps({
        "product": product["name"],
        "unit_price": product["price"],
        "quantity": input.quantity,
        "subtotal": round(subtotal, 2),
        "tax_rate": input.tax_rate,
        "tax": round(tax, 2),
        "total": round(total, 2),
    })}]}


@tool("create_order", "Create a new order", CreateOrderInput)
async def create_order_tool(input: CreateOrderInput) -> dict:
    """Create an order (demo — logs but doesn't persist)."""
    key = input.product_name.lower()
    product = PRODUCT_CATALOG.get(key)
    if not product:
        return {"content": [{"type": "text", "text": json.dumps({
            "error": f"Product '{input.product_name}' not found"
        })}]}

    if product["stock"] < input.quantity:
        return {"content": [{"type": "text", "text": json.dumps({
            "error": f"Insufficient stock: {product['stock']} available, {input.quantity} requested"
        })}]}

    order = {
        "order_id": f"ORD-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "customer": input.customer_name,
        "product": product["name"],
        "quantity": input.quantity,
        "total": round(product["price"] * input.quantity, 2),
        "status": "confirmed",
    }
    return {"content": [{"type": "text", "text": json.dumps(order)}]}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  MCP Server — Bundle tools into a server
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Step 3: Create MCP server from tools
# Tool naming convention: mcp__{server_name}__{tool_name}

inventory_server = create_sdk_mcp_server(
    "inventory",
    tools=[lookup_product_tool, calculate_total_tool, create_order_tool],
)

# This registers 3 tools:
#   mcp__inventory__lookup_product
#   mcp__inventory__calculate_total
#   mcp__inventory__create_order


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SDK Hooks — Tool call observability
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Step 4: Add hooks for tool call logging and validation

tool_call_log: list[dict] = []


async def pre_tool_hook(input: PreToolUseHookInput, context: HookContext):
    """Log tool calls before execution."""
    tool_name = input.tool_name
    tool_input = input.tool_input

    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "event": "pre_tool_use",
        "tool": tool_name,
        "input_keys": list(tool_input.keys()) if isinstance(tool_input, dict) else [],
    }
    tool_call_log.append(log_entry)
    print(f"  [hook:pre] {tool_name}({json.dumps(tool_input)[:80]})")

    # Return None to allow — return {"decision": "block", "reason": "..."} to deny
    return None


async def post_tool_hook(input: PostToolUseHookInput, context: HookContext):
    """Log tool results after execution."""
    tool_name = input.tool_name
    tool_result = input.tool_result

    # Extract result text for logging
    result_text = ""
    if isinstance(tool_result, dict):
        content = tool_result.get("content", [])
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                result_text = block.get("text", "")[:100]

    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "event": "post_tool_use",
        "tool": tool_name,
        "result_preview": result_text,
    }
    tool_call_log.append(log_entry)
    print(f"  [hook:post] {tool_name} -> {result_text[:60]}...")

    return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Tier-Gated Tool Access
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Step 5: Map subscription tiers to tool access

TIER_TOOL_ACCESS = {
    "basic": [
        "mcp__inventory__lookup_product",     # Read-only catalog access
    ],
    "advanced": [
        "mcp__inventory__lookup_product",
        "mcp__inventory__calculate_total",    # + pricing calculations
    ],
    "premium": [
        "mcp__inventory__lookup_product",
        "mcp__inventory__calculate_total",
        "mcp__inventory__create_order",       # + order creation
        "Read",                                # + file access
    ],
}


def build_options(
    tier: str = "premium",
    max_turns: int = 5,
    max_budget_usd: float = 0.10,
) -> ClaudeAgentOptions:
    """Build ClaudeAgentOptions with tier-gated tools and hooks."""
    env = {}
    if os.environ.get("CLAUDE_CODE_USE_BEDROCK") == "1":
        env["CLAUDE_CODE_USE_BEDROCK"] = "1"
        env["AWS_REGION"] = os.environ.get("AWS_REGION", "us-east-1")

    return ClaudeAgentOptions(
        model="haiku",
        system_prompt=(
            f"You are an inventory assistant (tier: {tier}). "
            "Help users look up products, calculate totals, and place orders. "
            "Use the inventory tools to answer questions. "
            "Always show prices and calculations clearly."
        ),
        allowed_tools=TIER_TOOL_ACCESS.get(tier, TIER_TOOL_ACCESS["basic"]),
        mcp_servers={"inventory": inventory_server},
        hooks=[
            HookMatcher(
                tool_name="mcp__inventory__.*",
                pre_tool_use=pre_tool_hook,
                post_tool_use=post_tool_hook,
            ),
        ],
        permission_mode="bypassPermissions",
        max_turns=max_turns,
        max_budget_usd=max_budget_usd,
        cwd=os.getcwd(),
        env=env,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Message Processing
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def run_query(prompt: str, tier: str = "premium") -> dict[str, Any]:
    """Run a single query with custom tools."""
    options = build_options(tier=tier)

    print(f"\n{'─' * 50}")
    print(f"Query ({tier}): {prompt}")
    print(f"Tools: {', '.join(TIER_TOOL_ACCESS[tier])}")
    print(f"{'─' * 50}")

    result_text = ""
    session_id = None
    cost = 0.0

    async for message in query(prompt=prompt, options=options):
        msg_type = type(message).__name__

        if msg_type == "SystemMessage":
            if hasattr(message, "data") and isinstance(message.data, dict):
                session_id = message.data.get("session_id")

        elif msg_type == "AssistantMessage":
            content = getattr(message, "content", [])
            for block in content:
                if hasattr(block, "text"):
                    result_text = block.text

        elif msg_type == "ResultMessage":
            cost = getattr(message, "cost_usd", 0.0) or 0.0
            if not session_id:
                session_id = getattr(message, "session_id", None)

    print(f"\n[result] {result_text[:300]}")
    print(f"[cost] ${cost:.4f} | [hooks] {len(tool_call_log)} events logged")

    return {
        "session_id": session_id,
        "result": result_text,
        "cost": cost,
        "tool_calls": len(tool_call_log),
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Main — Demo
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def main():
    """Run the custom tools demo."""
    # Demo 1: Basic tier — lookup only
    await run_query(
        "What products do you have available?",
        tier="basic",
    )

    # Demo 2: Advanced tier — lookup + pricing
    await run_query(
        "How much would 5 Widget Pro units cost with 8% tax?",
        tier="advanced",
    )

    # Demo 3: Premium tier — full access including orders
    await run_query(
        "I'd like to order 3 Mega Widgets for customer 'Acme Corp'.",
        tier="premium",
    )

    # Print hook audit log
    print(f"\n{'=' * 50}")
    print("Tool Call Audit Log")
    print(f"{'=' * 50}")
    for entry in tool_call_log:
        print(f"  {entry['timestamp']} | {entry['event']} | {entry['tool']}")


if __name__ == "__main__":
    asyncio.run(main())
