"""Langfuse trace story API — proxies Langfuse to build conversation traces."""

import base64
import json
import logging
import os
import urllib.request
from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger("eagle.traces")

router = APIRouter(prefix="/api/traces", tags=["traces"])


def _lf_get(path: str, auth: str, host: str) -> dict:
    """GET from Langfuse API with Basic auth."""
    req = urllib.request.Request(
        f"{host}{path}",
        headers={"Authorization": f"Basic {auth}"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def _build_story(observations: list) -> list[dict]:
    """Walk Langfuse observation hierarchy to build the trace story.

    Strands SDK OTEL hierarchy:
      AGEN invoke_agent (supervisor)
        SPAN execute_event_loop_cycle
          GENE chat            ← supervisor LLM call
          TOOL <skill_name>    ← tool span
            AGEN invoke_agent  ← subagent
              SPAN cycle
                GENE chat      ← subagent LLM call
    """
    children_map: dict[str, list] = {}
    for o in observations:
        pid = o.get("parentObservationId")
        if pid:
            children_map.setdefault(pid, []).append(o)

    def kids(oid: str, typ_prefix: str) -> list:
        return sorted(
            [c for c in children_map.get(oid, []) if (c.get("type") or "").startswith(typ_prefix)],
            key=lambda x: x.get("startTime", ""),
        )

    def direct_gen(oid: str):
        gs = kids(oid, "GEN")
        return gs[0] if gs else None

    def parse_resp_blocks(obs: dict) -> list:
        out = obs.get("output") or {}
        if not isinstance(out, dict):
            return []
        msg = out.get("message", "")
        if isinstance(msg, str) and msg.strip().startswith("["):
            try:
                return json.loads(msg)
            except Exception:
                return []
        return msg if isinstance(msg, list) else []

    def text_preview(blocks: list, max_len: int = 300) -> str:
        texts = []
        for b in blocks:
            if isinstance(b, dict):
                if "text" in b:
                    texts.append(b["text"])
                elif isinstance(b.get("content"), str):
                    texts.append(b["content"])
        full = " ".join(texts)
        return full[:max_len] + "..." if len(full) > max_len else full

    # Find root supervisor AGEN
    root_agens = [
        o for o in observations
        if (o.get("type") or "").startswith("AGEN") and not o.get("parentObservationId")
    ]
    if not root_agens:
        return []

    supervisor = root_agens[0]
    cycles = kids(supervisor["id"], "SPAN")

    story = []
    turn_num = 0

    for cycle in cycles:
        gen = direct_gen(cycle["id"])
        if not gen:
            continue

        turn_num += 1
        resp_blocks = parse_resp_blocks(gen)

        tool_names = []
        for b in resp_blocks:
            if isinstance(b, dict) and "toolUse" in b:
                tool_names.append(b["toolUse"].get("name", ""))

        turn: dict = {
            "turn": turn_num,
            "input_tokens": gen.get("promptTokens", 0) or 0,
            "output_tokens": gen.get("completionTokens", 0) or 0,
            "tool_calls": tool_names,
            "has_reasoning": any(
                "reasoningContent" in b for b in resp_blocks if isinstance(b, dict)
            ),
            "response_preview": text_preview(resp_blocks),
            "subagents": [],
        }

        # Walk TOOL spans for subagent invocations
        for ts in kids(cycle["id"], "TOOL"):
            sub_agens = kids(ts["id"], "AGEN")
            if not sub_agens:
                continue
            sub = sub_agens[0]
            sub_tok_in = sub_tok_out = 0
            sub_blocks: list = []
            internal_tools: list = []

            for sc in kids(sub["id"], "SPAN"):
                sg = direct_gen(sc["id"])
                if sg:
                    sub_tok_in += sg.get("promptTokens", 0) or 0
                    sub_tok_out += sg.get("completionTokens", 0) or 0
                    sub_blocks.extend(parse_resp_blocks(sg))

                # Collect internal tool calls made by the subagent
                for inner_ts in kids(sc["id"], "TOOL"):
                    # Skip nested subagent re-invocations (they show as AGEN children)
                    if kids(inner_ts["id"], "AGEN"):
                        continue
                    raw_input = inner_ts.get("input") or {}
                    raw_output = inner_ts.get("output") or {}
                    # Normalise: Langfuse may store as dict or JSON string
                    if isinstance(raw_input, str):
                        try:
                            raw_input = json.loads(raw_input)
                        except Exception:
                            raw_input = {"raw": raw_input}
                    if isinstance(raw_output, str):
                        raw_output = raw_output[:500]
                    elif isinstance(raw_output, dict):
                        # Surface 'results' count or first meaningful key
                        if "results" in raw_output and isinstance(raw_output["results"], list):
                            raw_output = {"result_count": len(raw_output["results"])}
                        else:
                            raw_output = {k: str(v)[:200] for k, v in list(raw_output.items())[:3]}
                    internal_tools.append({
                        "name": inner_ts.get("name", "tool"),
                        "input": raw_input,
                        "output_preview": raw_output,
                    })

            # Extract the input query sent to this subagent from the TOOL span input
            ts_input = ts.get("input") or {}
            if isinstance(ts_input, str):
                try:
                    ts_input = json.loads(ts_input)
                except Exception:
                    ts_input = {"query": ts_input}
            subagent_query = (
                ts_input.get("query")
                or ts_input.get("prompt")
                or ts_input.get("message")
                or (json.dumps(ts_input)[:300] if ts_input else "")
            )

            turn["subagents"].append({
                "name": ts.get("name", "unknown"),
                "input_query": subagent_query,
                "input_tokens": sub_tok_in,
                "output_tokens": sub_tok_out,
                "response_preview": text_preview(sub_blocks, 400),
                "internal_tools": internal_tools,
            })

        story.append(turn)

    return story


@router.get("/story")
async def get_trace_story(session_id: str = Query(..., description="Session ID to fetch traces for")):
    """Fetch Langfuse trace and build a conversation story.

    Returns the hierarchical supervisor → subagent trace with token counts,
    tool calls, and response previews.
    """
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")

    if not public_key or not secret_key:
        raise HTTPException(
            status_code=503,
            detail="Langfuse not configured — set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY",
        )

    host = os.getenv("LANGFUSE_HOST", "https://us.cloud.langfuse.com")
    auth = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()

    # Fetch traces for session
    try:
        traces_resp = _lf_get(f"/api/public/traces?sessionId={session_id}&limit=5", auth, host)
        traces = sorted(
            traces_resp.get("data", []),
            key=lambda t: t.get("timestamp", ""),
            reverse=True,
        )
    except Exception as e:
        logger.error("Langfuse traces fetch failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Langfuse API error: {e}")

    if not traces:
        raise HTTPException(status_code=404, detail=f"No traces found for session {session_id}")

    trace = traces[0]
    trace_id = trace["id"]

    # Fetch all observations for this trace
    try:
        obs_resp = _lf_get(f"/api/public/observations?traceId={trace_id}&limit=100", auth, host)
        observations = obs_resp.get("data", [])
    except Exception as e:
        logger.error("Langfuse observations fetch failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Langfuse API error: {e}")

    story = _build_story(observations)

    total_in = sum(t["input_tokens"] for t in story)
    total_out = sum(t["output_tokens"] for t in story)
    total_sub_in = sum(s["input_tokens"] for t in story for s in t["subagents"])
    total_sub_out = sum(s["output_tokens"] for t in story for s in t["subagents"])

    return {
        "trace_id": trace_id,
        "session_id": session_id,
        "timestamp": trace.get("timestamp"),
        "total_observations": len(observations),
        "supervisor_turns": len(story),
        "total_tokens": {
            "supervisor": {"input": total_in, "output": total_out},
            "subagents": {"input": total_sub_in, "output": total_sub_out},
            "combined": {"input": total_in + total_sub_in, "output": total_out + total_sub_out},
        },
        "story": story,
    }


@router.get("/sessions")
async def list_trace_sessions(limit: int = Query(10, ge=1, le=50)):
    """List recent Langfuse sessions with trace counts."""
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")

    if not public_key or not secret_key:
        raise HTTPException(status_code=503, detail="Langfuse not configured")

    host = os.getenv("LANGFUSE_HOST", "https://us.cloud.langfuse.com")
    auth = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()

    try:
        resp = _lf_get(f"/api/public/sessions?limit={limit}", auth, host)
        return resp
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Langfuse API error: {e}")
