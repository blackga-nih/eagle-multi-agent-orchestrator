"""
AgentCore Memory Service — wraps MemoryClient + MemorySessionManager
for persistent workspace memory scoped per tenant+user.

Provides operations: view, write, append, search, list_sessions.
Falls back to in-memory dict when AgentCore is unavailable.
"""

import json
import logging
import os
from typing import Any

logger = logging.getLogger("eagle.agentcore_memory")

_REGION = os.getenv("AWS_REGION", "us-east-1")
_MEMORY_ID = os.getenv("AGENTCORE_MEMORY_ID", "")

# Lazy singleton
_manager = None
_fallback_store: dict[str, dict[str, str]] = {}  # tenant#user -> {filename: content}


def _get_manager():
    """Lazy-init MemorySessionManager singleton."""
    global _manager
    if _manager is not None:
        return _manager

    if not _MEMORY_ID:
        logger.warning("AGENTCORE_MEMORY_ID not set — using in-memory fallback")
        return None

    try:
        from bedrock_agentcore.memory import MemorySessionManager
        _manager = MemorySessionManager(memory_id=_MEMORY_ID, region_name=_REGION)
        logger.info("AgentCore MemorySessionManager initialized (memory_id=%s)", _MEMORY_ID)
        return _manager
    except Exception as exc:
        logger.warning("AgentCore Memory unavailable: %s — using in-memory fallback", exc)
        return None


def _store_key(tenant_id: str, user_id: str) -> str:
    return f"{tenant_id}#{user_id}"


def workspace_memory(
    command: str,
    path: str,
    tenant_id: str,
    user_id: str,
    content: str = "",
    session_id: str | None = None,
) -> dict[str, Any]:
    """Execute a workspace memory operation.

    Args:
        command: view | write | append | clear | list
        path: File path (e.g. _workspace.txt)
        tenant_id: Tenant for scoping
        user_id: User for scoping
        content: Content for write/append
        session_id: Optional session ID for AgentCore events
    """
    manager = _get_manager()

    if manager:
        return _agentcore_op(manager, command, path, tenant_id, user_id, content, session_id)
    return _fallback_op(command, path, tenant_id, user_id, content)


def _agentcore_op(
    manager,
    command: str,
    path: str,
    tenant_id: str,
    user_id: str,
    content: str,
    session_id: str | None,
) -> dict:
    """AgentCore-backed workspace operations using events as storage."""
    from bedrock_agentcore.memory.constants import MessageRole
    from bedrock_agentcore.memory.session import ConversationalMessage

    actor_id = f"{tenant_id}:{user_id}"
    sid = session_id or f"workspace-{actor_id}"
    namespace = f"workspace/{tenant_id}/{user_id}"

    if command == "view":
        try:
            events = manager.list_events(
                actor_id=actor_id,
                session_id=sid,
            )
            # Find latest event with this path in metadata
            for event in reversed(events if isinstance(events, list) else []):
                meta = getattr(event, "metadata", {}) or {}
                if meta.get("path") == path:
                    messages = getattr(event, "messages", [])
                    if messages:
                        last = messages[-1]
                        text = getattr(last, "content", "") if hasattr(last, "content") else str(last)
                        return {"command": "view", "path": path, "content": text}
            return {"command": "view", "path": path, "content": "(empty)"}
        except Exception as exc:
            logger.warning("AgentCore view failed: %s — fallback", exc)
            return _fallback_op("view", path, tenant_id, user_id, "")

    elif command in ("write", "append"):
        try:
            if command == "append":
                existing = _agentcore_op(manager, "view", path, tenant_id, user_id, "", session_id)
                old = existing.get("content", "")
                if old == "(empty)":
                    old = ""
                content = old + "\n" + content if old else content

            manager.add_turns(
                actor_id=actor_id,
                session_id=sid,
                messages=[
                    ConversationalMessage(content, MessageRole.ASSISTANT),
                ],
                metadata={"path": path, "tenant_id": tenant_id, "user_id": user_id},
            )
            return {
                "command": command,
                "path": path,
                "message": f"{'Wrote' if command == 'write' else 'Appended'} to {path}",
                "size": len(content),
            }
        except Exception as exc:
            logger.warning("AgentCore %s failed: %s — fallback", command, exc)
            return _fallback_op(command, path, tenant_id, user_id, content)

    elif command == "clear":
        try:
            manager.add_turns(
                actor_id=actor_id,
                session_id=sid,
                messages=[
                    ConversationalMessage("", MessageRole.ASSISTANT),
                ],
                metadata={"path": path, "tenant_id": tenant_id, "user_id": user_id, "cleared": "true"},
            )
            return {"command": "clear", "path": path, "message": f"Cleared {path}"}
        except Exception as exc:
            logger.warning("AgentCore clear failed: %s — fallback", exc)
            return _fallback_op("clear", path, tenant_id, user_id, "")

    elif command == "list":
        try:
            sessions = manager.list_sessions(actor_id=actor_id)
            files = set()
            for session in (sessions if isinstance(sessions, list) else []):
                events = manager.list_events(actor_id=actor_id, session_id=getattr(session, "session_id", str(session)))
                for event in (events if isinstance(events, list) else []):
                    meta = getattr(event, "metadata", {}) or {}
                    p = meta.get("path")
                    if p:
                        files.add(p)
            return {"command": "list", "files": sorted(files), "count": len(files)}
        except Exception as exc:
            logger.warning("AgentCore list failed: %s — fallback", exc)
            return _fallback_op("list", path, tenant_id, user_id, "")

    elif command == "search":
        try:
            records = manager.retrieve_memory_records(
                query=content or path,
                namespace=namespace,
            )
            results = []
            for r in (records if isinstance(records, list) else []):
                results.append({
                    "content": getattr(r, "content", str(r)),
                    "score": getattr(r, "score", 0),
                })
            return {"command": "search", "query": content or path, "results": results, "count": len(results)}
        except Exception as exc:
            logger.warning("AgentCore search failed: %s — fallback", exc)
            return {"command": "search", "query": content or path, "results": [], "count": 0}

    return {"error": f"Unknown command: {command}", "valid_commands": ["view", "write", "append", "clear", "list", "search"]}


def _fallback_op(command: str, path: str, tenant_id: str, user_id: str, content: str) -> dict:
    """In-memory fallback when AgentCore is unavailable."""
    key = _store_key(tenant_id, user_id)
    store = _fallback_store.setdefault(key, {})

    if command == "view":
        return {"command": "view", "path": path, "content": store.get(path, "(empty)")}

    elif command == "write":
        store[path] = content
        return {"command": "write", "path": path, "message": f"Wrote to {path}", "size": len(content)}

    elif command == "append":
        existing = store.get(path, "")
        store[path] = (existing + "\n" + content) if existing else content
        return {"command": "append", "path": path, "message": f"Appended to {path}", "size": len(store[path])}

    elif command == "clear":
        store.pop(path, None)
        return {"command": "clear", "path": path, "message": f"Cleared {path}"}

    elif command == "list":
        files = sorted(store.keys())
        return {"command": "list", "files": files, "count": len(files)}

    return {"error": f"Unknown command: {command}"}
