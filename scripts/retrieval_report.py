"""3-layer retrieval report (Search / Rank / Read) — Dev vs QA vs RO.

Stitches Langfuse trace data into one HTML report per question.
Auto-detects: duplicate basenames, irrelevant doc pulls, agent_guidance gaps,
Part-15 misrouting, and read efficiency. RO column is free-text from the
docx comparison.

Usage (from repo root):
    python scripts/retrieval_report.py
Writes: docs/development/{ts}-report-retrieval-3layer-v1.html
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / "server" / ".env")

LF_PUB = os.getenv("LANGFUSE_PUBLIC_KEY", "")
LF_SEC = os.getenv("LANGFUSE_SECRET_KEY", "")
LF_HOST = os.getenv("LANGFUSE_HOST", "https://us.cloud.langfuse.com")
LF_PROJECT = os.getenv("LANGFUSE_PROJECT_ID", "")
AUTH = "Basic " + base64.b64encode(f"{LF_PUB}:{LF_SEC}".encode()).decode()


# ─── Scenario registry ────────────────────────────────────────────────────────
# Maps logical question → trace IDs and RO notes pulled from the docx.

@dataclass
class Scenario:
    key: str
    label: str
    question: str
    dev_trace: str | None = None
    qa_trace: str | None = None
    ro_notes: str = ""
    expected_part: str = ""           # canonical FAR part for this question
    suspected_misroute_to: str = ""   # FAR part agent wrongly anchored on


SCENARIOS = [
    Scenario(
        key="q4_yesterday",
        label="Q4 (2026-04-28) — JEFO $25M IDIQ sole-source",
        question="i'm placing a $25m sole-source order on a multi-award idiq and need to prepare a jefo. what's the approval authority and what elements does the JEFO need?",
        dev_trace="aa0c8d28e37f1a717935327549abeea9",
        qa_trace=None,
        ro_notes=(
            "RO surfaced fewer docs and answered with tighter primary-source grounding. "
            "Reviewer flagged: JEFO table missing 2/10 elements per FAR 16.507-6(d)(2); "
            "'SB set-aside JOFOC requires J&A' was incorrectly stated (FAR 6.102-2 says it does NOT)."
        ),
        expected_part="FAR Part 16.5",
    ),
    Scenario(
        key="q4_today",
        label="Q4 (2026-04-29) — sole source on multi-award IDIQ FAR 16.505",
        question="What are the special rules for issuing a sole source on a multi-award IDIQ under FAR 16.505?",
        dev_trace="069d5187061a61cf52a0f12cafbce886",
        qa_trace=None,
        ro_notes="(no RO comparison run for today's variant)",
        expected_part="FAR Part 16.5",
    ),
    Scenario(
        key="q5",
        label="Q5 — SBIR offeror, debriefing, protest timing",
        question=(
            "An SBIR offeror gets eliminated, then on Day 8 asks for a debriefing and "
            "files a protest before the debrief happens. What's the right sequence of "
            "events here, what are the timelines..."
        ),
        dev_trace="b9579cffb427c974864dac570ff4dd9c",
        qa_trace="d5a4741c4c0692be87d535ec7de667ad",
        ro_notes=(
            "Reviewer (Hash): 'Q5 version is worse — 25 docs pulled and a ton of them irrelevant. "
            "I don't like to focus on the RO ones but it was able to answer the question on a "
            "fraction of the context.' Reviewer (Black): legal instructions need adjusting — "
            "the question has Part-15-shaped vocabulary (debriefing/protest/eliminated offeror) "
            "so EAGLE pulls Part 15 docs and runs with that, even though SBIR is FAR 6.102(d)."
        ),
        expected_part="FAR 6.102(d) (SBIR competitive procedures) + GAO 10-day protest timeliness",
        suspected_misroute_to="FAR Part 15",
    ),
    Scenario(
        key="kb_inventory",
        label="KB inventory probe — 'show me latest additions to s3 knowledge base'",
        question="show me the latest and most recent additions to s3 knowledge base",
        dev_trace="afa43ba16692ecc6ca4c1a162ddb842d",
        qa_trace=None,
        ro_notes="(diagnostic — surfaces what the agent can/can't see in S3)",
        expected_part="(diagnostic)",
    ),
]


# ─── Trace fetching + extraction ──────────────────────────────────────────────

@dataclass
class ResearchCall:
    obs_idx: int
    query: str
    keyword: str
    acquisition_method: str
    contract_value: int | None
    msg_size: int
    s3_keys: list[str] = field(default_factory=list)
    confidence_scores: list[float] = field(default_factory=list)
    part15_hits: int = 0
    part6_hits: int = 0
    part13_hits: int = 0
    sbir_hits: int = 0
    has_agent_guidance: bool = False
    has_agent_route: bool = False


@dataclass
class TraceData:
    trace_id: str
    env: str
    timestamp: str
    obs_count: int
    research_calls: list[ResearchCall] = field(default_factory=list)
    s3_doc_ops: list[dict] = field(default_factory=list)
    search_far_calls: int = 0
    permission_denied_count: int = 0
    total_candidates: int = 0
    unique_basenames: int = 0
    duplicate_basenames: dict[str, int] = field(default_factory=dict)
    cross_prefix_dupes: dict[str, list[str]] = field(default_factory=dict)
    error: str | None = None


PART15_RX = re.compile(r"FAR\s*Part\s*15|FAR\s*15\.|15\.50[3-9]|15\.30[3-9]", re.I)
PART6_RX = re.compile(r"FAR\s*Part\s*6|FAR\s*6\.|6\.10[0-9]|6\.30[0-9]", re.I)
PART13_RX = re.compile(r"FAR\s*Part\s*13|FAR\s*13\.|13\.10[0-9]|13\.50[0-9]", re.I)
S3KEY_RX = re.compile(r'"s3_key"\s*:\s*"([^"]+)"')
CONF_RX = re.compile(r'"confidence_score"\s*:\s*([0-9.]+)')


async def fetch_trace(client: httpx.AsyncClient, trace_id: str) -> TraceData:
    """Pull observations and extract retrieval signals."""
    if not trace_id:
        return TraceData(trace_id="", env="", timestamp="", obs_count=0)

    r = await client.get(
        f"{LF_HOST}/api/public/observations",
        params={"traceId": trace_id, "limit": 200},
        headers={"Authorization": AUTH},
    )
    if r.status_code != 200:
        return TraceData(trace_id=trace_id, env="", timestamp="", obs_count=0,
                         error=f"HTTP {r.status_code}")
    obs = r.json().get("data", [])

    # Trace-level metadata
    rt = await client.get(f"{LF_HOST}/api/public/traces/{trace_id}",
                          headers={"Authorization": AUTH})
    env = ""
    ts = ""
    if rt.status_code == 200:
        td = rt.json()
        env = (td.get("metadata") or {}).get("environment") or ""
        ts = td.get("timestamp", "")

    out = TraceData(trace_id=trace_id, env=env, timestamp=ts, obs_count=len(obs))

    all_keys: list[str] = []
    for i, o in enumerate(obs):
        otype = o.get("type", "")
        name = o.get("name", "")
        if otype == "TOOL" and name == "research":
            inp = o.get("input")
            inp_str = json.dumps(inp) if inp else ""
            # The input is wrapped — extract the inner JSON
            try:
                inner = json.loads(inp[0]["content"]) if isinstance(inp, list) and inp else {}
            except Exception:
                inner = {}
            output = o.get("output") or {}
            msg = output.get("message", "") if isinstance(output, dict) else ""

            keys = S3KEY_RX.findall(msg)
            confs = [float(x) for x in CONF_RX.findall(msg)]
            call = ResearchCall(
                obs_idx=i,
                query=str(inner.get("query", ""))[:300],
                keyword=str(inner.get("keyword", ""))[:300],
                acquisition_method=str(inner.get("acquisition_method", "")),
                contract_value=inner.get("contract_value"),
                msg_size=len(msg),
                s3_keys=keys,
                confidence_scores=confs,
                part15_hits=len(PART15_RX.findall(msg)),
                part6_hits=len(PART6_RX.findall(msg)),
                part13_hits=len(PART13_RX.findall(msg)),
                sbir_hits=msg.lower().count("sbir"),
                has_agent_guidance=("agent_guidance" in msg),
                has_agent_route=("agent_route" in msg),
            )
            out.research_calls.append(call)
            all_keys.extend(keys)
        elif otype == "TOOL" and name == "s3_document_ops":
            output = o.get("output") or {}
            out_str = json.dumps(output)
            denied = "permission denied" in out_str.lower() or "access denied" in out_str.lower()
            if denied:
                out.permission_denied_count += 1
            out.s3_doc_ops.append({
                "obs_idx": i,
                "input": json.dumps(o.get("input", ""))[:200],
                "denied": denied,
                "output_preview": out_str[:300],
            })
        elif otype == "TOOL" and name == "search_far":
            out.search_far_calls += 1

    out.total_candidates = len(all_keys)
    basenames = [k.split("/")[-1] for k in all_keys]
    bn_counter = Counter(basenames)
    out.unique_basenames = len(bn_counter)
    out.duplicate_basenames = {n: c for n, c in bn_counter.items() if c > 1}

    # Cross-prefix duplicates: same basename appearing under different S3 prefixes
    by_basename: dict[str, list[str]] = {}
    for k in all_keys:
        by_basename.setdefault(k.split("/")[-1], []).append(k)
    out.cross_prefix_dupes = {
        bn: sorted(set(paths))
        for bn, paths in by_basename.items()
        if len({"/".join(p.split("/")[:-1]) for p in paths}) > 1
    }
    return out


# ─── Heuristics ───────────────────────────────────────────────────────────────

def detect_misroute(td: TraceData, expected_part: str, suspected: str) -> dict:
    """Compare Part-15 vs Part-6 vs Part-13 hit ratios across all research msgs."""
    p15 = sum(c.part15_hits for c in td.research_calls)
    p6 = sum(c.part6_hits for c in td.research_calls)
    p13 = sum(c.part13_hits for c in td.research_calls)
    total = max(p15 + p6 + p13, 1)
    return {
        "part15_pct": round(100 * p15 / total),
        "part6_pct": round(100 * p6 / total),
        "part13_pct": round(100 * p13 / total),
        "p15": p15, "p6": p6, "p13": p13,
        "expected": expected_part,
        "suspected_misroute": suspected,
        "misroute_detected": bool(suspected and "15" in suspected and p15 > p6),
    }


def detect_agent_guidance_gap(td: TraceData) -> dict:
    """Check if any research call returned agent_guidance / agent_route."""
    n = len(td.research_calls)
    if not n:
        return {"calls": 0, "with_guidance": 0, "with_route": 0, "gap": False}
    g = sum(1 for c in td.research_calls if c.has_agent_guidance)
    r = sum(1 for c in td.research_calls if c.has_agent_route)
    return {"calls": n, "with_guidance": g, "with_route": r, "gap": g == 0}


def detect_irrelevant_pulls(td: TraceData, expected_part: str) -> list[str]:
    """Heuristic: docs whose path strongly suggests a different topic than expected."""
    flagged: list[str] = []
    expected_l = expected_part.lower()
    is_micro = "13.2" in expected_l or "micro" in expected_l
    is_part16 = "part 16" in expected_l or "16.5" in expected_l
    is_sbir = "sbir" in expected_l or "6.102" in expected_l

    for call in td.research_calls:
        for k in call.s3_keys:
            kl = k.lower()
            base = k.split("/")[-1]
            # Micro purchase shouldn't pull protest / J&A docs
            if is_micro and ("protest" in kl or "/j&a/" in kl or "justifications/" in kl):
                flagged.append(f"{base} (protest/J&A doc in micro-purchase context)")
            # Part 16 shouldn't be flooded with Part 15 source-selection docs
            if is_part16 and ("15.306" in kl or "15.503" in kl or "15.504" in kl
                              or "competitive_range" in kl):
                flagged.append(f"{base} (Part 15 doc on Part 16 question)")
            # SBIR shouldn't be flooded with Part 15
            if is_sbir and ("15.503" in kl or "15.505" in kl or "15.506" in kl
                            or "part_15" in kl or "competitive_range" in kl):
                flagged.append(f"{base} (Part 15 doc on SBIR question)")
    # Dedup, cap at 12
    out: list[str] = []
    seen: set[str] = set()
    for f in flagged:
        if f in seen:
            continue
        seen.add(f)
        out.append(f)
        if len(out) >= 12:
            break
    return out


# ─── HTML rendering ───────────────────────────────────────────────────────────

CSS = """
body { font: 14px/1.5 -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; background: #f6f8fa; color: #24292f; }
.wrap { max-width: 1280px; margin: 0 auto; padding: 24px; }
h1 { font-size: 22px; margin: 0 0 4px; }
h2 { font-size: 17px; margin: 24px 0 8px; padding-top: 12px; border-top: 2px solid #d0d7de; }
h3 { font-size: 14px; margin: 14px 0 6px; color: #57606a; text-transform: uppercase; letter-spacing: .04em; }
.meta { color: #57606a; font-size: 12px; margin-bottom: 16px; }
.scenario { background: white; border: 1px solid #d0d7de; border-radius: 8px; padding: 16px; margin-bottom: 16px; }
.scenario h2 { margin-top: 0; border: 0; }
.q { background: #f6f8fa; padding: 8px 12px; border-left: 3px solid #0969da; font-style: italic; margin-bottom: 12px; font-size: 13px; }
.cols { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; }
.col { background: #f6f8fa; border-radius: 6px; padding: 12px; }
.col h4 { margin: 0 0 8px; font-size: 12px; text-transform: uppercase; letter-spacing: .04em; color: #57606a; }
.metric { display: flex; justify-content: space-between; padding: 3px 0; font-size: 12px; border-bottom: 1px dashed #eaeef2; }
.metric:last-child { border-bottom: 0; }
.metric .v { font-weight: 600; font-family: ui-monospace, monospace; }
.flag { background: #fff8c5; border-left: 3px solid #d4a72c; padding: 6px 10px; margin: 4px 0; font-size: 12px; border-radius: 4px; }
.flag.bad { background: #ffebe9; border-color: #cf222e; }
.flag.ok  { background: #dcffe4; border-color: #1a7f37; }
.code { font-family: ui-monospace, monospace; font-size: 11px; background: #f6f8fa; padding: 1px 4px; border-radius: 3px; }
.lane { display: inline-block; padding: 1px 6px; border-radius: 4px; font-size: 10px; font-weight: 600; margin-right: 4px; }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
table th, table td { text-align: left; padding: 4px 8px; border-bottom: 1px solid #eaeef2; }
table th { background: #f6f8fa; font-weight: 600; }
.q-list { font-family: ui-monospace, monospace; font-size: 11px; color: #57606a; max-height: 120px; overflow: auto; }
.summary-table th, .summary-table td { font-size: 12px; }
.bar { background: #d0d7de; height: 6px; border-radius: 3px; overflow: hidden; margin-top: 2px; }
.bar > div { height: 100%; background: #0969da; }
.bar > .red { background: #cf222e; }
.note-block { background: #f6f8fa; border-radius: 4px; padding: 8px; font-size: 12px; color: #57606a; line-height: 1.5; }
.kbd { font-family: ui-monospace, monospace; background: #eaeef2; padding: 1px 5px; border-radius: 3px; font-size: 11px; }
"""


def _h(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_column(td: TraceData | None, label: str, scen: Scenario, ro_text: str = "") -> str:
    if td is None or not td.trace_id:
        # RO column or missing trace
        body = f'<div class="note-block">{_h(ro_text) or "(no trace)"}</div>'
        return f'<div class="col"><h4>{_h(label)}</h4>{body}</div>'

    trace_url = f"{LF_HOST}/project/{LF_PROJECT}/traces/{td.trace_id}" if LF_PROJECT else ""

    if td.error:
        return f'<div class="col"><h4>{_h(label)}</h4><div class="flag bad">Error: {_h(td.error)}</div></div>'

    misroute = detect_misroute(td, scen.expected_part, scen.suspected_misroute_to)
    guidance = detect_agent_guidance_gap(td)
    irrelevant = detect_irrelevant_pulls(td, scen.expected_part)

    surfaced = td.total_candidates
    unique = td.unique_basenames
    dupes = sum(1 for c in td.duplicate_basenames.values() if c > 1)
    cross_dupes = len(td.cross_prefix_dupes)

    parts: list[str] = []
    parts.append(f'<div class="col"><h4>{_h(label)} <span style="float:right;font-weight:normal">'
                 f'<a href="{_h(trace_url)}" target="_blank">trace ↗</a></span></h4>')
    parts.append(f'<div style="font-size:10px;color:#8c959f;margin-bottom:8px">env={_h(td.env)} · '
                 f'{_h(td.timestamp[:19])}</div>')

    # Search layer
    parts.append('<h3>Search</h3>')
    parts.append(f'<div class="metric"><span>research calls</span><span class="v">{len(td.research_calls)}</span></div>')
    parts.append(f'<div class="metric"><span>candidates surfaced</span><span class="v">{surfaced}</span></div>')
    parts.append(f'<div class="metric"><span>unique basenames</span><span class="v">{unique}</span></div>')
    parts.append(f'<div class="metric"><span>same-basename dupes</span><span class="v">{dupes}</span></div>')
    parts.append(f'<div class="metric"><span>cross-prefix dupes</span><span class="v">{cross_dupes}</span></div>')

    # Rank layer
    parts.append('<h3>Rank — Part attribution mix</h3>')
    parts.append(
        f'<div class="metric"><span>FAR Part 15 hits</span><span class="v">{misroute["p15"]} ({misroute["part15_pct"]}%)</span></div>'
        f'<div class="bar"><div class="red" style="width:{misroute["part15_pct"]}%"></div></div>'
    )
    parts.append(
        f'<div class="metric"><span>FAR Part 6 hits</span><span class="v">{misroute["p6"]} ({misroute["part6_pct"]}%)</span></div>'
        f'<div class="bar"><div style="width:{misroute["part6_pct"]}%"></div></div>'
    )
    parts.append(
        f'<div class="metric"><span>FAR Part 13 hits</span><span class="v">{misroute["p13"]} ({misroute["part13_pct"]}%)</span></div>'
        f'<div class="bar"><div style="width:{misroute["part13_pct"]}%"></div></div>'
    )

    # Read layer
    fetched = len(td.s3_doc_ops)
    denied = td.permission_denied_count
    parts.append('<h3>Read</h3>')
    parts.append(f'<div class="metric"><span>s3 fetches issued</span><span class="v">{fetched}</span></div>')
    parts.append(f'<div class="metric"><span>permission denied</span><span class="v">{denied}</span></div>')
    parts.append(f'<div class="metric"><span>search_far calls</span><span class="v">{td.search_far_calls}</span></div>')

    eff = round(100 * fetched / max(surfaced, 1))
    parts.append(f'<div class="metric"><span>read efficiency</span><span class="v">{eff}% ({fetched}/{surfaced})</span></div>')

    # Specialist guidance
    parts.append('<h3>Specialist guidance</h3>')
    if guidance["gap"]:
        parts.append(f'<div class="flag bad">❌ <b>agent_guidance absent in all {guidance["calls"]} research calls</b> — '
                     f'supervisor answered without specialist framework</div>')
    else:
        parts.append(f'<div class="flag ok">✓ agent_guidance present in {guidance["with_guidance"]}/{guidance["calls"]} calls</div>')

    # Misroute
    if scen.suspected_misroute_to and misroute["misroute_detected"]:
        parts.append(f'<div class="flag bad">❌ <b>Part-15 misroute detected</b>: {misroute["part15_pct"]}% Part-15 hits '
                     f'vs {misroute["part6_pct"]}% Part-6 (expected: {_h(scen.expected_part)})</div>')

    # Cross-prefix dupes (KB sync gap evidence)
    if td.cross_prefix_dupes:
        parts.append('<h3>Cross-prefix duplicates (KB sync issue)</h3>')
        for bn, paths in list(td.cross_prefix_dupes.items())[:5]:
            paths_html = "<br>".join(f'<span class="code">{_h(p)}</span>' for p in paths)
            parts.append(f'<div class="flag">⚠ <b>{_h(bn)}</b><br>{paths_html}</div>')

    # Irrelevant pulls
    if irrelevant:
        parts.append('<h3>Likely irrelevant pulls</h3>')
        for fl in irrelevant[:8]:
            parts.append(f'<div class="flag">{_h(fl)}</div>')

    # Permission denials detail
    if td.permission_denied_count:
        parts.append('<h3>Permission denials (IAM gap)</h3>')
        for op in td.s3_doc_ops:
            if op["denied"]:
                parts.append(f'<div class="flag bad">❌ {_h(op["input"])}<br>'
                             f'<span class="code">{_h(op["output_preview"])[:160]}</span></div>')

    # Research queries (compact)
    if td.research_calls:
        parts.append('<h3>Research queries (compact)</h3>')
        parts.append('<div class="q-list">')
        for c in td.research_calls:
            q_short = c.query[:140] + ("…" if len(c.query) > 140 else "")
            parts.append(f'<div>• <span class="code">{_h(q_short)}</span> → {len(c.s3_keys)} hits</div>')
        parts.append('</div>')

    parts.append('</div>')
    return "\n".join(parts)


def render_summary_row(scen: Scenario, dev: TraceData | None, qa: TraceData | None) -> str:
    def cell(td: TraceData | None) -> str:
        if not td or not td.trace_id:
            return "—"
        misroute = detect_misroute(td, scen.expected_part, scen.suspected_misroute_to)
        guidance = detect_agent_guidance_gap(td)
        flags: list[str] = []
        if guidance["gap"]:
            flags.append("⚠ no agent_guidance")
        if scen.suspected_misroute_to and misroute["misroute_detected"]:
            flags.append("⚠ misroute")
        if td.cross_prefix_dupes:
            flags.append(f"⚠ {len(td.cross_prefix_dupes)} cross-prefix dupes")
        if td.permission_denied_count:
            flags.append(f"⚠ {td.permission_denied_count} IAM denied")
        suff = "<br><small>" + " · ".join(flags) + "</small>" if flags else ""
        return f'{td.total_candidates} surf / {len(td.s3_doc_ops)} read{suff}'

    return (
        f'<tr><td><b>{_h(scen.label)}</b></td>'
        f'<td>{cell(dev)}</td>'
        f'<td>{cell(qa)}</td>'
        f'<td><small>{_h(scen.ro_notes[:200])}…</small></td></tr>'
    )


# ─── Main ─────────────────────────────────────────────────────────────────────

async def main() -> Path:
    if not LF_PUB or not LF_SEC:
        raise SystemExit("LANGFUSE_PUBLIC_KEY/SECRET_KEY missing in server/.env")

    async with httpx.AsyncClient(timeout=45) as client:
        results: list[tuple[Scenario, TraceData | None, TraceData | None]] = []
        for scen in SCENARIOS:
            dev_td = await fetch_trace(client, scen.dev_trace) if scen.dev_trace else None
            qa_td = await fetch_trace(client, scen.qa_trace) if scen.qa_trace else None
            results.append((scen, dev_td, qa_td))

    # Render
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    out_path = REPO_ROOT / "docs" / "development" / f"{ts}-report-retrieval-3layer-v1.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    sections: list[str] = []
    sections.append(f'<h1>EAGLE Retrieval 3-Layer Report</h1>')
    sections.append(f'<div class="meta">Generated {datetime.utcnow().isoformat()}Z · '
                    f'AWS account 695681773636 (NIH.NCI.CBIIT.EAGLE.NONPROD) · '
                    f'KB bucket <span class="kbd">eagle-knowledge-base</span></div>')

    # Summary table
    sections.append('<h2>Summary</h2>')
    sections.append('<table class="summary-table">'
                    '<tr><th>Question</th><th>Dev</th><th>QA</th><th>RO (manual)</th></tr>')
    for scen, dev_td, qa_td in results:
        sections.append(render_summary_row(scen, dev_td, qa_td))
    sections.append('</table>')

    # Top-level findings
    sections.append('<h2>Top-level findings</h2>')
    findings: list[str] = []
    # 1. agent_guidance gap — count traces with no guidance
    no_guidance = sum(
        1 for _, d, q in results
        for td in (d, q) if td and td.research_calls and detect_agent_guidance_gap(td)["gap"]
    )
    total_traces = sum(1 for _, d, q in results for td in (d, q) if td and td.research_calls)
    findings.append(
        f'<div class="flag bad">❌ <b>agent_guidance never loaded in {no_guidance}/{total_traces} traces</b> — '
        f'supervisor was operating without specialist framework on every analyzed question. '
        f'Fix: expand keyword table at <span class="kbd">strands_agentic_service.py:4671-4679</span> '
        f'(compliance-strategist) and <span class="kbd">:4613-4622</span> (legal-counsel) to include '
        f'<span class="kbd">jefo</span>, <span class="kbd">fair opportunity</span>, <span class="kbd">sbir</span>, '
        f'<span class="kbd">debriefing</span>, <span class="kbd">idiq</span>, <span class="kbd">16.505</span>, '
        f'<span class="kbd">16.507</span>.</div>'
    )
    # 2. Q5 part-15 misroute
    findings.append(
        '<div class="flag bad">❌ <b>Q5 Part-15 misroute confirmed</b> — agent generated research keyword '
        '<span class="code">"debriefing preaward 15.505 postaward 15.506..."</span> '
        '<i>before</i> any KB lookup. The Part-15 vocabulary in the user\'s question (debriefing/protest/'
        'eliminated offeror) anchored the agent on Part 15, even though SBIR is FAR 6.102(d). '
        'Fix: <b>shortcut at intake</b> — detect SBIR / R&D / R&amp;D phrases in the user message '
        'and force <span class="kbd">acquisition_method="sbir"</span> + force-load '
        '<span class="kbd">compliance-strategist</span> + <span class="kbd">legal-counsel</span> '
        'BEFORE the supervisor crafts a research query.</div>'
    )
    # 3. KB IAM gap
    findings.append(
        '<div class="flag bad">❌ <b>Agent cannot list <span class="kbd">eagle-knowledge-base</span> from inside</b> — '
        '<span class="code">s3_document_ops list eagle-knowledge-base</span> returns "AWS permission denied" '
        '(see KB inventory probe trace). The agent fell back to listing <span class="kbd">eagle-documents-695681773636-dev</span> '
        '(user-doc bucket, returned 0 files). Fix: grant the ECS task role <span class="kbd">s3:ListBucket</span> on the KB bucket '
        '— affects both Dev and QA based on the KB inventory probe.</div>'
    )
    # 4. Read efficiency
    findings.append(
        '<div class="flag">⚠ <b>Search-to-read ratio is low</b> across all questions — typically 30+ candidates surfaced, '
        '3–6 read. This is expected and HEALTHY (Search casts wide, Read narrows) per the 3-layer model. '
        'The concern is not the surfaced count — it\'s when Rank fails to put the RIGHT 6 in the read slots. '
        'See per-question detail below.</div>'
    )
    # 5. Updated KB instructions context
    findings.append(
        '<div class="flag">ℹ <b>"S3 bucket with updated instructions"</b> — the KB inventory probe '
        '(2026-04-29 13:59 UTC) couldn\'t directly list the bucket due to the IAM gap above, so the agent '
        'reconstructed inventory from prior research results. The single bucket referenced is '
        '<span class="kbd">eagle-knowledge-base</span> (account 695681773636). If a separate "new instructions" '
        'bucket exists outside this trace stream, it has not yet been queried by the agent — recommend confirming '
        'with Brian/team and adding it to <span class="kbd">_AGENTS_FOLDER_PREFIX</span> in '
        '<span class="kbd">strands_agentic_service.py:4598</span> if so.</div>'
    )
    sections.append("".join(findings))

    # Per-scenario detail
    sections.append('<h2>Per-question detail</h2>')
    for scen, dev_td, qa_td in results:
        sections.append('<div class="scenario">')
        sections.append(f'<h2>{_h(scen.label)}</h2>')
        sections.append(f'<div class="q">{_h(scen.question)}</div>')
        sections.append(f'<div style="font-size:12px;color:#57606a;margin-bottom:8px">'
                        f'Expected: <b>{_h(scen.expected_part)}</b>'
                        + (f' · Suspected misroute → <b>{_h(scen.suspected_misroute_to)}</b>'
                           if scen.suspected_misroute_to else '') + '</div>')
        sections.append('<div class="cols">')
        sections.append(render_column(dev_td, "Dev", scen))
        sections.append(render_column(qa_td, "QA", scen))
        sections.append(render_column(None, "RO (manual notes)", scen, ro_text=scen.ro_notes))
        sections.append('</div></div>')

    # Recommendations
    sections.append('<h2>Recommendations (PR order)</h2>')
    sections.append('<ol>')
    sections.append('<li><b>PR1 — agent_guidance keyword expansion</b> (closes Q4 + Q5 root cause): '
                    'add <span class="kbd">jefo</span>, <span class="kbd">fair opportunity</span>, '
                    '<span class="kbd">sbir</span>, <span class="kbd">debriefing</span>, '
                    '<span class="kbd">idiq</span>, <span class="kbd">16.505</span>, <span class="kbd">16.507</span> '
                    'to compliance-strategist and legal-counsel keyword tables in '
                    '<span class="kbd">strands_agentic_service.py:4671-4679, :4613-4622</span>. '
                    'Bump fetch failures from WARNING to ERROR + emit visible <span class="kbd">agent_route_error</span> '
                    'SSE card.</li>')
    sections.append('<li><b>PR2 — Pre-research method shortcut for SBIR / Part-vocabulary mismatch</b> '
                    '(closes Q5 misroute): in the supervisor agent prompt, add an intake-stage classifier '
                    'block that, BEFORE calling <span class="kbd">research</span>, scans the user message for '
                    'SBIR / "Phase I/II" / "STTR" / "BAA" patterns. If matched, force '
                    '<span class="kbd">acquisition_method=sbir</span> in the research call and explicitly '
                    'append "FAR 6.102(d), GAO 10-day timeliness rule" to the keyword. This pre-empts the '
                    'Part-15-shaped vocabulary problem at source.</li>')
    sections.append('<li><b>PR3 — KB list IAM grant</b>: add <span class="kbd">s3:ListBucket</span> + '
                    '<span class="kbd">s3:GetObject</span> on <span class="kbd">eagle-knowledge-base</span> '
                    'to the ECS task role in <span class="kbd">infrastructure/cdk-eagle/lib/core-stack.ts</span>. '
                    'Required for any KB-inventory diagnostic skill (Jitong\'s "ask the prompt what\'s in the KB" check).</li>')
    sections.append('<li><b>PR4 — JEFO 10-element enforcement</b>: add forcing line to '
                    '<span class="kbd">eagle-plugin/agents/compliance-strategist/agent.md</span> for FAR 16.507-6(d)(2). '
                    'Already in <span class="kbd">.claude/specs/20260429-102357-plan-q4-uc21-coworker-feedback-triage-v1.md</span>.</li>')
    sections.append('<li><b>PR5 — Method-aware doc filter</b>: drop protest/J&A docs from research results when '
                    '<span class="kbd">acquisition_method=micro_purchase</span>. Same spec.</li>')
    sections.append('</ol>')

    html = (
        f'<!DOCTYPE html><html><head><meta charset="utf-8">'
        f'<title>EAGLE Retrieval 3-Layer Report</title>'
        f'<style>{CSS}</style></head><body><div class="wrap">'
        + "\n".join(sections)
        + '</div></body></html>'
    )
    out_path.write_text(html, encoding="utf-8")
    print(f"Wrote {out_path}")
    return out_path


if __name__ == "__main__":
    asyncio.run(main())
