# Execution Plan: Local Chat Fixes

**Date**: 2025-02-25
**Branch**: main
**Source**: dev/greg-justfiles-update
**Status**: PENDING

---

## Overview

This plan details the changes required to enable local chat functionality on the `main` branch by porting critical fixes from `dev/greg-justfiles-update`. The root cause is that AWS credentials are not properly resolved and passed to the Claude SDK subprocess.

---

## File 1: `server/app/sdk_agentic_service.py`

### Problem
The Claude CLI subprocess cannot use boto3's SSO credential resolver because it's a Node.js process. Currently, main branch only passes `CLAUDE_CODE_USE_BEDROCK=1` and `AWS_REGION` without actual credentials.

### Solution
Add a `_get_bedrock_env()` function that resolves AWS credentials via boto3 and passes them as environment variables to the CLI subprocess.

### Changes

**Location**: After line 41 (after `logger = logging.getLogger("eagle.sdk_agent")`)

**Add this function**:

```python
def _get_bedrock_env() -> dict:
    """Resolve AWS credentials via boto3 (handles SSO, IAM roles, env vars) and
    return as a flat env dict for the Claude CLI subprocess.

    The bundled Claude Code CLI is Node.js and cannot use botocore's SSO resolver,
    so we bridge the gap: resolve here in Python and pass static creds to the CLI.
    """
    import boto3

    env: dict = {
        "CLAUDE_CODE_USE_BEDROCK": "1",
        "AWS_REGION": os.getenv("AWS_REGION", "us-east-1"),
        "HOME": os.getenv("HOME", "/home/appuser"),
    }
    try:
        creds = boto3.Session().get_credentials()
        if creds:
            frozen = creds.get_frozen_credentials()
            env["AWS_ACCESS_KEY_ID"] = frozen.access_key
            env["AWS_SECRET_ACCESS_KEY"] = frozen.secret_key
            if frozen.token:
                env["AWS_SESSION_TOKEN"] = frozen.token
    except Exception as e:
        logger.warning("Could not resolve AWS credentials for CLI subprocess: %s", e)
    return env
```

**Location**: Line 258-261 in `sdk_query()` function

**Replace**:
```python
        env={
            "CLAUDE_CODE_USE_BEDROCK": "1",
            "AWS_REGION": "us-east-1",
        },
```

**With**:
```python
        env=_get_bedrock_env(),
```

**Location**: Line 315-318 in `sdk_query_single_skill()` function

**Replace**:
```python
        env={
            "CLAUDE_CODE_USE_BEDROCK": "1",
            "AWS_REGION": "us-east-1",
        },
```

**With**:
```python
        env=_get_bedrock_env(),
```

### Validation
```bash
cd server && python -c "from app.sdk_agentic_service import _get_bedrock_env; print(_get_bedrock_env())"
```

---

## File 2: `deployment/docker-compose.dev.yml`

### Problem
AWS credentials are mounted to `/root/.aws:ro` but the container runs as `appuser`, not `root`. The read-only mount also prevents credential caching.

### Solution
Mount to the correct user path `/home/appuser/.aws` and set a default AWS_PROFILE.

### Changes

**Location**: Lines 14-26

**Replace**:
```yaml
      - AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID:-}
      - AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY:-}
      - AWS_SESSION_TOKEN=${AWS_SESSION_TOKEN:-}
      # AWS SSO support: if AWS_PROFILE is set, use credential process
      - AWS_PROFILE=${AWS_PROFILE:-}
      - AWS_SDK_LOAD_CONFIG=1
    volumes:
      - ../server/app:/app/app
      # Mount AWS credentials directory for SSO (read-only)
      # On Windows Git Bash: ${HOME}/.aws works
      # On Windows CMD/PowerShell: use %USERPROFILE%\.aws
      # Alternative: set AWS_CONFIG_DIR env var before running docker compose
      - ${AWS_CONFIG_DIR:-${HOME}/.aws}:/root/.aws:ro
```

**With**:
```yaml
      - AWS_PROFILE=${AWS_PROFILE:-eagle}
      - AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID:-}
      - AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY:-}
      - AWS_SESSION_TOKEN=${AWS_SESSION_TOKEN:-}
    volumes:
      - ../server/app:/app/app
      - ${HOME}/.aws:/home/appuser/.aws
```

