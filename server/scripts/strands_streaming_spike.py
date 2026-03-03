"""Strands streaming fidelity spike.

Usage:
  cd server && python3 scripts/strands_streaming_spike.py
"""

import asyncio
import json

try:
    from strands import Agent, tool
except Exception as e:
    raise SystemExit(f"Failed to import Strands. Install dependencies first: {e}")


@tool(name="inner_echo", description="Simple inner specialist tool")
def inner_echo(query: str) -> str:
    return f"INNER_ECHO: {query}"


@tool(name="delegate_inner", description="Delegates to inner agent")
def delegate_inner(query: str) -> str:
    inner = Agent(
        system_prompt="You are an inner specialist. Be concise.",
        tools=[inner_echo],
    )
    return str(inner(query))


async def main() -> None:
    outer = Agent(
        system_prompt=(
            "You are an orchestrator. Always call delegate_inner tool first, "
            "then return a short final answer."
        ),
        tools=[delegate_inner],
    )

    print("=== Strands Streaming Spike: raw event keys ===")
    async for event in outer.stream_async("Please summarize current acquisition need for lab equipment"):
        if isinstance(event, dict):
            print(f"keys={sorted(event.keys())}")
            print(json.dumps(event, default=str)[:2000])
        else:
            print(type(event).__name__, str(event)[:400])


if __name__ == "__main__":
    asyncio.run(main())
