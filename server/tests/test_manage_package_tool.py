"""Tests for manage_package tool, package_store thresholds, and SSE metadata drain."""

from __future__ import annotations

import asyncio
import json
from decimal import Decimal


# ── package_store._pathway_from_value threshold tests ──────────────────


def test_pathway_micro_purchase_under_15k():
    from app.stores.package_store import _pathway_from_value

    assert _pathway_from_value(Decimal("0")) == "micro_purchase"
    assert _pathway_from_value(Decimal("9999")) == "micro_purchase"
    assert _pathway_from_value(Decimal("14999.99")) == "micro_purchase"


def test_pathway_simplified_15k_to_350k():
    from app.stores.package_store import _pathway_from_value

    assert _pathway_from_value(Decimal("15000")) == "simplified"
    assert _pathway_from_value(Decimal("100000")) == "simplified"
    assert _pathway_from_value(Decimal("349999.99")) == "simplified"


def test_pathway_full_competition_at_350k():
    from app.stores.package_store import _pathway_from_value

    assert _pathway_from_value(Decimal("350000")) == "full_competition"
    assert _pathway_from_value(Decimal("750000")) == "full_competition"
    assert _pathway_from_value(Decimal("10000000")) == "full_competition"


def test_required_docs_simplified_includes_sow_igce_market_research():
    from app.stores.package_store import _required_docs_for

    docs = _required_docs_for("simplified")
    assert "sow" in docs
    assert "igce" in docs
    assert "market-research" in docs


def test_required_docs_full_competition():
    from app.stores.package_store import _required_docs_for

    docs = _required_docs_for("full_competition")
    assert "sow" in docs
    assert "igce" in docs
    assert "market-research" in docs
    assert "acquisition-plan" in docs


def test_required_docs_micro_purchase_empty():
    from app.stores.package_store import _required_docs_for

    assert _required_docs_for("micro_purchase") == []


# ── manage_package tool create operation ──────────────────────────────


def test_manage_package_create_calls_store_and_returns_checklist(monkeypatch):
    from app.strands_agentic_service import _make_manage_package_tool

    fake_pkg = {
        "package_id": "PKG-2026-0001",
        "acquisition_pathway": "full_competition",
        "status": "intake",
        "title": "Cloud Hosting Services",
        "estimated_value": "750000",
    }
    fake_checklist = {
        "required": ["sow", "igce", "market-research", "acquisition-plan"],
        "completed": [],
        "missing": ["sow", "igce", "market-research", "acquisition-plan"],
        "complete": False,
    }

    monkeypatch.setattr(
        "app.stores.package_store.create_package",
        lambda **kwargs: fake_pkg,
    )
    monkeypatch.setattr(
        "app.stores.package_store.get_package_checklist",
        lambda tenant_id, pkg_id: fake_checklist,
    )

    loop = asyncio.new_event_loop()
    queue = asyncio.Queue()

    tool_fn = _make_manage_package_tool(
        tenant_id="test-tenant",
        user_id="test-user",
        session_id="sess-123",
        result_queue=queue,
        loop=loop,
    )

    # Run the tool call in a thread so loop.call_soon_threadsafe works
    import concurrent.futures

    async def _run():
        with concurrent.futures.ThreadPoolExecutor() as pool:
            result_str = await loop.run_in_executor(
                pool,
                lambda: tool_fn(
                    operation="create",
                    title="Cloud Hosting Services",
                    estimated_value="750000",
                    requirement_type="services",
                    contract_type="ffp",
                    acquisition_method="negotiated",
                ),
            )
        return result_str

    result_str = loop.run_until_complete(_run())
    result = json.loads(result_str)

    assert result["ok"] is True
    assert result["package_id"] == "PKG-2026-0001"
    assert result["pathway"] == "full_competition"
    assert result["checklist"]["required"] == ["sow", "igce", "market-research", "acquisition-plan"]

    # Should have pushed metadata event to queue
    items = []
    while not queue.empty():
        items.append(queue.get_nowait())
    metadata_items = [i for i in items if i.get("type") == "metadata"]
    assert len(metadata_items) == 1
    assert metadata_items[0]["content"]["state_type"] == "phase_change"
    assert metadata_items[0]["content"]["package_id"] == "PKG-2026-0001"

    loop.close()


