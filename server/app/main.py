"""
EAGLE – NCI Acquisition Assistant
Full-featured FastAPI application merging:
- Original multi-tenant architecture (SSE streaming, admin HTML pages, tenant costs)
- EAGLE option1-simple (Anthropic SDK, document export, S3 browser, admin dashboard, WebSocket)
"""
import os as _os
from pathlib import Path as _Path
from dotenv import load_dotenv
# Load .env from project root (parent of app/) — must happen before any other imports
_env_path = _Path(__file__).resolve().parent.parent / ".env"
print(f"[EAGLE STARTUP] .env path: {_env_path} exists={_env_path.exists()}")
if _env_path.exists():
    load_dotenv(str(_env_path), override=True)
    print(f"[EAGLE STARTUP] Loaded .env, ANTHROPIC_API_KEY set={bool(_os.getenv('ANTHROPIC_API_KEY'))}, DEV_MODE={_os.getenv('DEV_MODE')}")
else:
    load_dotenv(override=True)
    print(f"[EAGLE STARTUP] No .env found at {_env_path}, using defaults")

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import time
import logging
import os

from .cognito_auth import extract_user_context
from .subscription_service import SubscriptionService
from .streaming_routes import create_streaming_router

# Route modules
from .routes.chat import router as chat_router
from .routes.sessions import router as sessions_router
from .routes.documents import router as documents_router
from .routes.admin import router as admin_router
from .routes.packages import router as packages_router
from .routes.workspaces import router as workspaces_router
from .routes.tenants import router as tenants_router
from .routes.user import router as user_router
from .routes.templates import router as templates_router
from .routes.skills import router as skills_router
from .routes.misc import router as misc_router
from .routes.traces import router as traces_router

# ── Logging ──────────────────────────────────────────────────────────
from .telemetry.log_context import configure_logging
configure_logging(level=logging.INFO)
logger = logging.getLogger("eagle")

# ── Langfuse OTEL Tracing ────────────────────────────────────────────
def _setup_langfuse():
    """Initialize Langfuse OTEL exporter if credentials are set.

    When LANGFUSE_PUBLIC_KEY is absent this is a silent no-op so local dev
    and CI work without any trace backend.
    """
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    if not public_key or not secret_key:
        return
    try:
        import base64
        from strands.telemetry import StrandsTelemetry
        base = os.getenv(
            "LANGFUSE_OTEL_ENDPOINT",
            "https://us.cloud.langfuse.com/api/public/otel",
        )
        # OTLPSpanExporter only auto-appends /v1/traces for the generic env var,
        # not for explicit endpoint= args, so we must include the full path.
        endpoint = f"{base.rstrip('/')}/v1/traces"
        auth = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
        StrandsTelemetry().setup_otlp_exporter(
            endpoint=endpoint,
            headers={"Authorization": f"Basic {auth}"},
        )
        logger.info("[EAGLE STARTUP] Langfuse OTEL exporter enabled → %s", endpoint)
    except Exception as exc:
        logger.warning("[EAGLE STARTUP] Langfuse setup failed (non-fatal): %s", exc)

_setup_langfuse()

# ── App ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="EAGLE – NCI Acquisition Assistant",
    version="4.0.0",
    description="Multi-tenant acquisition intake system with Anthropic SDK, auth, persistence, and analytics"
)

# ── CORS Middleware ──────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API Request Telemetry Middleware ─────────────────────────────────
_SKIP_PATHS = {"/api/health", "/favicon.ico", "/_next", "/api/logs"}


@app.middleware("http")
async def api_request_telemetry(request: Request, call_next):
    path = request.url.path
    if any(path.startswith(p) for p in _SKIP_PATHS):
        return await call_next(request)

    start = time.time()
    response = await call_next(request)
    duration_ms = int((time.time() - start) * 1000)

    try:
        auth_header = request.headers.get("authorization")
        user, _ = extract_user_context(auth_header)
        tenant_id = user.tenant_id
    except Exception:
        tenant_id = "unknown"

    try:
        from .agentcore.observability import record_metric
        record_metric("eagle.api_duration_ms", float(duration_ms), {
            "method": request.method,
            "path": path,
            "status_code": str(response.status_code),
            "tenant_id": tenant_id,
        })
    except Exception:
        pass

    return response


# ── Initialize services ──────────────────────────────────────────────
subscription_service = SubscriptionService()

# ── Include routers ──────────────────────────────────────────────────
# SSE streaming router (preserved from C3 integration)
streaming_router = create_streaming_router(subscription_service)
app.include_router(streaming_router)

# Extracted route modules
app.include_router(chat_router)
app.include_router(sessions_router)
app.include_router(documents_router)
app.include_router(admin_router)
app.include_router(packages_router)
app.include_router(workspaces_router)
app.include_router(tenants_router)
app.include_router(user_router)
app.include_router(templates_router)
app.include_router(skills_router)
app.include_router(misc_router)
app.include_router(traces_router)


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("APP_PORT", "8000"))
    uvicorn.run(app, host="127.0.0.1", port=port)
