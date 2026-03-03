# Codebase Cleanup Plan

## Context

`server/app/main.py` was created by merging two codebases: the original multi-tenant
architecture and the newer EAGLE option1-simple. The result is a 1,098-line file with
two clearly-labeled sections: "EAGLE ENDPOINTS (new)" and "PRESERVED MULTI-TENANT
ENDPOINTS (from original main.py)". The bottom half uses a legacy auth system
(`auth.py`). A frontend audit confirms these preserved endpoints are dead — the
frontend never calls `/api/tenants/*`, `/api/mcp/weather/*`, or the granular
admin-tenant cost routes.

**What's already done**: The orchestration migration from `stream_chat()` to
`sdk_query()` was completed and committed in `e358c83`. Both `main.py` and
`streaming_routes.py` already use `sdk_query` exclusively. `agentic_service.py` is
intentionally preserved as a tool library — `execute_tool()` is used by eval tests
16–20, and `EAGLE_TOOLS`/`MODEL` are still exported from it. Do not archive it.

There is a duplicate `GET /api/health` registered in both `main.py` and
`streaming_routes.py`.

**Net impact**: ~450 lines removed from `main.py`, 4 files archived to `server/legacy/`.

---

## Step 1 — Clean up `main.py` imports

**File**: `server/app/main.py`

`agentic_service.py` is intentionally preserved — keep imports of `MODEL` and
`EAGLE_TOOLS` from it. Only remove what is genuinely unused:

Remove unused standard-library / FastAPI imports:
- `Response` from fastapi (never used in any route handler)
- `JSONResponse` from fastapi.responses (never used — `StreamingResponse` is used)
- `Decimal` (never used)
- `asyncio` (never used)
- `get_client` from `.agentic_service` (imported but never invoked)

Remove legacy-only imports (only used by the dead route section being removed in Step 2):
- `from .auth import get_current_user`
- `from .models import TenantContext, UsageMetric, SubscriptionTier`
- `from .admin_cost_service import AdminCostService`
- `from .admin_auth import verify_tenant_admin` (keep `get_admin_user` — used by cost-report)

Remove unused service instantiations:
- `admin_cost_service = AdminCostService()` — only used by removed granular tenant routes

Simplify streaming router call (subscription_service is passed but never used inside):
- `streaming_router = create_streaming_router()` (no args — see Step 3)

---

## Step 2 — Remove dead route section from `main.py`

**File**: `server/app/main.py`

Delete the entire `# PRESERVED MULTI-TENANT ENDPOINTS` section (lines ~843–1068):

| Endpoints removed | Reason |
|---|---|
| `GET /api/tenants/{tenant_id}/usage` | Dead — no frontend call |
| `GET /api/tenants/{tenant_id}/costs` | Dead — no frontend call |
| `GET /api/tenants/{tenant_id}/users/{user_id}/costs` | Dead — no frontend call |
| `GET /api/tenants/{tenant_id}/subscription` | Dead — no frontend call |
| `GET /api/tenants/{tenant_id}/sessions` | Dead — no frontend call |
| `GET /api/tenants/{tenant_id}/analytics` | Dead — no frontend call |
| `GET /api/mcp/weather/tools` | Dead — no frontend call |
| `POST /api/mcp/weather/{tool_name}` | Dead — no frontend call |
| `GET /api/admin/tier-costs/{tier}` | Dead — no frontend call |
| `GET /api/admin/tenants/{tenant_id}/overall-cost` | Dead — no frontend call |
| `GET /api/admin/tenants/{tenant_id}/per-user-cost` | Dead — no frontend call |
| `GET /api/admin/tenants/{tenant_id}/service-wise-cost` | Dead — no frontend call |
| `GET /api/admin/tenants/{tenant_id}/users/{user_id}/service-cost` | Dead — no frontend call |
| `GET /api/admin/tenants/{tenant_id}/comprehensive-report` | Dead — no frontend call |

**Keep** (used by frontend or are admin utilities):
- `GET /api/admin/cost-report` — frontend proxy `GET /api/admin/costs` calls this
- `GET /api/admin/my-tenants` — admin utility
- `POST /api/admin/add-to-group` — admin utility

Also remove duplicate health check: `main.py` line ~1083 `GET /api/health` duplicates
one defined in `streaming_routes.py`. Remove the one in `streaming_routes.py` (Step 3).

---

## Step 3 — Clean up `streaming_routes.py`

**File**: `server/app/streaming_routes.py`

1. Remove `GET /api/health` endpoint from this router (lines ~163–208).
   It duplicates the one in `main.py`. The authoritative health check belongs in
   `main.py`. Once removed, the `EAGLE_TOOLS` and `MODEL` imports are no longer used
   here either — drop them.

2. Simplify `create_streaming_router` signature — remove the `subscription_service`
   parameter (it's accepted but never used in `stream_generator`):
   ```python
   # Before
   def create_streaming_router(subscription_service: SubscriptionService) -> APIRouter:
   # After
   def create_streaming_router() -> APIRouter:
   ```
   Also remove the `SubscriptionService` import (no longer needed here).

---

## Step 4 — Archive dead files to `server/legacy/`

Create `server/legacy/` directory with a `README.md` noting these are archived.

Move (git mv, not copy):
| Source | Destination | Notes |
|---|---|---|
| `server/app/auth.py` | `server/legacy/auth.py` | Legacy JWT auth, superseded by `cognito_auth.py`; only used by removed routes |
| `server/app/weather_mcp_service.py` | `server/legacy/weather_mcp_service.py` | No frontend usage; removed endpoints |
| `server/app/mcp_agent_integration.py` | `server/legacy/mcp_agent_integration.py` | Broken import of non-existent `AgenticService`; never instantiated |
| `server/app/gateway_client.py` | `server/legacy/gateway_client.py` | Not imported anywhere in active code |

**Do NOT archive**: `server/app/agentic_service.py` — intentionally preserved:
- `execute_tool()` is called by eval tests 16–20
- `EAGLE_TOOLS` and `MODEL` still imported by `main.py` and `streaming_routes.py`
- Per spec `20260222-223657-plan-backend-sdk-wiring-v1.md`: "Do not delete agentic_service.py"

---

## Step 5 — Clean up `main.py` header comment (optional)

Update the module docstring from its current "merging..." description to reflect
the clean architecture. (2-line change)

---

## Verification

```bash
# Level 1 — Lint (must pass)
cd server && ruff check app/

# Level 2 — Import smoke test (catches broken imports)
python -c "from app.main import app; print('OK')"

# Level 2 — Unit tests
python -m pytest tests/ -v

# Manual spot checks
curl http://localhost:8000/api/health
curl http://localhost:8000/api/tools
```

---

## Summary

| Metric | Before | After |
|---|---|---|
| `main.py` lines | 1,098 | ~650 |
| `streaming_routes.py` lines | 210 | ~145 |
| Files archived to `server/legacy/` | 0 | 4 |
| Dead route lines removed | 0 | ~450 |
| Route count (active) | ~35 | ~22 |
| Auth systems | 2 | 1 (cognito_auth only) |
| `agentic_service.py` status | active imports | preserved tool library (intentional) |