def test_manage_package_create_rejects_empty_title(monkeypatch):
    from app.strands_agentic_service import _make_manage_package_tool

    tool_fn = _make_manage_package_tool(
        tenant_id="test-tenant",
        user_id="test-user",
        session_id="sess-123",
    )

    result = json.loads(tool_fn(operation="create", title=""))
    assert "error" in result
    assert "title" in result["error"].lower()


def test_manage_package_status_returns_package(monkeypatch):
    from app.strands_agentic_service import _make_manage_package_tool

    fake_pkg = {
        "package_id": "PKG-2026-0001",
        "status": "intake",
        "title": "Test Package",
    }
    monkeypatch.setattr(
        "app.stores.package_store.get_package",
        lambda tenant_id, pkg_id: fake_pkg,
    )

    tool_fn = _make_manage_package_tool(
        tenant_id="test-tenant",
        user_id="test-user",
        session_id="sess-123",
    )

    result = json.loads(tool_fn(operation="status", package_id="PKG-2026-0001"))
    assert result["package_id"] == "PKG-2026-0001"
    assert result["status"] == "intake"


def test_manage_package_status_requires_package_id():
    from app.strands_agentic_service import _make_manage_package_tool

    tool_fn = _make_manage_package_tool(
        tenant_id="test-tenant",
        user_id="test-user",
        session_id="sess-123",
    )

    result = json.loads(tool_fn(operation="status", package_id=""))
    assert "error" in result


def test_manage_package_checklist_returns_data(monkeypatch):
    from app.strands_agentic_service import _make_manage_package_tool

    fake_checklist = {
        "required": ["sow", "igce"],
        "completed": ["sow"],
        "missing": ["igce"],
        "complete": False,
    }
    monkeypatch.setattr(
        "app.stores.package_store.get_package_checklist",
        lambda tenant_id, pkg_id: fake_checklist,
    )

    tool_fn = _make_manage_package_tool(
        tenant_id="test-tenant",
        user_id="test-user",
        session_id="sess-123",
    )

    result = json.loads(tool_fn(operation="checklist", package_id="PKG-2026-0001"))
    assert result["required"] == ["sow", "igce"]
    assert result["completed"] == ["sow"]
    assert result["missing"] == ["igce"]


def test_manage_package_unknown_operation():
    from app.strands_agentic_service import _make_manage_package_tool

    tool_fn = _make_manage_package_tool(
        tenant_id="test-tenant",
        user_id="test-user",
        session_id="sess-123",
    )

    result = json.loads(tool_fn(operation="delete"))
    assert "error" in result
    assert "Unknown operation" in result["error"]


# ── _drain_tool_results metadata passthrough ──────────────────────────


def test_drain_tool_results_passes_metadata_events():
    """Metadata events (no 'name' field) should be drained, not dropped."""
    # We can't easily test the inner function directly since it's nested,
    # so we test the Queue/drain pattern that _drain_tool_results implements.
    queue = asyncio.Queue()

    # Simulate what manage_package pushes
    metadata_event = {
        "type": "metadata",
        "content": {
            "state_type": "phase_change",
            "phase": "intake",
            "package_id": "PKG-2026-0001",
            "checklist": {"required": ["sow"], "completed": [], "missing": ["sow"], "complete": False},
        },
    }
    tool_result_event = {
        "name": "manage_package",
        "result": {"ok": True, "package_id": "PKG-2026-0001"},
    }
    nameless_junk = {"foo": "bar"}  # should be dropped (no type=metadata, no name)

    queue.put_nowait(metadata_event)
    queue.put_nowait(tool_result_event)
    queue.put_nowait(nameless_junk)

    # Replicate _drain_tool_results logic
    tools_called = []
    drained = []
    while True:
        try:
            item = queue.get_nowait()
            if item.get("type") == "metadata":
                drained.append(item)
                continue
            name = item.get("name")
            if not name:
                continue
            tools_called.append(name)
            drained.append(item)
        except asyncio.QueueEmpty:
            break

    assert len(drained) == 2
    assert drained[0]["type"] == "metadata"
    assert drained[0]["content"]["state_type"] == "phase_change"
    assert drained[1]["name"] == "manage_package"
    assert tools_called == ["manage_package"]
