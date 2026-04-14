"""Langfuse analytical report generator.

Pulls traces + observations for a time window from Langfuse Cloud, aggregates by
environment / tool / document type / research keyword / user, optionally joins a
CloudWatch error scan, and emits markdown + HTML reports. Used by the
`langfuse-analytics` skill.

Usage:
    python .claude/skills/langfuse-analytics/scripts/langfuse_report.py --window=today
    python .claude/skills/langfuse-analytics/scripts/langfuse_report.py --window=4h --env=qa
    python .claude/skills/langfuse-analytics/scripts/langfuse_report.py --window=7d --out=report.md
    python .claude/skills/langfuse-analytics/scripts/langfuse_report.py --window=24h --html=dash.html --cloudwatch
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*_args, **_kwargs):
        return None


REPO_ROOT = Path(__file__).resolve().parents[4]
SERVER_ENV = REPO_ROOT / "server" / ".env"


def parse_window(window: str) -> datetime:
    now = datetime.now(timezone.utc)
    if window == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    m = re.match(r"^(\d+)([hd])$", window)
    if not m:
        raise SystemExit(f"Invalid --window '{window}'. Use: today, 1h, 4h, 24h, 7d")
    n = int(m.group(1))
    unit = m.group(2)
    delta = timedelta(hours=n) if unit == "h" else timedelta(days=n)
    return now - delta


def load_credentials() -> tuple[str, str, str, str]:
    load_dotenv(SERVER_ENV)
    pub = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    sec = os.getenv("LANGFUSE_SECRET_KEY", "")
    host = os.getenv("LANGFUSE_HOST", "https://us.cloud.langfuse.com")
    project_id = os.getenv("LANGFUSE_PROJECT_ID", "")
    if not pub or not sec:
        raise SystemExit(
            f"LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY not set in {SERVER_ENV}"
        )
    return pub, sec, host, project_id


async def _paged_get(client: httpx.AsyncClient, url: str, params: dict, headers: dict, label: str) -> list:
    out: list = []
    page = 1
    while True:
        p = {**params, "page": page, "limit": 100}
        r = await client.get(url, params=p, headers=headers)
        r.raise_for_status()
        j = r.json()
        data = j.get("data", [])
        if not data:
            break
        out.extend(data)
        meta = j.get("meta", {})
        total_pages = meta.get("totalPages", 1)
        print(f"  [{label}] page {page}/{total_pages} -> {len(data)} (cum={len(out)})", file=sys.stderr)
        if page >= total_pages or page >= 30:
            break
        page += 1
    return out


async def fetch_all(from_ts: str) -> tuple[list, list]:
    pub, sec, host, _ = load_credentials()
    auth = "Basic " + base64.b64encode(f"{pub}:{sec}".encode()).decode()
    headers = {"Authorization": auth}
    async with httpx.AsyncClient(timeout=120) as c:
        traces = await _paged_get(
            c, f"{host}/api/public/traces", {"fromTimestamp": from_ts}, headers, "traces"
        )
        obs = await _paged_get(
            c, f"{host}/api/public/observations", {"fromStartTime": from_ts}, headers, "obs"
        )
    return traces, obs


def obs_env(o: dict) -> str:
    md = o.get("metadata") or {}
    if isinstance(md, dict):
        attrs = md.get("attributes") or {}
        if isinstance(attrs, dict):
            env = attrs.get("eagle.environment")
            if env:
                return str(env)
        env = md.get("environment")
        if env and env != "default":
            return str(env)
    return "unknown"


def obs_session(o: dict) -> str | None:
    md = o.get("metadata") or {}
    if isinstance(md, dict):
        attrs = md.get("attributes") or {}
        if isinstance(attrs, dict):
            sid = attrs.get("eagle.session_id") or attrs.get("session.id")
            if sid:
                return str(sid)
        sid = md.get("session_id")
        if sid:
            return str(sid)
    return None


def trace_user(t: dict) -> str:
    uid = t.get("userId")
    if uid:
        return str(uid)
    md = t.get("metadata") or {}
    if isinstance(md, dict):
        attrs = md.get("attributes") or {}
        if isinstance(attrs, dict):
            for k in ("eagle.user_id", "user.id", "langfuse.user.id"):
                v = attrs.get(k)
                if v:
                    return str(v)
        for k in ("user_id", "userId"):
            v = md.get(k)
            if v:
                return str(v)
    return "unknown"


def trace_env(t: dict) -> str:
    md = t.get("metadata") or {}
    if isinstance(md, dict):
        attrs = md.get("attributes") or {}
        if isinstance(attrs, dict):
            env = attrs.get("eagle.environment")
            if env:
                return str(env)
        env = md.get("environment")
        if env and env != "default":
            return str(env)
    for tag in t.get("tags") or []:
        if isinstance(tag, str) and tag.startswith("env:"):
            return tag.split(":", 1)[1]
    return "unknown"


def trace_cost(t: dict) -> float:
    """Total cost (USD) for a Langfuse trace.

    Langfuse surfaces this at the trace root as `totalCost` (float). There is
    no nested `usage` object on traces — tokens/usage live on the child
    GENERATION observations. We fall back to `calculatedTotalCost` for
    older SDK versions that still emit that key.
    """
    for key in ("totalCost", "calculatedTotalCost"):
        v = t.get(key)
        if v is None:
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    return 0.0


def obs_tokens(o: dict) -> tuple[int, int]:
    """Input / output tokens for a Langfuse observation.

    GENERATION observations expose tokens in three places (in priority order):
      1. `usageDetails` (current Langfuse v4 shape — what Strands OTel emits)
      2. `usage.input` / `usage.output`            (legacy)
      3. `promptTokens` / `completionTokens`       (pre-v4)
    """
    ud = o.get("usageDetails")
    if isinstance(ud, dict):
        try:
            return int(ud.get("input") or 0), int(ud.get("output") or 0)
        except (TypeError, ValueError):
            pass
    u = o.get("usage")
    if isinstance(u, dict):
        try:
            return int(u.get("input") or 0), int(u.get("output") or 0)
        except (TypeError, ValueError):
            pass
    try:
        return int(o.get("promptTokens") or 0), int(o.get("completionTokens") or 0)
    except (TypeError, ValueError):
        return 0, 0


def obs_cost(o: dict) -> float:
    """Cost (USD) attributed to a single observation (fallback path)."""
    cd = o.get("costDetails")
    if isinstance(cd, dict):
        try:
            return float(cd.get("total") or 0)
        except (TypeError, ValueError):
            pass
    for key in ("calculatedTotalCost", "totalPrice"):
        v = o.get(key)
        if v is None:
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    return 0.0


def parse_tool_input(o: dict) -> dict | None:
    inp = o.get("input")
    if not isinstance(inp, list):
        return None
    for item in inp:
        if isinstance(item, dict) and item.get("role") == "tool":
            content = item.get("content")
            if isinstance(content, str):
                try:
                    return json.loads(content)
                except Exception:
                    return None
            if isinstance(content, dict):
                return content
    return None


def aggregate(traces: list, obs: list, env_filter: str | None) -> dict:
    # Build trace index first: trace_id -> {user, env, cost, session, level}
    # Tokens are NOT on traces — they are aggregated from GENERATION
    # observations below and attributed back via trace_index[traceId].user.
    trace_index: dict[str, dict] = {}
    for t in traces:
        tid = t.get("id") or ""
        if not tid:
            continue
        trace_index[tid] = {
            "user": trace_user(t),
            "env": trace_env(t),
            "cost": trace_cost(t),
            "session": t.get("sessionId") or "",
            "level": t.get("level") or "",
        }

    # Apply env filter against both obs and the trace pool so user rollups
    # reflect the same scope as tool counts.
    if env_filter and env_filter != "all":
        obs = [o for o in obs if obs_env(o) == env_filter]
        traces = [t for t in traces if trace_env(t) == env_filter]

    env_counts: Counter = Counter()
    env_tool_counts: dict[str, Counter] = defaultdict(Counter)
    env_gen_counts: Counter = Counter()
    env_error_counts: Counter = Counter()
    env_cost: Counter = Counter()
    session_ids: set = set()

    tool_counts: Counter = Counter()
    tool_envs: dict[str, set] = defaultdict(set)

    doc_types: Counter = Counter()
    doc_titles: dict[str, list] = defaultdict(list)

    research_keywords: Counter = Counter()
    web_queries: Counter = Counter()
    far_queries: list = []
    compliance_ops: Counter = Counter()

    errors: list = []

    # Per-user rollup skeleton.
    def _new_user() -> dict:
        return {
            "traces": 0,
            "sessions": set(),
            "envs": set(),
            "tool_calls": 0,
            "generations": 0,
            "cost": 0.0,
            "tokens_in": 0,
            "tokens_out": 0,
            "errors": 0,
            "docs": 0,
            "doc_types": Counter(),
            "top_tools": Counter(),
        }

    per_user: dict[str, dict] = defaultdict(_new_user)

    # Trace-level cost aggregation. Tokens come from observations below.
    total_cost = 0.0
    for t in traces:
        uid = trace_user(t)
        env = trace_env(t)
        c = trace_cost(t)
        total_cost += c
        env_cost[env] += c
        u = per_user[uid]
        u["traces"] += 1
        sid = t.get("sessionId")
        if sid:
            u["sessions"].add(sid)
        u["envs"].add(env)
        u["cost"] += c
        if t.get("level") == "ERROR":
            u["errors"] += 1

    total_tokens_in = 0
    total_tokens_out = 0
    for o in obs:
        env = obs_env(o)
        env_counts[env] += 1
        sid = obs_session(o)
        if sid:
            session_ids.add(sid)
        # Attribute the observation back to its trace-level user.
        tid = o.get("traceId") or ""
        uid = (trace_index.get(tid) or {}).get("user", "unknown")
        if o.get("level") == "ERROR":
            env_error_counts[env] += 1
            errors.append({
                "traceId": tid,
                "name": o.get("name"),
                "env": env,
                "user": uid,
                "message": (o.get("statusMessage") or "")[:300],
            })
        t = o.get("type")
        if t == "GENERATION":
            env_gen_counts[env] += 1
            per_user[uid]["generations"] += 1
            tin, tout = obs_tokens(o)
            total_tokens_in += tin
            total_tokens_out += tout
            per_user[uid]["tokens_in"] += tin
            per_user[uid]["tokens_out"] += tout
        elif t == "TOOL":
            name = o.get("name") or "(unknown)"
            tool_counts[name] += 1
            tool_envs[name].add(env)
            env_tool_counts[env][name] += 1
            per_user[uid]["tool_calls"] += 1
            per_user[uid]["top_tools"][name] += 1
            payload = parse_tool_input(o)
            if name == "create_document" and payload:
                dtype = payload.get("document_type") or payload.get("doc_type") or payload.get("type") or "unknown"
                title = payload.get("title") or payload.get("name") or payload.get("file_name") or ""
                doc_types[str(dtype)] += 1
                per_user[uid]["docs"] += 1
                per_user[uid]["doc_types"][str(dtype)] += 1
                if title:
                    doc_titles[str(dtype)].append(str(title))
            elif name == "research" and payload:
                kw = payload.get("keyword") or payload.get("query") or ""
                if kw:
                    research_keywords[str(kw)[:80]] += 1
            elif name == "web_search" and payload:
                q = payload.get("query") or payload.get("search_query") or ""
                if q:
                    web_queries[str(q)[:90]] += 1
            elif name == "search_far" and payload:
                far_queries.append(payload)
            elif name == "query_compliance_matrix" and payload:
                op = payload.get("operation") or "query"
                compliance_ops[str(op)] += 1

    return {
        "env_counts": env_counts,
        "env_tool_counts": env_tool_counts,
        "env_gen_counts": env_gen_counts,
        "env_error_counts": env_error_counts,
        "env_cost": env_cost,
        "session_count": len(session_ids),
        "tool_counts": tool_counts,
        "tool_envs": {k: sorted(v) for k, v in tool_envs.items()},
        "doc_types": doc_types,
        "doc_titles": doc_titles,
        "research_keywords": research_keywords,
        "web_queries": web_queries,
        "far_queries": far_queries,
        "compliance_ops": compliance_ops,
        "errors": errors,
        "trace_count": len(traces),
        "obs_count": len(obs),
        "per_user": per_user,
        "total_cost": total_cost,
        "total_tokens_in": total_tokens_in,
        "total_tokens_out": total_tokens_out,
        "user_count": len([u for u in per_user if u != "unknown"]) or len(per_user),
    }


# -----------------------------------------------------------------------------
# CloudWatch scan
# -----------------------------------------------------------------------------

CLOUDWATCH_DEFAULT_GROUPS = (
    "/eagle/ecs/backend-dev",
    "/eagle/ecs/backend-qa",
    "/eagle/ecs/frontend-dev",
    "/eagle/ecs/frontend-qa",
    "/eagle/app",
)

# (needle, category, severity)
CLOUDWATCH_PATTERNS: tuple[tuple[str, str, str], ...] = (
    ("Token has expired", "SSO Token Expired", "ACTIONABLE"),
    ("AccessDenied", "IAM Access Denied", "ACTIONABLE"),
    ("ThrottlingException", "Bedrock Throttling", "Warning"),
    ("ModelNotReady", "Bedrock Cold Start", "Noise"),
    ("ValidationException", "Bedrock Validation", "ACTIONABLE"),
    ("ModelTimeout", "Bedrock Timeout", "ACTIONABLE"),
    ("SIGTERM", "Container Killed", "ACTIONABLE"),
    ("OutOfMemory", "OOM", "ACTIONABLE"),
    (" OOM ", "OOM", "ACTIONABLE"),
    ("Task stopped", "ECS Task Crash", "ACTIONABLE"),
    ("Failed to detach context", "OTel Context (handled)", "Noise"),
    ("DeprecationWarning", "Python Deprecation", "Noise"),
    ("BadZipFile", "Corrupt Upload", "ACTIONABLE"),
)


_LOGS_INSIGHTS_QUERY = r"""
fields @timestamp, @message, @logStream
| filter @message like /(?i)error|exception|fatal|traceback|denied|sigterm| oom |throttling|token has expired|badzipfile|task stopped/
| sort @timestamp desc
| limit 200
""".strip()


def scan_cloudwatch(
    start_dt: datetime,
    profile: str = "eagle",
    region: str = "us-east-1",
    log_groups: tuple[str, ...] | list[str] = CLOUDWATCH_DEFAULT_GROUPS,
    limit_per_group: int = 200,
    poll_timeout: int = 120,
) -> dict:
    """Scan CloudWatch for error-level events in the requested window.

    Uses CloudWatch Logs Insights (start_query + get_query_results) instead of
    filter_log_events, because the latter paginates chronologically from oldest
    events and will burn through thousands of health-check lines before hitting
    any actual error. Logs Insights evaluates the filter server-side and
    returns newest-first results.

    Returns a dict with `available=False` + `reason` on any failure so the
    caller can render a 'degraded' section instead of aborting the whole report.
    """
    try:
        import time
        import boto3  # type: ignore
        from botocore.exceptions import (  # type: ignore
            BotoCoreError,
            ClientError,
            NoCredentialsError,
            TokenRetrievalError,
        )
    except ImportError:
        return {"available": False, "reason": "boto3 not installed"}

    try:
        session = boto3.Session(profile_name=profile, region_name=region)
        client = session.client("logs")
    except Exception as e:  # noqa: BLE001
        return {"available": False, "reason": f"boto3 session failed: {e}"}

    start_ts = int(start_dt.timestamp())
    end_ts = int(datetime.now(timezone.utc).timestamp())

    per_group: dict[str, list] = {}
    totals: Counter = Counter()
    categories: Counter = Counter()
    severities: Counter = Counter()
    sample_events: list = []

    # Start all queries in parallel so the whole scan completes in one
    # poll cycle rather than N sequential waits.
    pending: list[tuple[str, str]] = []  # (log_group, query_id)
    for g in log_groups:
        try:
            q = client.start_query(
                logGroupName=g,
                startTime=start_ts,
                endTime=end_ts,
                queryString=_LOGS_INSIGHTS_QUERY,
                limit=limit_per_group,
            )
            pending.append((g, q["queryId"]))
        except (NoCredentialsError, TokenRetrievalError) as e:
            return {
                "available": False,
                "reason": f"AWS SSO expired or missing — run `aws sso login --profile {profile}` ({e})",
            }
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            # A missing log group shouldn't kill the whole scan.
            if code in ("ResourceNotFoundException", "InvalidParameterException"):
                per_group[g] = [{"error": f"{code}: {e.response.get('Error', {}).get('Message', '')[:160]}"}]
                totals[g] = -1
                continue
            return {"available": False, "reason": f"start_query failed on {g}: {e}"}
        except BotoCoreError as e:
            return {"available": False, "reason": f"start_query failed on {g}: {e}"}

    # Poll all pending queries until each one completes / fails / times out.
    deadline = time.time() + poll_timeout
    results_by_group: dict[str, list] = {}
    while pending and time.time() < deadline:
        still: list[tuple[str, str]] = []
        for g, qid in pending:
            try:
                r = client.get_query_results(queryId=qid)
            except (ClientError, BotoCoreError) as e:
                per_group[g] = [{"error": f"get_query_results: {e}"}]
                totals[g] = -1
                continue
            status = r.get("status")
            if status == "Complete":
                results_by_group[g] = r.get("results", [])
            elif status in ("Failed", "Cancelled", "Timeout"):
                per_group[g] = [{"error": f"query {status}"}]
                totals[g] = -1
            else:
                still.append((g, qid))
        pending = still
        if pending:
            time.sleep(1)

    # Anything still pending when the timeout fires gets recorded as an error.
    for g, _qid in pending:
        per_group[g] = [{"error": f"query exceeded {poll_timeout}s timeout"}]
        totals[g] = -1

    # Process results. Each row is a list of {field, value} dicts.
    for g, rows in results_by_group.items():
        out_rows: list = []
        for row in rows:
            fields = {f["field"]: f["value"] for f in row if "field" in f}
            msg = (fields.get("@message") or "").strip()
            stream = fields.get("@logStream") or ""
            ts = fields.get("@timestamp") or ""
            out_rows.append({
                "timestamp": ts,
                "stream": stream,
                "message": msg[:500],
            })
            matched = False
            for needle, cat, sev in CLOUDWATCH_PATTERNS:
                if needle.lower() in msg.lower():
                    categories[cat] += 1
                    severities[sev] += 1
                    matched = True
                    break
            if not matched:
                categories["Other"] += 1
                severities["Unknown"] += 1
            if len(sample_events) < 25:
                sample_events.append({
                    "group": g,
                    "timestamp": ts,
                    "stream": stream,
                    "message": msg[:240],
                })
        per_group[g] = out_rows
        totals[g] = len(out_rows)

    # Ensure every requested log group has an entry even if empty.
    for g in log_groups:
        if g not in per_group:
            per_group[g] = []
            totals.setdefault(g, 0)

    return {
        "available": True,
        "profile": profile,
        "region": region,
        "start": start_dt.isoformat(),
        "end": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "query": _LOGS_INSIGHTS_QUERY,
        "groups": list(log_groups),
        "per_group": per_group,
        "totals_by_group": dict(totals),
        "categories": dict(categories),
        "severities": dict(severities),
        "sample_events": sample_events,
        "total_events": sum(v for v in totals.values() if v > 0),
    }


def render_markdown(agg: dict, window: str, env_filter: str, cw: dict | None = None) -> str:
    lines: list = []
    lines.append("# Langfuse Activity Report")
    lines.append(f"_Window: **{window}** · Env filter: **{env_filter}** · Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}_")
    lines.append("")

    lines.append("## Summary")
    lines.append(f"- Total traces: **{agg['trace_count']}**")
    lines.append(f"- Total observations: **{agg['obs_count']}**")
    lines.append(f"- Unique sessions: **{agg['session_count']}**")
    lines.append(f"- Unique users: **{agg.get('user_count', 0)}**")
    lines.append(f"- Tool calls: **{sum(agg['tool_counts'].values())}**")
    lines.append(f"- Generations (LLM calls): **{sum(agg.get('env_gen_counts', Counter()).values())}**")
    lines.append(f"- Total cost (USD): **${agg.get('total_cost', 0):.4f}**")
    lines.append(
        f"- Tokens: **{agg.get('total_tokens_in', 0):,}** in / "
        f"**{agg.get('total_tokens_out', 0):,}** out"
    )
    lines.append(f"- Errors: **{sum(agg['env_error_counts'].values())}**")
    lines.append("")

    lines.append("## Environment Breakdown")
    lines.append("| Environment | Observations | Tool calls | Generations | Errors | Cost (USD) |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: |")
    env_cost: Counter = agg.get("env_cost") or Counter()
    for env, cnt in agg["env_counts"].most_common():
        tc = sum(agg["env_tool_counts"].get(env, Counter()).values())
        gc = agg["env_gen_counts"].get(env, 0)
        ec = agg["env_error_counts"].get(env, 0)
        cost = env_cost.get(env, 0.0)
        lines.append(f"| {env} | {cnt} | {tc} | {gc} | {ec} | ${cost:.4f} |")
    lines.append("")

    # --- Per-user aggregates ---
    per_user: dict = agg.get("per_user") or {}
    if per_user:
        lines.append("## Per-User Usage")
        lines.append(
            "| User | Traces | Sessions | Tool Calls | Generations | Tokens In | Tokens Out | Cost (USD) | Docs | Errors | Top Tool |"
        )
        lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |")
        rows = sorted(per_user.items(), key=lambda kv: kv[1]["cost"], reverse=True)
        for uid, u in rows[:30]:
            top_tool = ""
            if u["top_tools"]:
                name, c = u["top_tools"].most_common(1)[0]
                top_tool = f"{name} ({c})"
            lines.append(
                f"| `{uid}` | {u['traces']} | {len(u['sessions'])} | {u['tool_calls']} | "
                f"{u['generations']} | {u['tokens_in']:,} | {u['tokens_out']:,} | "
                f"${u['cost']:.4f} | {u['docs']} | {u['errors']} | {top_tool} |"
            )
        lines.append("")

    lines.append("## Tools Used")
    if not agg["tool_counts"]:
        lines.append("_No tool calls in window._")
    else:
        lines.append("| Tool | Calls | Envs |")
        lines.append("| --- | ---: | --- |")
        for name, cnt in agg["tool_counts"].most_common():
            envs = ", ".join(agg["tool_envs"].get(name, []))
            lines.append(f"| `{name}` | {cnt} | {envs} |")
    lines.append("")

    lines.append("## Documents Generated (`create_document`)")
    if not agg["doc_types"]:
        lines.append("_No documents generated in window._")
    else:
        lines.append("| Document Type | Count | Sample Titles |")
        lines.append("| --- | ---: | --- |")
        for dtype, cnt in agg["doc_types"].most_common():
            titles = agg["doc_titles"].get(dtype, [])
            sample = "; ".join(t[:80] for t in titles[:2])
            lines.append(f"| `{dtype}` | {cnt} | {sample} |")
    lines.append("")

    lines.append("## Specialist Subagent / Research Dispatches")
    if not agg["research_keywords"]:
        lines.append("_No research subagent calls in window._")
    else:
        lines.append("| Topic / Keyword | Calls |")
        lines.append("| --- | ---: |")
        for kw, cnt in agg["research_keywords"].most_common(20):
            lines.append(f"| {kw} | {cnt} |")
    lines.append("")

    lines.append("## Sources Fetched — `web_search` Queries")
    if not agg["web_queries"]:
        lines.append("_No web searches in window._")
    else:
        for q, cnt in agg["web_queries"].most_common(20):
            suffix = f" ({cnt}x)" if cnt > 1 else ""
            lines.append(f"- {q}{suffix}")
    lines.append("")

    if agg["compliance_ops"]:
        lines.append("## Compliance Matrix Operations")
        lines.append("| Operation | Calls |")
        lines.append("| --- | ---: |")
        for op, cnt in agg["compliance_ops"].most_common():
            lines.append(f"| `{op}` | {cnt} |")
        lines.append("")

    if agg["far_queries"]:
        lines.append("## FAR Searches")
        for fq in agg["far_queries"][:10]:
            lines.append(f"- `{json.dumps(fq, default=str)[:160]}`")
        lines.append("")

    if agg["errors"]:
        lines.append("## Errors (Langfuse)")
        for e in agg["errors"][:15]:
            user = e.get("user") or "unknown"
            lines.append(
                f"- **{e['env']}** · user=`{user}` · `{e['traceId']}` — {e['name']}: {e['message']}"
            )
        lines.append("")

    # --- CloudWatch section ---
    if cw is not None:
        lines.append("## CloudWatch Error Scan")
        if not cw.get("available"):
            lines.append(f"_Unavailable — {cw.get('reason', 'unknown error')}._")
        else:
            lines.append(
                f"_Profile: `{cw['profile']}` · Region: `{cw['region']}` · "
                f"Since: `{cw['start']}` · Total events: **{cw.get('total_events', 0)}**_"
            )
            lines.append("")
            lines.append("### Events by Log Group")
            lines.append("| Log Group | Count |")
            lines.append("| --- | ---: |")
            for g, n in (cw.get("totals_by_group") or {}).items():
                label = str(n) if n >= 0 else "error"
                lines.append(f"| `{g}` | {label} |")
            lines.append("")
            cats = cw.get("categories") or {}
            if cats:
                lines.append("### Categories")
                lines.append("| Category | Count | Severity |")
                lines.append("| --- | ---: | --- |")
                sev_map = {
                    cat: sev
                    for needle, cat, sev in CLOUDWATCH_PATTERNS
                }
                for cat, cnt in sorted(cats.items(), key=lambda kv: kv[1], reverse=True):
                    sev = sev_map.get(cat, "Unknown")
                    lines.append(f"| {cat} | {cnt} | {sev} |")
                lines.append("")
            samples = cw.get("sample_events") or []
            if samples:
                lines.append("### Recent Events (sample)")
                for s in samples[:15]:
                    msg = s["message"].replace("\n", " ")[:200]
                    lines.append(f"- **{s['timestamp']}** `{s['group']}` · {msg}")
                lines.append("")

    return "\n".join(lines)


# -----------------------------------------------------------------------------
# HTML renderer
# -----------------------------------------------------------------------------

def _html_escape(s: str) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def render_html(agg: dict, window: str, env_filter: str, cw: dict | None = None) -> str:
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    total_cost = agg.get("total_cost", 0.0)
    total_tool = sum(agg["tool_counts"].values())
    total_gen = sum(agg.get("env_gen_counts", Counter()).values())
    total_err = sum(agg["env_error_counts"].values())
    cw_err_count = (cw or {}).get("total_events", 0) if cw else 0

    def kpi(label: str, value: str, accent: str = "") -> str:
        return (
            f'<div class="kpi {accent}"><div class="kpi-label">{_html_escape(label)}</div>'
            f'<div class="kpi-value">{_html_escape(value)}</div></div>'
        )

    def table(headers: list[str], rows: list[list[str]], empty_msg: str = "_No data._") -> str:
        if not rows:
            return f'<p class="empty">{_html_escape(empty_msg)}</p>'
        thead = "".join(f"<th>{_html_escape(h)}</th>" for h in headers)
        body = "".join(
            "<tr>" + "".join(f"<td>{_html_escape(c)}</td>" for c in r) + "</tr>"
            for r in rows
        )
        return f"<table><thead><tr>{thead}</tr></thead><tbody>{body}</tbody></table>"

    # Environment rows
    env_cost = agg.get("env_cost") or Counter()
    env_rows = []
    for env, cnt in agg["env_counts"].most_common():
        tc = sum(agg["env_tool_counts"].get(env, Counter()).values())
        gc = agg["env_gen_counts"].get(env, 0)
        ec = agg["env_error_counts"].get(env, 0)
        cost = env_cost.get(env, 0.0)
        env_rows.append([env, str(cnt), str(tc), str(gc), str(ec), f"${cost:.4f}"])

    # Tool rows
    tool_rows = []
    for name, cnt in agg["tool_counts"].most_common(30):
        envs = ", ".join(agg["tool_envs"].get(name, []))
        tool_rows.append([name, str(cnt), envs])

    # Per-user rows
    user_rows = []
    for uid, u in sorted(
        (agg.get("per_user") or {}).items(),
        key=lambda kv: kv[1]["cost"],
        reverse=True,
    )[:30]:
        top_tool = ""
        if u["top_tools"]:
            n, c = u["top_tools"].most_common(1)[0]
            top_tool = f"{n} ({c})"
        user_rows.append([
            uid,
            str(u["traces"]),
            str(len(u["sessions"])),
            str(u["tool_calls"]),
            str(u["generations"]),
            f"{u['tokens_in']:,}",
            f"{u['tokens_out']:,}",
            f"${u['cost']:.4f}",
            str(u["docs"]),
            str(u["errors"]),
            top_tool,
        ])

    # Doc rows
    doc_rows = []
    for dtype, cnt in (agg.get("doc_types") or Counter()).most_common(20):
        titles = agg.get("doc_titles", {}).get(dtype, [])
        sample = "; ".join(t[:60] for t in titles[:2])
        doc_rows.append([dtype, str(cnt), sample])

    # Research rows
    research_rows = []
    for kw, cnt in (agg.get("research_keywords") or Counter()).most_common(20):
        research_rows.append([kw, str(cnt)])

    # Web search rows
    web_rows = []
    for q, cnt in (agg.get("web_queries") or Counter()).most_common(20):
        web_rows.append([q, str(cnt)])

    # CloudWatch rendering
    cw_html = ""
    if cw is not None:
        if not cw.get("available"):
            cw_html = (
                '<section><h2>CloudWatch Error Scan</h2>'
                f'<p class="warn">Unavailable — {_html_escape(cw.get("reason", "unknown error"))}</p>'
                '</section>'
            )
        else:
            cw_group_rows = [
                [g, str(n) if n >= 0 else "error"]
                for g, n in (cw.get("totals_by_group") or {}).items()
            ]
            sev_map = {cat: sev for _, cat, sev in CLOUDWATCH_PATTERNS}
            cw_cat_rows = [
                [cat, str(cnt), sev_map.get(cat, "Unknown")]
                for cat, cnt in sorted(
                    (cw.get("categories") or {}).items(),
                    key=lambda kv: kv[1],
                    reverse=True,
                )
            ]
            cw_sample_rows = [
                [s["timestamp"], s["group"], s["stream"][:40], s["message"][:240]]
                for s in (cw.get("sample_events") or [])[:20]
            ]
            cw_html = (
                '<section><h2>CloudWatch Error Scan</h2>'
                f'<p class="meta">Profile: <code>{_html_escape(cw["profile"])}</code> · '
                f'Region: <code>{_html_escape(cw["region"])}</code> · '
                f'Since: <code>{_html_escape(cw["start"])}</code> · '
                f'Total events: <strong>{cw_err_count}</strong></p>'
                '<h3>Events by Log Group</h3>'
                + table(["Log Group", "Count"], cw_group_rows, "No log groups scanned.")
                + "<h3>Categories</h3>"
                + table(["Category", "Count", "Severity"], cw_cat_rows, "No categorized events.")
                + "<h3>Recent Sample Events</h3>"
                + table(["Time", "Log Group", "Stream", "Message"], cw_sample_rows, "No sample events.")
                + "</section>"
            )

    langfuse_url = ""
    try:
        _, _, host, project_id = load_credentials()
        if project_id:
            langfuse_url = f"{host.rstrip('/')}/project/{project_id}/traces"
    except SystemExit:
        langfuse_url = ""

    css = """
    :root{--navy:#0a2540;--accent:#635bff;--bg:#f6f9fc;--ink:#2a3f5f;--muted:#64748b;--warn:#b91c1c;--ok:#047857;}
    *{box-sizing:border-box;}
    body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,sans-serif;margin:0;background:var(--bg);color:var(--ink);}
    header{background:var(--navy);color:#fff;padding:24px 40px;}
    header h1{margin:0;font-size:22px;letter-spacing:.2px;}
    header .meta{opacity:.8;font-size:13px;margin-top:4px;}
    header a{color:#9ad6ff;text-decoration:none;margin-left:12px;}
    main{max-width:1400px;margin:0 auto;padding:28px 40px 60px;}
    .kpi-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:14px;margin-bottom:28px;}
    .kpi{background:#fff;border:1px solid #e6ebf1;border-radius:10px;padding:16px 18px;box-shadow:0 1px 2px rgba(10,37,64,.04);}
    .kpi-label{color:var(--muted);font-size:12px;letter-spacing:.4px;text-transform:uppercase;}
    .kpi-value{font-size:24px;font-weight:600;color:var(--navy);margin-top:4px;}
    .kpi.accent .kpi-value{color:var(--accent);}
    .kpi.warn .kpi-value{color:var(--warn);}
    .kpi.ok .kpi-value{color:var(--ok);}
    section{background:#fff;border:1px solid #e6ebf1;border-radius:10px;padding:20px 24px;margin-bottom:22px;box-shadow:0 1px 2px rgba(10,37,64,.04);}
    section h2{margin:0 0 12px;font-size:17px;color:var(--navy);}
    section h3{margin:18px 0 8px;font-size:14px;color:var(--muted);text-transform:uppercase;letter-spacing:.4px;}
    table{width:100%;border-collapse:collapse;font-size:13px;}
    th,td{text-align:left;padding:8px 10px;border-bottom:1px solid #eef2f7;vertical-align:top;}
    th{background:#f9fbfd;color:var(--muted);font-weight:600;text-transform:uppercase;font-size:11px;letter-spacing:.4px;}
    tbody tr:hover{background:#f9fbfd;}
    td code,p code{background:#f1f5f9;padding:1px 5px;border-radius:4px;font-size:12px;}
    .empty{color:var(--muted);font-style:italic;}
    .warn{color:var(--warn);}
    footer{text-align:center;color:var(--muted);font-size:12px;padding:24px;}
    """

    header_extra = f' · <a href="{_html_escape(langfuse_url)}">Open in Langfuse ↗</a>' if langfuse_url else ""

    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>EAGLE | Langfuse Analytics</title>
<style>{css}</style></head><body>
<header>
  <h1>EAGLE | Langfuse Analytics Dashboard</h1>
  <div class="meta">Window: <strong>{_html_escape(window)}</strong> · Env: <strong>{_html_escape(env_filter)}</strong> · Generated {_html_escape(generated)}{header_extra}</div>
</header>
<main>
  <div class="kpi-grid">
    {kpi("Traces", f"{agg['trace_count']:,}")}
    {kpi("Observations", f"{agg['obs_count']:,}")}
    {kpi("Sessions", f"{agg['session_count']:,}")}
    {kpi("Users", f"{agg.get('user_count', 0):,}")}
    {kpi("Tool Calls", f"{total_tool:,}", "accent")}
    {kpi("Generations", f"{total_gen:,}", "accent")}
    {kpi("Tokens In",  f"{agg.get('total_tokens_in', 0):,}")}
    {kpi("Tokens Out", f"{agg.get('total_tokens_out', 0):,}")}
    {kpi("Total Cost", f"${total_cost:.4f}", "ok")}
    {kpi("Langfuse Errors", f"{total_err:,}", "warn" if total_err else "")}
    {kpi("CloudWatch Errors", f"{cw_err_count:,}", "warn" if cw_err_count else "")}
  </div>

  <section><h2>Environment Breakdown</h2>
    {table(["Environment", "Observations", "Tool Calls", "Generations", "Errors", "Cost (USD)"], env_rows, "No environments recorded.")}
  </section>

  <section><h2>Per-User Usage (Top 30 by Cost)</h2>
    {table(["User", "Traces", "Sessions", "Tool Calls", "Generations", "Tokens In", "Tokens Out", "Cost (USD)", "Docs", "Errors", "Top Tool"], user_rows, "No user activity.")}
  </section>

  <section><h2>Tools Used</h2>
    {table(["Tool", "Calls", "Envs"], tool_rows, "No tool calls.")}
  </section>

  <section><h2>Documents Generated (create_document)</h2>
    {table(["Document Type", "Count", "Sample Titles"], doc_rows, "No documents generated.")}
  </section>

  <section><h2>Specialist Subagent / Research Dispatches</h2>
    {table(["Keyword / Topic", "Calls"], research_rows, "No research subagent calls.")}
  </section>

  <section><h2>Sources Fetched — web_search Queries</h2>
    {table(["Query", "Calls"], web_rows, "No web searches.")}
  </section>

  {cw_html}
</main>
<footer>Generated by <code>.claude/skills/langfuse-analytics/scripts/langfuse_report.py</code> at {_html_escape(generated)}</footer>
</body></html>
"""
    return html


def get_summary(window: str = "24h", env: str = "all") -> dict:
    """Reusable one-shot helper. Fetches + aggregates; returns the raw agg dict.

    Used by scripts/morning_report.py to embed Langfuse stats in the Teams card.
    Returns an empty dict (never raises) if credentials are missing or the API fails.
    """
    try:
        start = parse_window(window)
        traces, obs = asyncio.run(fetch_all(start.isoformat()))
        return aggregate(traces, obs, env)
    except Exception as e:  # noqa: BLE001 - never break the caller
        print(f"[langfuse_report.get_summary] skipped: {e}", file=sys.stderr)
        return {}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--window", default="today", help="today, 1h, 4h, 24h, 7d, etc.")
    parser.add_argument("--env", default="all", choices=["all", "local", "qa", "prod", "dev", "unknown"])
    parser.add_argument("--json", help="Optional JSON output path for raw aggregates")
    parser.add_argument("--out", help="Optional markdown output path")
    parser.add_argument("--html", help="Optional HTML dashboard output path")
    parser.add_argument(
        "--cloudwatch",
        action="store_true",
        help="Also scan CloudWatch log groups for errors in the same window (requires `aws sso login --profile eagle`).",
    )
    parser.add_argument("--profile", default="eagle", help="AWS SSO profile for CloudWatch scan")
    parser.add_argument("--region", default="us-east-1", help="AWS region for CloudWatch scan")
    args = parser.parse_args()

    start = parse_window(args.window)
    from_ts = start.isoformat()
    print(f"Fetching traces + observations since {from_ts} ...", file=sys.stderr)
    traces, obs = asyncio.run(fetch_all(from_ts))
    print(f"Fetched {len(traces)} traces, {len(obs)} observations.", file=sys.stderr)

    agg = aggregate(traces, obs, args.env)

    cw = None
    if args.cloudwatch:
        print(f"Scanning CloudWatch (profile={args.profile}, region={args.region}) ...", file=sys.stderr)
        cw = scan_cloudwatch(start_dt=start, profile=args.profile, region=args.region)
        if cw.get("available"):
            print(f"CloudWatch: {cw.get('total_events', 0)} events across {len(cw.get('groups', []))} groups.", file=sys.stderr)
        else:
            print(f"CloudWatch unavailable: {cw.get('reason', '?')}", file=sys.stderr)

    report = render_markdown(agg, args.window, args.env, cw=cw)
    print(report)

    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
        print(f"\nWrote report -> {args.out}", file=sys.stderr)

    if args.html:
        html = render_html(agg, args.window, args.env, cw=cw)
        Path(args.html).write_text(html, encoding="utf-8")
        print(f"Wrote HTML  -> {args.html}", file=sys.stderr)

    if args.json:
        def _to_jsonable(x):
            if isinstance(x, Counter):
                return dict(x)
            if isinstance(x, set):
                return sorted(x)
            if isinstance(x, dict):
                return {k: _to_jsonable(v) for k, v in x.items()}
            if isinstance(x, list):
                return [_to_jsonable(v) for v in x]
            return x
        jagg = {k: _to_jsonable(v) for k, v in agg.items()}
        if cw is not None:
            jagg["cloudwatch"] = _to_jsonable(cw)
        Path(args.json).write_text(json.dumps(jagg, default=str, indent=2), encoding="utf-8")
        print(f"Wrote JSON -> {args.json}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
