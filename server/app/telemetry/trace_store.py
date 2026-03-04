"""
Trace store — routes to local file store or DynamoDB based on TRACE_STORE env var.

Set TRACE_STORE=local (default) to use a local JSON file (no AWS needed).
Set TRACE_STORE=dynamodb to use the existing 'eagle' DynamoDB table.
"""
import os

_TRACE_STORE_BACKEND = os.getenv("TRACE_STORE", "local").lower()

if _TRACE_STORE_BACKEND == "local":
    # Local file-based store — no AWS credentials required
    from .local_trace_store import (  # noqa: F401
        store_trace,
        get_traces,
        get_trace_detail,
        get_traces_by_session,
    )
else:
    # DynamoDB store — requires AWS credentials and 'eagle' table
    from .dynamodb_trace_store import (  # noqa: F401
        store_trace,
        get_traces,
        get_trace_detail,
        get_traces_by_session,
    )
