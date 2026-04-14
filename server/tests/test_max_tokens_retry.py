"""Unit tests for MaxTokensReachedException retry path in sdk_query().

Covers:
- When the first Agent call raises MaxTokensReachedException, a second Agent
  is constructed and called (Agent instantiated twice).
- When _SUPERVISOR_MAX_TOKENS == _SUPERVISOR_MAX_TOKENS_CEILING, the ceiling
  guard prevents the retry (no second Agent).

Note: strands SDK may not be installed in all environments.  The tests mock
the exception class and the Agent/BedrockModel constructors so they run
without a live AWS environment.

Run: pytest server/tests/test_max_tokens_retry.py -v
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_server_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeMaxTokensReachedException(Exception):
    """Stand-in for strands.types.exceptions.MaxTokensReachedException."""


def _fake_tool_decorator(*args, **kwargs):
    """Pass-through stand-in for ``@strands.tool``.

    Supports both bare ``@tool`` and parameterized ``@tool(name=...)`` forms.
    """
    if len(args) == 1 and callable(args[0]) and not kwargs:
        return args[0]
    return lambda fn: fn


def _install_fake_strands_modules():
    """Install fake strands.* modules in sys.modules.

    strands_agentic_service.py imports at module load:
        from strands import Agent, tool
        from strands.agent.conversation_manager import SummarizingConversationManager
        from strands.models import BedrockModel
        from strands.models.bedrock import CacheConfig

    Plus sdk_query catches ``strands.types.exceptions.MaxTokensReachedException``.
    All of those names need to resolve before the module can be imported. Once
    imported, the per-test patches override the symbols on ``svc`` directly.

    Returns the list of sys.modules keys we installed so the fixture can clean
    them up.
    """
    installed: list[str] = []

    def _ensure(name: str) -> types.ModuleType:
        if name not in sys.modules:
            sys.modules[name] = types.ModuleType(name)
            installed.append(name)
        return sys.modules[name]

    strands = _ensure("strands")
    if not hasattr(strands, "Agent"):
        strands.Agent = MagicMock
    if not hasattr(strands, "tool"):
        strands.tool = _fake_tool_decorator

    _ensure("strands.agent")
    cm = _ensure("strands.agent.conversation_manager")
    if not hasattr(cm, "SummarizingConversationManager"):
        cm.SummarizingConversationManager = MagicMock

    models = _ensure("strands.models")
    if not hasattr(models, "BedrockModel"):
        models.BedrockModel = MagicMock
    bedrock = _ensure("strands.models.bedrock")
    if not hasattr(bedrock, "CacheConfig"):
        bedrock.CacheConfig = MagicMock

    _ensure("strands.types")
    exc = types.ModuleType("strands.types.exceptions")
    exc.MaxTokensReachedException = FakeMaxTokensReachedException
    exc.ContextWindowOverflowException = Exception
    sys.modules["strands.types.exceptions"] = exc
    installed.append("strands.types.exceptions")

    return installed


async def _drain(gen):
    """Drain an async generator and return all yielded items."""
    items = []
    async for item in gen:
        items.append(item)
    return items


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def patched_strands_exceptions(monkeypatch):
    """Inject fake strands.* modules so sdk_query can be imported.

    If real strands is already installed we leave the existing modules alone
    (real wins) but still replace ``strands.types.exceptions`` so that
    ``MaxTokensReachedException`` is the test's fake — that lets the test
    raise an exception type the production code's ``isinstance()`` will catch.
    """
    installed = _install_fake_strands_modules()

    yield sys.modules["strands.types.exceptions"]

    # Cleanup any modules we created (leave pre-existing real ones alone)
    for name in installed:
        sys.modules.pop(name, None)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def _patched_sdk_query_helpers(svc, *, max_tokens: int, ceiling: int):
    """Neutralize every helper sdk_query() calls before reaching the Agent.

    sdk_query is a sprawling function — workspace lookup, skill/service tool
    builders, session preloader, conversation manager, langfuse hooks, forced
    create_document reconciliation. To unit-test the retry decision in
    isolation we silence all of that and let the test focus on whether Agent
    is constructed once (ceiling guard) or twice (retry). Any helper added
    to sdk_query in the future that isn't patched here will surface as a
    test failure pointing at the relevant module symbol.
    """
    patches = [
        patch.object(svc, "BedrockModel", return_value=MagicMock()),
        patch.object(svc, "_ensure_langfuse_exporter"),
        patch.object(svc, "_maybe_fast_path_greeting", new=AsyncMock(return_value=None)),
        patch.object(svc, "build_skill_tools", return_value=[]),
        patch.object(svc, "_build_service_tools", return_value=([], {})),
        patch.object(svc, "_to_strands_messages", return_value=[]),
        patch.object(svc, "_build_conversation_manager", return_value=MagicMock()),
        patch.object(svc, "_get_active_model", return_value=("model-id", MagicMock())),
        patch.object(svc, "_cacheable_system_prompt", side_effect=lambda s: s),
        patch.object(svc, "_build_trace_attrs", return_value={}),
        patch.object(svc, "build_supervisor_prompt", return_value="system"),
        patch.object(svc, "_append_kb_sources", side_effect=lambda t, _: t),
        patch.object(
            svc,
            "_ensure_create_document_for_direct_request",
            new=AsyncMock(return_value=None),
        ),
        patch.object(svc, "_SUPERVISOR_MAX_TOKENS", max_tokens),
        patch.object(svc, "_SUPERVISOR_MAX_TOKENS_CEILING", ceiling),
        # Lazy imports inside sdk_query that need to resolve to no-ops
        patch(
            "app.session_preloader.preload_session_context",
            new=AsyncMock(return_value={}),
        ),
        patch("app.session_preloader.format_context_for_prompt", return_value=""),
        patch(
            "app.workspace_store.get_or_create_default",
            return_value={"workspace_id": "ws"},
        ),
    ]
    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        yield


class TestMaxTokensRetry:
    """Tests for the one-shot MaxTokensReachedException retry in sdk_query()."""

    @pytest.mark.asyncio
    async def test_retry_constructs_second_agent(self, patched_strands_exceptions):
        """First Agent raises MaxTokensReachedException → second Agent is built."""
        import app.strands_agentic_service as svc

        agent_instances = []

        def fake_agent_constructor(*args, **kwargs):
            inst = MagicMock()
            if not agent_instances:
                # First Agent: blow the output budget on call.
                inst.side_effect = FakeMaxTokensReachedException("output budget exhausted")
            else:
                # Second Agent (retry): return a normal result object.
                inst.return_value = MagicMock(metrics=MagicMock())
            agent_instances.append(inst)
            return inst

        with _patched_sdk_query_helpers(svc, max_tokens=32000, ceiling=64000), \
             patch.object(svc, "Agent", side_effect=fake_agent_constructor) as mock_agent_cls:
            await _drain(
                svc.sdk_query(
                    prompt="write a full SOW",
                    tenant_id="test-tenant",
                    user_id="test-user",
                )
            )

        assert mock_agent_cls.call_count == 2, (
            f"Expected Agent to be instantiated exactly twice (first + retry), "
            f"got {mock_agent_cls.call_count}"
        )

    @pytest.mark.asyncio
    async def test_ceiling_guard_skips_retry(self, patched_strands_exceptions):
        """When _SUPERVISOR_MAX_TOKENS == _SUPERVISOR_MAX_TOKENS_CEILING, no retry."""
        import app.strands_agentic_service as svc

        def fake_agent_constructor(*args, **kwargs):
            inst = MagicMock()
            inst.side_effect = FakeMaxTokensReachedException("budget exhausted")
            return inst

        # Set base == ceiling so _bumped <= _SUPERVISOR_MAX_TOKENS → guard fires.
        with _patched_sdk_query_helpers(svc, max_tokens=64000, ceiling=64000), \
             patch.object(svc, "Agent", side_effect=fake_agent_constructor) as mock_agent_cls:
            await _drain(
                svc.sdk_query(
                    prompt="write a full SOW",
                    tenant_id="test-tenant",
                )
            )

        # Only one Agent should have been constructed — no retry
        assert mock_agent_cls.call_count == 1, (
            f"Expected Agent to be instantiated exactly once (ceiling guard), "
            f"got {mock_agent_cls.call_count}"
        )
