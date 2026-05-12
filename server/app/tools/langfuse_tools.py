"""Langfuse trace query handler.

Backs the `langfuse_traces` agent tool. Reads creds from environment:

    LANGFUSE_PUBLIC_KEY   — pk-lf-...
    LANGFUSE_SECRET_KEY   — sk-lf-...
    LANGFUSE_HOST         — https://cloud.langfuse.com (default)

Operations:
    list_recent     — recent traces (filterable)
    get_trace       — single trace by id
    search_errors   — recent traces with level=ERROR
    health_summary  — error rate / avg latency / cost over a window

The handler MUST NOT raise — Langfuse outages should degrade gracefully so
the rest of the diagnostics tool keeps working. All paths return a dict;
failures surface as {"error": "...", "operation": "..."}.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import urllib.parse
import urllib.request
import urllib.error
import base64
import json

logger = logging.getLogger("eagle.tools.langfuse")

_DEFAULT_HOST = "https://cloud.langfuse.com"
_TIMEOUT_S = 8.0


def _parse_relative(token: str) -> datetime | None:
    """Parse '-1h', '-30m', '-24h', '-7d' relative offsets. Returns UTC datetime."""
    token = (token or "").strip()
    if not token.startswith("-") or len(token) < 3:
        return None
    try:
        n = int(token[1:-1])
    except ValueError:
        return None
    unit = token[-1].lower()
    delta = {"m": timedelta(minutes=n), "h": timedelta(hours=n), "d": timedelta(days=n)}.get(unit)
    if delta is None:
        return None
    return datetime.now(timezone.utc) - delta


def _resolve_time(token: str) -> str | None:
    """Resolve a token (ISO 8601 or relative) to ISO 8601 UTC. Returns None if blank."""
    if not token:
        return None
    rel = _parse_relative(token)
    if rel is not None:
        return rel.isoformat()
    return token  # assume caller passed valid ISO 8601


def _auth_header() -> str | None:
    pk = os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()
    sk = os.getenv("LANGFUSE_SECRET_KEY", "").strip()
    if not pk or not sk:
        return None
    raw = f"{pk}:{sk}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


def _request(path: str, query: dict[str, Any] | None = None) -> dict[str, Any]:
    auth = _auth_header()
    if not auth:
        return {
            "error": "Langfuse credentials missing — set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY",
            "configured": False,
        }
    host = os.getenv("LANGFUSE_HOST", _DEFAULT_HOST).rstrip("/")
    qs = ""
    if query:
        clean = {k: v for k, v in query.items() if v not in (None, "")}
        if clean:
            qs = "?" + urllib.parse.urlencode(clean)
    url = f"{host}{path}{qs}"
    req = urllib.request.Request(url, headers={"Authorization": auth, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        return {"error": f"langfuse http {exc.code}: {exc.reason}", "url": url}
    except urllib.error.URLError as exc:
        return {"error": f"langfuse network: {exc.reason}", "url": url}
    except (TimeoutError, json.JSONDecodeError) as exc:
        return {"error": f"langfuse: {exc}", "url": url}


def exec_langfuse_traces(params: dict, tenant_id: str) -> dict:
    """Query Langfuse traces. See module docstring for operations."""
    operation = (params.get("operation") or "list_recent").strip()
    limit = max(1, min(int(params.get("limit") or 20), 100))

    if operation == "get_trace":
        trace_id = (params.get("trace_id") or "").strip()
        if not trace_id:
            return {"error": "trace_id required for get_trace", "operation": operation}
        return _request(f"/api/public/traces/{urllib.parse.quote(trace_id)}")

    common_q: dict[str, Any] = {
        "limit": limit,
        "userId": params.get("user_id_filter") or None,
        "sessionId": params.get("session_id_filter") or None,
        "fromTimestamp": _resolve_time(params.get("start_time", "")),
        "toTimestamp": _resolve_time(params.get("end_time", "")),
    }
    tags = (params.get("tags_filter") or "").strip()
    if tags:
        common_q["tags"] = tags

    if operation == "list_recent":
        return _request("/api/public/traces", common_q)

    if operation == "search_errors":
        # Pull traces in window; bucket by ERROR-level observations.
        traces = _request("/api/public/traces", {**common_q, "limit": min(limit * 2, 100)})
        if "error" in traces:
            return traces
        items = traces.get("data") or traces.get("traces") or []
        errors = [t for t in items if (t.get("level") or "").upper() == "ERROR"
                  or any((o.get("level") or "").upper() == "ERROR"
                         for o in (t.get("observations") or []))]
        return {
            "operation": "search_errors",
            "window_from": common_q.get("fromTimestamp"),
            "window_to": common_q.get("toTimestamp"),
            "error_count": len(errors),
            "traces": errors[:limit],
        }

    if operation == "health_summary":
        # Default window: last 1h if not specified.
        if not common_q.get("fromTimestamp"):
            common_q["fromTimestamp"] = _resolve_time("-1h")
        traces = _request("/api/public/traces", {**common_q, "limit": 100})
        if "error" in traces:
            return traces
        items = traces.get("data") or traces.get("traces") or []
        total = len(items)
        errors = sum(1 for t in items if (t.get("level") or "").upper() == "ERROR")
        latencies = [t.get("latency") for t in items if isinstance(t.get("latency"), (int, float))]
        costs = [t.get("totalCost") for t in items if isinstance(t.get("totalCost"), (int, float))]
        avg_latency = sum(latencies) / len(latencies) if latencies else None
        total_cost = sum(costs) if costs else 0.0
        return {
            "operation": "health_summary",
            "window_from": common_q.get("fromTimestamp"),
            "window_to": common_q.get("toTimestamp"),
            "trace_count": total,
            "error_count": errors,
            "error_rate_pct": round((errors / total) * 100, 2) if total else 0.0,
            "avg_latency_ms": round(avg_latency, 1) if avg_latency is not None else None,
            "total_cost_usd": round(total_cost, 4),
        }

    return {
        "error": f"unknown operation: {operation}",
        "operation": operation,
        "valid_operations": ["list_recent", "get_trace", "search_errors", "health_summary"],
    }