### Validation
```bash
docker compose -f deployment/docker-compose.dev.yml config | grep -A5 "volumes:"
```

---

## File 3: `server/app/main.py`

### Problem
1. SDK response text extraction misses the `result` field from `ResultMessage`
2. S3 bucket defaults to empty string instead of the actual bucket name
3. `session_id` is passed to `sdk_query()` but it doesn't accept that parameter

### Solution
Add fallback text extraction from `ResultMessage.result` and set proper S3 bucket default.

### Changes

#### Change 3a: REST chat endpoint response extraction (around line 175-198)

**Replace**:
```python
        _text_parts: list[str] = []
        _usage: dict = {}
        _tools_called: list[str] = []
        async for _sdk_msg in sdk_query(
            prompt=req.message,
            tenant_id=tenant_id,
            user_id=user_id,
            tier=user.tier or "advanced",
            session_id=session_id,
        ):
            _msg_type = type(_sdk_msg).__name__
            if _msg_type == "AssistantMessage":
                for _block in _sdk_msg.content:
                    if getattr(_block, "type", None) == "text":
                        _text_parts.append(_block.text)
                    elif getattr(_block, "type", None) == "tool_use":
                        _tools_called.append(getattr(_block, "name", ""))
            elif _msg_type == "ResultMessage":
                _raw = getattr(_sdk_msg, "usage", {})
                _usage = _raw if isinstance(_raw, dict) else {
                    "input_tokens": getattr(_raw, "input_tokens", 0),
                    "output_tokens": getattr(_raw, "output_tokens", 0),
                }
        result = {"text": "".join(_text_parts), "usage": _usage, "model": MODEL, "tools_called": _tools_called}
```

**With**:
```python
        _text_parts: list[str] = []
        _usage: dict = {}
        _tools_called: list[str] = []
        _final_text: str = ""
        async for _sdk_msg in sdk_query(
            prompt=req.message,
            tenant_id=tenant_id,
            user_id=user_id,
            tier=user.tier or "advanced",
        ):
            _msg_type = type(_sdk_msg).__name__
            if _msg_type == "AssistantMessage":
                for _block in _sdk_msg.content:
                    if getattr(_block, "type", None) == "text":
                        _text_parts.append(_block.text)
                    elif getattr(_block, "type", None) == "tool_use":
                        _tools_called.append(getattr(_block, "name", ""))
            elif _msg_type == "ResultMessage":
                _raw = getattr(_sdk_msg, "usage", {})
                _usage = _raw if isinstance(_raw, dict) else {
                    "input_tokens": getattr(_raw, "input_tokens", 0),
                    "output_tokens": getattr(_raw, "output_tokens", 0),
                }
                _final_text = str(getattr(_sdk_msg, "result", "") or "")
        _response_text = "".join(_text_parts) or _final_text
        result = {"text": _response_text, "usage": _usage, "model": MODEL, "tools_called": _tools_called}
```

#### Change 3b: S3 bucket default (line 470)

**Replace**:
```python
    bucket = os.getenv("S3_BUCKET", "")
```

**With**:
```python
    bucket = os.getenv("S3_BUCKET", "nci-documents")
```

#### Change 3c: S3 bucket default for get_document (line 505)

**Replace**:
```python
    bucket = os.getenv("S3_BUCKET", "")
```

**With**:
```python
    bucket = os.getenv("S3_BUCKET", "nci-documents")
```

#### Change 3d: WebSocket chat response extraction (around line 757-782)

