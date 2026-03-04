"""
Local file-based trace store — drop-in replacement for trace_store.py.

Stores traces as JSON in a local file (default: server/traces.json).
No DynamoDB or AWS credentials required.

Activate by setting: TRACE_STORE=local
"""
import json
import logging
import os
import threading
from datetime import datetime
from typing import Optional, List, Dict, Any

logger = logging.getLogger("eagle.telemetry.local_store")

TRACE_FILE = os.getenv(
    "TRACE_STORE_FILE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "traces.json"),
)

_lock = threading.Lock()


def _read_all() -> list:
    """Read all traces from the JSON file."""
    try:
        with open(TRACE_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _write_all(traces: list):
    """Write all traces to the JSON file."""
    os.makedirs(os.path.dirname(os.path.abspath(TRACE_FILE)), exist_ok=True)
    with open(TRACE_FILE, "w") as f:
        json.dump(traces, f, indent=2, default=str)


def store_trace(summary: dict, spans: list, trace_json: list = None) -> bool:
    """Persist a trace to the local JSON file."""
    trace_id = summary.get("trace_id", "unknown")
    now = datetime.utcnow()

    item = {
        "trace_id": trace_id,
        "tenant_id": summary.get("tenant_id", "default"),
        "user_id": summary.get("user_id", "anonymous"),
        "session_id": summary.get("session_id", "unknown"),
        "created_at": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "duration_ms": summary.get("duration_ms", 0),
        "total_input_tokens": summary.get("total_input_tokens", 0),
        "total_output_tokens": summary.get("total_output_tokens", 0),
        "total_cost_usd": float(summary.get("total_cost_usd", 0)),
        "tools_called": summary.get("tools_called", []),
        "agents_delegated": summary.get("agents_delegated", []),
        "span_count": len(spans),
        "spans": spans,
        "status": "error" if summary.get("error") else "success",
    }

    if trace_json:
        item["trace_json"] = trace_json

    with _lock:
        traces = _read_all()
        traces.insert(0, item)  # newest first
        # Keep max 500 traces locally
        traces = traces[:500]
        _write_all(traces)

    logger.info("Stored trace %s locally (%s)", trace_id, TRACE_FILE)
    return True


def get_traces(
    tenant_id: str = None,
    limit: int = 50,
    from_date: str = None,
) -> List[Dict[str, Any]]:
    """Fetch recent traces, optionally filtered by tenant."""
    with _lock:
        traces = _read_all()

    if tenant_id:
        traces = [t for t in traces if t.get("tenant_id") == tenant_id]
    if from_date:
        traces = [t for t in traces if t.get("date", "") >= from_date]

    # Return summaries (without trace_json for list view)
    results = []
    for t in traces[:limit]:
        summary = {k: v for k, v in t.items() if k not in ("trace_json", "spans")}
        summary["span_count"] = t.get("span_count", len(t.get("spans", [])))
        results.append(summary)
    return results


def get_trace_detail(tenant_id: str, trace_id: str, date: str = None) -> Optional[Dict]:
    """Fetch a single trace with full spans and trace_json."""
    with _lock:
        traces = _read_all()

    for t in traces:
        if t.get("trace_id") == trace_id:
            return t
    return None


def get_traces_by_session(session_id: str, limit: int = 20) -> List[Dict]:
    """Fetch traces for a specific session."""
    with _lock:
        traces = _read_all()

    return [t for t in traces if t.get("session_id") == session_id][:limit]
