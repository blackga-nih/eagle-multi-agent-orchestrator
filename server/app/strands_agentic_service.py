"""Strands-only orchestration service for EAGLE.

Provides normalized event streaming for SSE/REST/WebSocket consumers.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, AsyncGenerator

import boto3

from .admin_service import calculate_cost
from .strands_tools import build_specialist_tools, to_public_tool_docs
from eagle_skill_constants import AGENTS

logger = logging.getLogger("eagle.strands_agent")

try:
    from strands import Agent
    from strands.models import BedrockModel
except Exception:  # pragma: no cover - handled at runtime if strands is absent
    Agent = None
    BedrockModel = None

MODEL_ALIASES = {
    "haiku": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    "sonnet": "us.anthropic.claude-sonnet-4-20250514-v1:0",
}

MODEL = os.getenv("EAGLE_MODEL", os.getenv("EAGLE_SDK_MODEL", "haiku"))
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

TIER_BUDGETS = {
    "basic": 0.10,
    "advanced": 0.25,
    "premium": 0.75,
}


class StrandsLimitReached(RuntimeError):
    pass


def _ensure_strands() -> None:
    if Agent is None or BedrockModel is None:
        raise RuntimeError(
            "strands package is not installed. Add 'strands-agents' to requirements and install dependencies."
        )


def resolve_model_id(model_name: str | None = None) -> str:
    raw = (model_name or MODEL or "haiku").strip()
    return MODEL_ALIASES.get(raw, raw)


def get_active_model() -> str:
    return resolve_model_id(MODEL)


def get_bedrock_model(model_name: str | None = None, region: str | None = None) -> Any:
    _ensure_strands()
    model_id = resolve_model_id(model_name)
    boto_session = boto3.Session(region_name=region or AWS_REGION)
    return BedrockModel(model_id=model_id, boto_session=boto_session)


def build_supervisor_prompt(
    *, tenant_id: str, user_id: str, tier: str, available_tools: list[dict[str, Any]]
) -> str:
    supervisor_entry = AGENTS.get("supervisor")
    if supervisor_entry:
        base_prompt = supervisor_entry.get("body", "").strip()
    else:
        base_prompt = "You are the EAGLE Supervisor Agent for NCI Office of Acquisitions."

    tool_lines = "\n".join(
        f"- {tool['name']}: {tool.get('description', '').strip()}" for tool in available_tools
    )

    return (
        f"Tenant: {tenant_id} | User: {user_id} | Tier: {tier}\n\n"
        f"{base_prompt}\n\n"
        f"--- ACTIVE SPECIALISTS ---\n"
        f"Available specialist tools for delegation:\n{tool_lines}\n\n"
        "IMPORTANT: Delegate specialist tasks to the appropriate specialist tool. "
        "When delegating, include precise context and user constraints."
    )


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _extract_usage_from_obj(obj: Any) -> dict[str, int]:
    """Best-effort usage extraction from event/result/agent objects."""
    if obj is None:
        return {"input_tokens": 0, "output_tokens": 0}

    # Dict-like usage payloads
    if isinstance(obj, dict):
        usage_block = obj.get("usage") if isinstance(obj.get("usage"), dict) else obj
        return {
            "input_tokens": _to_int(
                usage_block.get("input_tokens")
                or usage_block.get("inputTokens")
                or usage_block.get("inputTokenCount")
            ),
            "output_tokens": _to_int(
                usage_block.get("output_tokens")
                or usage_block.get("outputTokens")
                or usage_block.get("outputTokenCount")
            ),
        }

    # Object-like usage fields
    usage = getattr(obj, "usage", None)
    if usage is not None:
        return _extract_usage_from_obj(usage)

    token_usage = getattr(obj, "token_usage", None)
    if token_usage is not None:
        return _extract_usage_from_obj(token_usage)

    return {
        "input_tokens": _to_int(getattr(obj, "input_tokens", 0) or getattr(obj, "inputTokens", 0)),
        "output_tokens": _to_int(getattr(obj, "output_tokens", 0) or getattr(obj, "outputTokens", 0)),
    }


def _merge_usage(primary: dict[str, int], secondary: dict[str, int]) -> dict[str, int]:
    return {
        "input_tokens": max(_to_int(primary.get("input_tokens")), _to_int(secondary.get("input_tokens"))),
        "output_tokens": max(_to_int(primary.get("output_tokens")), _to_int(secondary.get("output_tokens"))),
    }


def _extract_agent_usage(agent: Any) -> dict[str, int]:
    return _extract_usage_from_obj(getattr(agent, "token_usage", None))


def _extract_result_text(result_obj: Any) -> str:
    if result_obj is None:
        return ""
    if isinstance(result_obj, dict):
        for key in ("text", "result", "output", "message"):
            val = result_obj.get(key)
            if isinstance(val, str) and val.strip():
                return val
        return str(result_obj)
    if isinstance(result_obj, str):
        return result_obj
    for attr in ("text", "result", "output", "message"):
        val = getattr(result_obj, attr, None)
        if isinstance(val, str) and val.strip():
            return val
    return str(result_obj)


def normalize_stream_event(event: Any) -> dict[str, Any] | None:
    """Normalize Strands stream_async events into internal contract.

    Returns event dict with type in {text, tool_use, complete, error}.
    """
    if not isinstance(event, dict):
        return None
    if isinstance(event.get("event"), dict):
        event = event["event"]

    if event.get("error"):
        return {"type": "error", "message": str(event.get("error"))}

    if "data" in event and event.get("data") is not None:
        data = event.get("data")
        if isinstance(data, str):
            text = data
        elif isinstance(data, dict):
            text = str(data.get("text") or data.get("content") or "")
        else:
            text = str(data)
        if text:
            return {"type": "text", "content": text}

    if event.get("current_tool_use"):
        tool_use = event.get("current_tool_use")
        if isinstance(tool_use, dict):
            return {
                "type": "tool_use",
                "name": str(tool_use.get("name", "")),
                "input": tool_use.get("input") if isinstance(tool_use.get("input"), dict) else {},
            }
        return {"type": "tool_use", "name": str(tool_use), "input": {}}

    if "result" in event:
        result_obj = event.get("result")
        usage = _extract_usage_from_obj(result_obj)
        return {
            "type": "complete",
            "usage": usage,
            "result": _extract_result_text(result_obj),
        }

    return None


def _normalize_tier(tier: str | None) -> str:
    t = (tier or "advanced").lower()
    if t in TIER_BUDGETS:
        return t
    if t == "free":
        return "basic"
    if t == "enterprise":
        return "premium"
    return "advanced"


def _over_budget(usage: dict[str, int], tier: str) -> bool:
    budget = TIER_BUDGETS.get(tier, TIER_BUDGETS["advanced"])
    cost = calculate_cost(usage.get("input_tokens", 0), usage.get("output_tokens", 0))
    return cost > budget


async def strands_query(
    prompt: str,
    tenant_id: str = "demo-tenant",
    user_id: str = "demo-user",
    tier: str = "advanced",
    model: str | None = None,
    skill_names: list[str] | None = None,
    session_id: str | None = None,
    max_turns: int = 15,
) -> AsyncGenerator[dict[str, Any], None]:
    """Run supervisor orchestration via Strands and yield normalized events."""
    _ensure_strands()
    effective_tier = _normalize_tier(tier)

    def _model_factory(model_override: str | None = None) -> Any:
        return get_bedrock_model(model_override or model)

    specialist_tools, tool_meta = build_specialist_tools(
        tier=effective_tier,
        model_factory=_model_factory,
        skill_names=skill_names,
    )

    supervisor_prompt = build_supervisor_prompt(
        tenant_id=tenant_id,
        user_id=user_id,
        tier=effective_tier,
        available_tools=tool_meta,
    )

    supervisor_agent = Agent(
        system_prompt=supervisor_prompt,
        tools=specialist_tools,
        model=get_bedrock_model(model),
    )

    usage = {"input_tokens": 0, "output_tokens": 0}
    tool_calls = 0
    complete_seen = False
    stream = supervisor_agent.stream_async(prompt)

    try:
        async for raw_event in stream:
            normalized = normalize_stream_event(raw_event)

            # Keep a best-effort running usage estimate from every raw event.
            raw_usage = _extract_usage_from_obj(raw_event)
            if raw_usage["input_tokens"] or raw_usage["output_tokens"]:
                usage = _merge_usage(usage, raw_usage)

            if not normalized:
                continue

            if normalized["type"] == "text":
                yield normalized
                continue

            if normalized["type"] == "tool_use":
                tool_calls += 1
                if tool_calls > max_turns:
                    yield {
                        "type": "error",
                        "message": f"Turn limit reached: max_turns={max_turns}",
                    }
                    break
                yield normalized
                continue

            if normalized["type"] == "complete":
                c_usage = normalized.get("usage", {})
                usage = _merge_usage(usage, c_usage)
                usage = _merge_usage(usage, _extract_agent_usage(supervisor_agent))

                if _over_budget(usage, effective_tier):
                    yield {
                        "type": "error",
                        "message": f"Budget limit reached for tier '{effective_tier}'",
                    }
                    break

                normalized["usage"] = usage
                complete_seen = True
                yield normalized
                break

            if normalized["type"] == "error":
                yield normalized
                break

        if not complete_seen:
            usage = _merge_usage(usage, _extract_agent_usage(supervisor_agent))
            if _over_budget(usage, effective_tier):
                yield {"type": "error", "message": f"Budget limit reached for tier '{effective_tier}'"}
            else:
                yield {"type": "complete", "usage": usage, "result": ""}

    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error("Strands query error: %s", e, exc_info=True)
        yield {"type": "error", "message": str(e)}
    finally:
        if hasattr(stream, "aclose"):
            try:
                await stream.aclose()
            except Exception:
                pass


async def strands_query_single_skill(
    prompt: str,
    skill_name: str,
    tenant_id: str = "demo-tenant",
    user_id: str = "demo-user",
    tier: str = "advanced",
    model: str | None = None,
    max_turns: int = 5,
) -> AsyncGenerator[dict[str, Any], None]:
    """Invoke a single specialist by constraining skill_names to one entry."""
    async for event in strands_query(
        prompt=prompt,
        tenant_id=tenant_id,
        user_id=user_id,
        tier=tier,
        model=model,
        skill_names=[skill_name],
        max_turns=max_turns,
    ):
        yield event


def get_tools_for_api(tier: str = "advanced") -> list[dict[str, Any]]:
    return to_public_tool_docs(tier=_normalize_tier(tier))
