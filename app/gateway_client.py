"""
OpenClaw Gateway WebSocket client.

Connects to the local OpenClaw gateway to send chat messages.
The gateway routes through to Anthropic using the configured OAuth token.

Protocol:
  1. Connect WebSocket
  2. Receive connect.challenge event
  3. Send connect request with auth
  4. Receive connect response (handshake OK)
  5. Send chat.send request
  6. Receive chat events (delta, final, error) as {type:"event", event:"chat", payload:{state, message}}
"""
import asyncio
import json
import logging
import os
import time
from uuid import uuid4
from typing import AsyncGenerator, Dict, Any, Tuple

import websockets

logger = logging.getLogger("eagle.gateway")

GATEWAY_URL = os.getenv("OPENCLAW_GATEWAY_URL", "ws://localhost:18789")
GATEWAY_TOKEN = os.getenv("OPENCLAW_GATEWAY_TOKEN", "f25cd1c6a865d62023226f4bb663bfcff0dd5ab28c155d82")


async def _gateway_handshake(ws) -> str:
    """Perform the gateway connect handshake. Returns connect request id."""
    # Step 1: Receive challenge event
    raw = await asyncio.wait_for(ws.recv(), timeout=10)
    challenge = json.loads(raw)
    logger.debug("Challenge: %s", challenge.get("event"))

    # Step 2: Handshake
    connect_id = str(uuid4())
    await ws.send(json.dumps({
        "type": "req",
        "id": connect_id,
        "method": "connect",
        "params": {
            "minProtocol": 3,
            "maxProtocol": 3,
            "client": {
                "id": "gateway-client",
                "version": "1.0.0",
                "platform": "linux",
                "mode": "backend",
            },
            "role": "operator",
            "scopes": ["operator.read", "operator.write"],
            "caps": [],
            "commands": [],
            "permissions": {},
            "auth": {"token": GATEWAY_TOKEN},
            "locale": "en-US",
            "userAgent": "eagle-agent/1.0.0",
        },
    }))

    # Wait for handshake response (skip other events)
    for _ in range(20):
        raw = await asyncio.wait_for(ws.recv(), timeout=10)
        frame = json.loads(raw)
        if frame.get("type") == "res" and frame.get("id") == connect_id:
            if not frame.get("ok"):
                raise RuntimeError(f"Handshake failed: {frame.get('error')}")
            logger.info("Gateway handshake OK")
            return connect_id

    raise RuntimeError("Handshake: no response after 20 frames")


async def chat_via_gateway(
    message: str,
    session_key: str = "agent:main:webchat:dm:eagle-demo",
    system_prompt: str = "",
    timeout_seconds: int = 120,
) -> Dict[str, Any]:
    """
    Send a message through the OpenClaw gateway and collect the full response.

    Returns dict with: text, tool_calls, usage, model, response_time_ms
    """
    start = time.time()
    try:
        async with websockets.connect(GATEWAY_URL, open_timeout=10) as ws:
            await _gateway_handshake(ws)

            full_message = message
            if system_prompt:
                full_message = f"<system>{system_prompt}</system>\n\n{message}"

            msg_id = str(uuid4())
            await ws.send(json.dumps({
                "type": "req",
                "id": msg_id,
                "method": "chat.send",
                "params": {
                    "message": full_message,
                    "sessionKey": session_key,
                    "idempotencyKey": str(uuid4()),
                },
            }))

            # Collect streaming response — deltas carry cumulative text,
            # so we track previous length to extract incremental chunks.
            full_text = ""
            tool_calls = []
            usage = {}
            model = ""

            deadline = time.time() + timeout_seconds

            while time.time() < deadline:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=60)
                except asyncio.TimeoutError:
                    logger.warning("Timeout waiting for gateway response")
                    break

                frame = json.loads(raw)
                frame_type = frame.get("type")
                event_name = frame.get("event", "")

                if frame_type == "res" and frame.get("id") == msg_id:
                    logger.debug("Chat started: runId=%s", frame.get("payload", {}).get("runId", ""))
                    continue

                if frame_type == "event" and event_name == "chat":
                    payload = frame.get("payload", {})
                    state = payload.get("state", "")

                    if state == "delta":
                        # Gateway sends cumulative text in each delta
                        delta_text = _extract_text(payload)
                        if delta_text:
                            full_text = delta_text  # replace, don't append
                        tool_calls.extend(_extract_tools(payload))

                    elif state == "final":
                        final_text = _extract_text(payload)
                        if final_text:
                            full_text = final_text
                        usage = payload.get("usage", {})
                        model = payload.get("model", "")
                        break

                    elif state in ("error", "aborted"):
                        error_msg = payload.get("errorMessage", "Unknown error")
                        logger.error("Chat error: %s", error_msg)
                        if not full_text:
                            full_text = f"Error: {error_msg}"
                        break

            elapsed_ms = int((time.time() - start) * 1000)
            return {
                "text": full_text,
                "tool_calls": tool_calls,
                "usage": usage,
                "model": model,
                "response_time_ms": elapsed_ms,
            }

    except Exception as e:
        logger.error("Gateway client error: %s", e)
        elapsed_ms = int((time.time() - start) * 1000)
        return {
            "text": f"Gateway error: {e}",
            "tool_calls": [],
            "usage": {},
            "model": "",
            "response_time_ms": elapsed_ms,
            "error": str(e),
        }