**Replace**:
```python
                _text_parts: list[str] = []
                _usage: dict = {}
                async for _sdk_msg in sdk_query(
                    prompt=user_message,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    tier=user.tier or "advanced",
                    session_id=session_id,
                ):
                    _msg_type = type(_sdk_msg).__name__
                    if _msg_type == "AssistantMessage":
                        for _block in _sdk_msg.content:
                            _bt = getattr(_block, "type", None)
                            if _bt == "text":
                                _text_parts.append(_block.text)
                                await on_text(_block.text)
                            elif _bt == "tool_use":
                                tools_called.append(getattr(_block, "name", ""))
                                await on_tool_use(getattr(_block, "name", ""), getattr(_block, "input", {}))
                    elif _msg_type == "ResultMessage":
                        _raw = getattr(_sdk_msg, "usage", {})
                        _usage = _raw if isinstance(_raw, dict) else {
                            "input_tokens": getattr(_raw, "input_tokens", 0),
                            "output_tokens": getattr(_raw, "output_tokens", 0),
                        }
                result = {"text": "".join(_text_parts), "usage": _usage, "model": MODEL, "tools_called": tools_called}
```

**With**:
```python
                _text_parts: list[str] = []
                _usage: dict = {}
                _final_text: str = ""
                async for _sdk_msg in sdk_query(
                    prompt=user_message,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    tier=user.tier or "advanced",
                ):
                    _msg_type = type(_sdk_msg).__name__
                    if _msg_type == "AssistantMessage":
                        for _block in _sdk_msg.content:
                            _bt = getattr(_block, "type", None)
                            if _bt == "text":
                                _text_parts.append(_block.text)
                                await on_text(_block.text)
                            elif _bt == "tool_use":
                                tools_called.append(getattr(_block, "name", ""))
                                await on_tool_use(getattr(_block, "name", ""), getattr(_block, "input", {}))
                    elif _msg_type == "ResultMessage":
                        _raw = getattr(_sdk_msg, "usage", {})
                        _usage = _raw if isinstance(_raw, dict) else {
                            "input_tokens": getattr(_raw, "input_tokens", 0),
                            "output_tokens": getattr(_raw, "output_tokens", 0),
                        }
                        _final_text = str(getattr(_sdk_msg, "result", "") or "")
                _response_text = "".join(_text_parts) or _final_text
                if _response_text and not _text_parts:
                    await on_text(_response_text)
                result = {"text": _response_text, "usage": _usage, "model": MODEL, "tools_called": tools_called}
```

### Validation
```bash
cd server && python -c "from app.main import app; print('main.py imports successfully')"
```

---

## File 4: `client/app/api/invoke/route.ts`

### Problem
The route tries SSE streaming endpoint `/api/chat/stream` first, then falls back to REST. This adds complexity and the streaming endpoint may fail.

### Solution
Simplify to use REST endpoint `/api/chat` directly and add slash command normalization.

### Changes

**Full file replacement** - see the complete new version below:

```typescript
/**
 * FastAPI Chat API Route
 *
 * Proxies requests to the FastAPI backend and emits SSE-formatted
 * events back to the frontend for compatibility.
 *
 * Backend: FastAPI POST /api/chat (JSON)
 */

import { NextRequest, NextResponse } from 'next/server';

const FASTAPI_URL = process.env.FASTAPI_URL || 'http://localhost:8000';

function normalizeSlashCommand(input: string): string {
  const message = input.trim();
  if (!message.startsWith('/')) return message;

  const [rawCommand, ...restParts] = message.split(/\s+/);
  const command = rawCommand.toLowerCase();
  const rest = restParts.join(' ').trim();

  switch (command) {
    case '/document':
      return rest
        ? `Create the requested acquisition document(s): ${rest}`
        : 'Create the requested acquisition document(s).';
    case '/research':
      return rest
        ? `Research this acquisition/regulatory question and provide guidance: ${rest}`
        : 'Research acquisition/regulatory guidance for me.';
    case '/status':
      return 'Show the current acquisition package status, completed artifacts, and next steps.';
    case '/help':
      return 'List your capabilities and the best commands/prompts to generate acquisition artifacts.';
    case '/acquisition-package':
      return rest
        ? `Start a new acquisition package using this information: ${rest}`
        : 'Start a new acquisition package and ask me for the minimum required intake details.';
    default:
      // Unknown slash command: remove the leading command token and keep user intent text.
      return rest || message.replace(/^\//, '');
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    if (!body.prompt && !body.query) {
      return NextResponse.json(
        { error: 'Missing required field: prompt or query' },
        { status: 400 }
      );
    }

    const sessionId = body.session_id || crypto.randomUUID();
    const rawMessage = body.prompt || body.query;
    const message = normalizeSlashCommand(rawMessage);

    // Forward Authorization header from client
    const authHeader = request.headers.get('authorization');

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (authHeader) {
      headers['Authorization'] = authHeader;
    }

    // Transform to FastAPI chat request format
    const fastApiBody = {
      message,
      session_id: sessionId,
    };

    const response = await fetch(`${FASTAPI_URL}/api/chat`, {
      method: 'POST',
      headers,
      body: JSON.stringify(fastApiBody),
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error(`FastAPI error: ${response.status} - ${errorText}`);
      return NextResponse.json(
        { error: `Backend error: ${response.status}` },
        { status: response.status }
      );
    }

    // Convert REST response to SSE format for consistent frontend handling
    const data = await response.json();
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        const event = {
          type: 'text',
          agent_id: 'eagle-assistant',
          agent_name: 'EAGLE Assistant',
          content: data.response,
          timestamp: new Date().toISOString(),
        };
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(event)}\n\n`));

        const complete = {
          type: 'complete',
          agent_id: 'eagle-assistant',
          agent_name: 'EAGLE Assistant',
          metadata: {
            session_id: data.session_id,
            usage: data.usage,
            model: data.model,
            tools_called: data.tools_called,
            cost_usd: data.cost_usd,
          },
          timestamp: new Date().toISOString(),
        };
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(complete)}\n\n`));
        controller.close();
      },
    });

    return new Response(stream, {
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
      },
    });
  } catch (error) {
    console.error('API route error:', error);

    if (error instanceof TypeError && error.message.includes('fetch')) {
      return NextResponse.json(
        {
          error: 'Cannot connect to backend',
          details: `Ensure FastAPI is running at ${FASTAPI_URL}`,
        },
        { status: 503 }
      );
    }

    return NextResponse.json(
      { error: 'Internal server error', details: String(error) },
      { status: 500 }
    );
  }
}

/**
 * Health check - pings FastAPI backend
 */
export async function GET() {
  try {
    const response = await fetch(`${FASTAPI_URL}/api/tools`, {
      method: 'GET',
      signal: AbortSignal.timeout(5000),
    });

    if (response.ok) {
      return NextResponse.json({
        status: 'healthy',
        backend: FASTAPI_URL,
        timestamp: new Date().toISOString(),
      });
    }

    return NextResponse.json(
      {
        status: 'unhealthy',
        backend: FASTAPI_URL,
        error: `Backend returned ${response.status}`,
      },
      { status: 503 }
    );
  } catch {
    return NextResponse.json(
      {
        status: 'unhealthy',
        backend: FASTAPI_URL,
        error: 'Cannot connect to backend',
      },
      { status: 503 }
    );
  }
}
```

### Validation
```bash
cd client && npx tsc --noEmit
```

---

## File 5: `server/app/streaming_routes.py`

### Problem
1. `stream_generator` uses `tenant_context` object but should use extracted `tenant_id` and `user_id` strings
2. Missing cancellation handling for client disconnects
3. SDK async generator not properly closed

### Solution
Fix parameter handling and add proper cleanup.

### Changes

#### Change 5a: Add import (line 17)

**After**:
```python
import logging
```

**Add**:
```python
from contextlib import suppress
```

#### Change 5b: Update function signature (lines 35-40)

**Replace**:
```python
async def stream_generator(
    message: str,
    tenant_context,
    tier,
    subscription_service: SubscriptionService,
) -> AsyncGenerator[str, None]:
```

**With**:
```python
async def stream_generator(
    message: str,
    tenant_id: str,
    user_id: str,
    tier,
    subscription_service: SubscriptionService,
) -> AsyncGenerator[str, None]:
```

#### Change 5c: Update SDK query call (lines 58-67)

**Replace**:
```python
    try:
        tenant_id = getattr(tenant_context, "tenant_id", "demo-tenant")
        user_id = getattr(tenant_context, "user_id", "demo-user")

        async for sdk_msg in sdk_query(
            prompt=message,
            tenant_id=tenant_id,
            user_id=user_id,
            tier=tier or "advanced",
        ):
```

