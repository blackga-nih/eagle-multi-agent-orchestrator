"""
Structured logging context for EAGLE.

Provides a contextvars-based mechanism to inject tenant_id and user_id into
every log record, plus a JSON formatter for CloudWatch-friendly output.

Usage in request handlers:
    set_log_context(tenant_id="acme", user_id="user-1", session_id="s-123")
    # ... all logger calls in this async context now include tenant/user/session
    clear_log_context()

The JSON formatter produces one-line JSON objects:
    {"ts":"2026-03-04T12:00:00","level":"INFO","logger":"eagle","tenant_id":"acme","user_id":"user-1","session_id":"s-123","msg":"..."}
"""
import contextvars
import json
import logging
from datetime import datetime, timezone

# Context variables — set per-request, inherited by async tasks
_tenant_id: contextvars.ContextVar[str] = contextvars.ContextVar("tenant_id", default="")
_user_id: contextvars.ContextVar[str] = contextvars.ContextVar("user_id", default="")
_session_id: contextvars.ContextVar[str] = contextvars.ContextVar("session_id", default="")


def set_log_context(
    tenant_id: str = "",
    user_id: str = "",
    session_id: str = "",
):
    """Set the per-request logging context (call at request entry)."""
    if tenant_id:
        _tenant_id.set(tenant_id)
    if user_id:
        _user_id.set(user_id)
    if session_id:
        _session_id.set(session_id)


def clear_log_context():
    """Reset context vars (call at request exit or in middleware)."""
    _tenant_id.set("")
    _user_id.set("")
    _session_id.set("")


class EagleContextFilter(logging.Filter):
    """Inject tenant_id, user_id, session_id into every LogRecord."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.tenant_id = _tenant_id.get("")  # type: ignore[attr-defined]
        record.user_id = _user_id.get("")  # type: ignore[attr-defined]
        record.session_id = _session_id.get("")  # type: ignore[attr-defined]
        return True


class JSONFormatter(logging.Formatter):
    """Single-line JSON log formatter for CloudWatch ingestion."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "tenant_id": getattr(record, "tenant_id", ""),
            "user_id": getattr(record, "user_id", ""),
            "session_id": getattr(record, "session_id", ""),
            "msg": record.getMessage(),
        }
        # Drop empty context fields to keep logs compact
        entry = {k: v for k, v in entry.items() if v}
        if record.exc_info and record.exc_info[1]:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def configure_logging(level: int = logging.INFO):
    """Replace the root logger's handler with structured JSON output.

    Call once at startup (main.py) *instead of* logging.basicConfig().
    """
    root = logging.getLogger()
    root.setLevel(level)

    # Remove existing handlers
    for h in root.handlers[:]:
        root.removeHandler(h)

    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    handler.addFilter(EagleContextFilter())
    root.addHandler(handler)