async def chat_via_gateway_stream(
    message: str,
    session_key: str = "agent:main:webchat:dm:eagle-demo",
    timeout_seconds: int = 120,
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Streaming version — yields events as they arrive:
      {"type": "delta", "text": "..."}
      {"type": "tool_use", "name": "...", "input": {...}}
      {"type": "final", "text": "...", "usage": {...}, "model": "...", "response_time_ms": int}
      {"type": "error", "message": "..."}
    """
    start = time.time()
    full_text = ""          # cumulative text so far
    prev_text_len = 0       # length already sent to caller
    try:
        async with websockets.connect(GATEWAY_URL, open_timeout=10) as ws:
            await _gateway_handshake(ws)

            msg_id = str(uuid4())
            await ws.send(json.dumps({
                "type": "req",
                "id": msg_id,
                "method": "chat.send",
                "params": {
                    "message": message,
                    "sessionKey": session_key,
                    "idempotencyKey": str(uuid4()),
                },
            }))

            deadline = time.time() + timeout_seconds

            while time.time() < deadline:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=60)
                except asyncio.TimeoutError:
                    yield {"type": "error", "message": "Timeout waiting for response"}
                    return

                frame = json.loads(raw)
                frame_type = frame.get("type")
                event_name = frame.get("event", "")

                # Ack for chat.send
                if frame_type == "res" and frame.get("id") == msg_id:
                    if not frame.get("ok", True):
                        yield {"type": "error", "message": frame.get("error", {}).get("message", "Request rejected")}
                        return
                    continue

                if frame_type == "event" and event_name == "chat":
                    payload = frame.get("payload", {})
                    state = payload.get("state", "")

                    if state == "delta":
                        # Gateway sends cumulative text — emit only the new portion
                        delta_text = _extract_text(payload)
                        if delta_text and len(delta_text) > prev_text_len:
                            new_chunk = delta_text[prev_text_len:]
                            full_text = delta_text
                            prev_text_len = len(delta_text)
                            yield {"type": "delta", "text": new_chunk}
                        for tc in _extract_tools(payload):
                            yield {"type": "tool_use", "name": tc["tool"], "input": tc["input"]}

                    elif state == "final":
                        final_text = _extract_text(payload)
                        if final_text:
                            full_text = final_text
                        elapsed_ms = int((time.time() - start) * 1000)
                        yield {
                            "type": "final",
                            "text": full_text,
                            "usage": payload.get("usage", {}),
                            "model": payload.get("model", ""),
                            "response_time_ms": elapsed_ms,
                        }
                        return

                    elif state in ("error", "aborted"):
                        error_msg = payload.get("errorMessage", "Unknown error")
                        yield {"type": "error", "message": error_msg}
                        return

    except Exception as e:
        logger.error("Gateway stream error: %s", e)
        yield {"type": "error", "message": str(e)}


# ── helpers ──────────────────────────────────────────────────────────

def _extract_text(payload: dict) -> str:
    """Pull text from a chat event payload."""
    msg_data = payload.get("message", {})
    content_blocks = msg_data.get("content", [])
    text = ""
    for block in content_blocks:
        if isinstance(block, dict) and block.get("type") == "text":
            text += block.get("text", "")
        elif isinstance(block, str):
            text += block
    return text


def _extract_tools(payload: dict) -> list:
    """Pull tool_use blocks from a chat event payload."""
    msg_data = payload.get("message", {})
    content_blocks = msg_data.get("content", [])
    tools = []
    for block in content_blocks:
        if isinstance(block, dict) and block.get("type") == "tool_use":
            tools.append({"tool": block.get("name", ""), "input": block.get("input", {})})
    return tools