**With**:
```python
    try:
        sdk_messages = sdk_query(
            prompt=message,
            tenant_id=tenant_id,
            user_id=user_id,
            tier=tier or "advanced",
        )

        async for sdk_msg in sdk_messages:
```

#### Change 5d: Add exception handling (after line 89)

**After the existing exception handler**:
```python
    except Exception as e:
        logger.error("Streaming chat error: %s", str(e), exc_info=True)
        await writer.write_error(queue, str(e))
        yield await queue.get()
```

**Replace with**:
```python
    except asyncio.CancelledError:
        # Client disconnected mid-stream; treat as expected cancellation path.
        logger.info("Streaming client disconnected")
        return
    except Exception as e:
        logger.error("Streaming chat error: %s", str(e), exc_info=True)
        await writer.write_error(queue, str(e))
        yield await queue.get()
    finally:
        # Ensure SDK async generator is closed from this task.
        if "sdk_messages" in locals():
            with suppress(Exception):
                await sdk_messages.aclose()
```

#### Change 5e: Update router call (lines 148-154)

**Replace**:
```python
        return StreamingResponse(
            stream_generator(
                message=message.message,
                tenant_context=message.tenant_context,
                tier=user.tier,
                subscription_service=subscription_service,
            ),
```

**With**:
```python
        return StreamingResponse(
            stream_generator(
                message=message.message,
                tenant_id=tenant_id,
                user_id=user_id,
                tier=user.tier,
                subscription_service=subscription_service,
            ),
```

### Validation
```bash
cd server && python -c "from app.streaming_routes import create_streaming_router; print('streaming_routes.py imports successfully')"
```

---

## Execution Order

1. `server/app/sdk_agentic_service.py` - Add credential bridging (foundational)
2. `deployment/docker-compose.dev.yml` - Fix AWS mount path
3. `server/app/main.py` - Fix response extraction + S3 defaults
4. `server/app/streaming_routes.py` - Fix parameter handling
5. `client/app/api/invoke/route.ts` - Simplify to REST endpoint

---

## Full Validation Sequence

```bash
# 1. Python lint
cd ~/Desktop/sm_eagle/server && python -m ruff check app/

# 2. TypeScript lint
cd ~/Desktop/sm_eagle/client && npx tsc --noEmit

# 3. Import test
cd ~/Desktop/sm_eagle/server && python -c "
from app.sdk_agentic_service import _get_bedrock_env, sdk_query
from app.main import app
from app.streaming_routes import create_streaming_router
print('All imports successful')
"

# 4. Docker compose validation
cd ~/Desktop/sm_eagle && docker compose -f deployment/docker-compose.dev.yml config

# 5. Start local stack
cd ~/Desktop/sm_eagle && just dev
```

---

## Rollback

If issues occur, revert to main branch state:
```bash
git checkout main -- server/app/sdk_agentic_service.py
git checkout main -- deployment/docker-compose.dev.yml
git checkout main -- server/app/main.py
git checkout main -- server/app/streaming_routes.py
git checkout main -- client/app/api/invoke/route.ts
```

---

## File 6: `deployment/docker/Dockerfile.backend` (CRITICAL)

### Problem
The container runs as root, but Claude CLI refuses to run with `--dangerously-skip-permissions` as root for security reasons.

### Solution
Create a non-root user `appuser` and run the container as that user.

### Changes

**Replace the entire file with**:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install curl for ECS health checks
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY server/app/ app/
COPY server/run.py .
COPY server/config.py .
COPY server/eagle_skill_constants.py .
COPY eagle-plugin/ ../eagle-plugin/

# Claude Code CLI blocks --dangerously-skip-permissions when running as root
RUN useradd -m -u 1000 appuser \
    && chown -R appuser:appuser /app /eagle-plugin

ENV HOME=/home/appuser
USER appuser

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Validation
```bash
docker compose -f deployment/docker-compose.dev.yml config
docker compose -f deployment/docker-compose.dev.yml up --build
```

---

## Related Files (Optional)

These files have minor improvements in the dev branch but are not critical for local chat:

- `Justfile` - Python path variable, simplified SSO commands
- `.env.example` - Environment variable updates

