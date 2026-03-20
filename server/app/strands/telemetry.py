"""
EAGLE Strands Telemetry

Langfuse OTEL exporter setup and trace attribute building.
"""

import logging
import os
import socket

logger = logging.getLogger("eagle.strands_agent")

_langfuse_injected = False


def ensure_langfuse_exporter():
    """Initialize Strands telemetry + Langfuse OTLP exporter (once).

    Must be called **before** the first ``Agent()`` so that the Agent's cached
    tracer references the real SDKTracerProvider (with the Langfuse exporter).
    """
    global _langfuse_injected
    if _langfuse_injected:
        return
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    if not public_key or not secret_key:
        return
    try:
        import base64

        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from strands.telemetry import StrandsTelemetry

        st = StrandsTelemetry()
        provider = st.tracer_provider

        base = os.getenv(
            "LANGFUSE_OTEL_ENDPOINT",
            "https://us.cloud.langfuse.com/api/public/otel",
        )
        endpoint = f"{base.rstrip('/')}/v1/traces"
        auth = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()

        exporter = OTLPSpanExporter(
            endpoint=endpoint,
            headers={"Authorization": f"Basic {auth}"},
        )
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        _langfuse_injected = True
        logger.info("[EAGLE] Langfuse OTEL exporter injected → %s", endpoint)
        logging.getLogger("opentelemetry.context").setLevel(logging.CRITICAL)
    except Exception as exc:
        logger.warning("[EAGLE] Langfuse exporter injection failed: %s", exc)


def build_trace_attrs(
    *,
    tenant_id: str,
    user_id: str,
    tier: str,
    session_id: str = "",
    subagent: str = "",
    username: str = "",
) -> dict:
    """Build trace_attributes dict for Langfuse/OTEL Agent() constructor.

    Tags every trace with sm-eagle source, local-vs-live environment,
    and hostname for source tracing.
    """
    hostname = socket.gethostname()
    dev_mode = os.getenv("DEV_MODE", "false").lower() == "true"
    environment = "local" if dev_mode else "live"

    attrs = {
        "eagle.source": "sm-eagle",
        "eagle.environment": environment,
        "eagle.hostname": hostname,
        "eagle.tenant_id": tenant_id,
        "eagle.user_id": user_id,
        "eagle.tier": tier,
        "eagle.session_id": session_id or "",
        "session.id": session_id or "",
        "langfuse.session.id": session_id or "",
        "langfuse.user.id": username or user_id or "",
    }
    if subagent:
        attrs["eagle.subagent"] = subagent

    try:
        local_ip = socket.gethostbyname(hostname)
        attrs["eagle.ip"] = local_ip
    except Exception:
        pass

    return attrs
