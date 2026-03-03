"""Strands Agentic Service Integration Test.

Exercises the full sdk_query() and sdk_query_single_skill() paths through
strands_agentic_service.py, verifying that adapter messages (AssistantMessage,
ResultMessage) work correctly with the same consumption pattern as
streaming_routes.py and main.py.

Run:
  AWS_PROFILE=eagle pytest tests/test_strands_service_integration.py -v -s
"""

import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


# -- Helpers ----------------------------------------------------------

async def _collect_messages(async_gen):
    """Collect all messages from an async generator."""
    messages = []
    async for msg in async_gen:
        messages.append(msg)
    return messages


# -- Tests ------------------------------------------------------------

@pytest.mark.asyncio
async def test_sdk_query_adapter_messages():
    """sdk_query() yields AssistantMessage then ResultMessage with correct interface."""
    from app.strands_agentic_service import sdk_query

    t0 = time.time()
    messages = await _collect_messages(
        sdk_query(
            prompt="What is a micro-purchase threshold?",
            tenant_id="test-tenant",
            user_id="test-user",
            tier="advanced",
            skill_names=["oa-intake"],
        )
    )
    elapsed = time.time() - t0

    print(f"\n  sdk_query elapsed: {elapsed:.2f}s")
    print(f"  Messages received: {len(messages)}")

    # Should get exactly 2 messages: AssistantMessage + ResultMessage
    assert len(messages) == 2, f"Expected 2 messages, got {len(messages)}"

    # Verify AssistantMessage
    assistant_msg = messages[0]
    assert type(assistant_msg).__name__ == "AssistantMessage", (
        f"First message should be AssistantMessage, got {type(assistant_msg).__name__}"
    )
    assert hasattr(assistant_msg, "content"), "AssistantMessage must have .content"
    assert isinstance(assistant_msg.content, list), "AssistantMessage.content must be a list"
    assert len(assistant_msg.content) >= 1, "AssistantMessage.content must have at least 1 block"

    # Verify text block
    text_block = assistant_msg.content[0]
    assert getattr(text_block, "type", None) == "text", "First block must be type='text'"
    assert hasattr(text_block, "text"), "Text block must have .text attribute"
    assert len(text_block.text) > 50, f"Response too short: {len(text_block.text)} chars"

    print(f"  AssistantMessage.content[0].text: {text_block.text[:100]}...")

    # Verify ResultMessage
    result_msg = messages[1]
    assert type(result_msg).__name__ == "ResultMessage", (
        f"Second message should be ResultMessage, got {type(result_msg).__name__}"
    )
    assert hasattr(result_msg, "result"), "ResultMessage must have .result"
    assert hasattr(result_msg, "usage"), "ResultMessage must have .usage"
    assert isinstance(result_msg.usage, dict), "ResultMessage.usage must be a dict"
    assert len(result_msg.result) > 50, f"Result too short: {len(result_msg.result)} chars"

    # Verify domain content
    result_lower = result_msg.result.lower()
    assert any(w in result_lower for w in [
        "micro-purchase", "micro purchase", "$15,000", "threshold", "simplified"
    ]), f"Response should mention micro-purchase concepts"

    print(f"  ResultMessage.result length: {len(result_msg.result)} chars")
    print("  PASS")


@pytest.mark.asyncio
async def test_sdk_query_single_skill_adapter():
    """sdk_query_single_skill() yields correct adapter messages."""
    from app.strands_agentic_service import sdk_query_single_skill

    t0 = time.time()
    messages = await _collect_messages(
        sdk_query_single_skill(
            prompt="What are the key FAR compliance requirements for sole-source contracts?",
            skill_name="legal-counsel",
            tenant_id="test-tenant",
            user_id="test-user",
            tier="advanced",
        )
    )
    elapsed = time.time() - t0

    print(f"\n  sdk_query_single_skill elapsed: {elapsed:.2f}s")
    print(f"  Messages received: {len(messages)}")

    assert len(messages) == 2
    assert type(messages[0]).__name__ == "AssistantMessage"
    assert type(messages[1]).__name__ == "ResultMessage"

    result_lower = messages[1].result.lower()
    assert any(w in result_lower for w in [
        "far", "sole source", "sole-source", "compliance", "competition", "justification"
    ]), "Response should mention FAR/sole-source concepts"

    print(f"  Response length: {len(messages[1].result)} chars")
    print("  PASS")


# -- CLI Runner -------------------------------------------------------

if __name__ == "__main__":
    asyncio.run(test_sdk_query_adapter_messages())
    asyncio.run(test_sdk_query_single_skill_adapter())
    print("\n ALL INTEGRATION TESTS PASSED\n")
