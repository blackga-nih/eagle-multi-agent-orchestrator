"""Generate an HTML baseline comparison report: EAGLE vN vs Research Optimizer.

Reads the baseline JSON results file and produces a visual HTML report showing:
- Score comparison (EAGLE vs RO as gold standard)
- Document retrieval pills for both systems
- Tool call badges for EAGLE
- Side-by-side response comparison
- KB coverage analysis

Usage:
    python generate_report.py --version v8 [--json PATH] [--output PATH]
"""
import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from html import escape

sys.stdout.reconfigure(encoding="utf-8")

# ── Question metadata ────────────────────────────────────────────────
QUESTION_META = {
    1: {"category": "Threshold", "short": "MPT and SAT under FAC 2025-06"},
    2: {"category": "Case Law", "short": "GAO B-302358 IDIQ minimum obligation"},
    3: {"category": "Appropriations", "short": "Severable vs non-severable funding"},
    4: {"category": "IDIQ", "short": "Fair opportunity exceptions (FAR 16.505)"},
    5: {"category": "Protest", "short": "SBIR elimination + debriefing + protest"},
    6: {"category": "Design", "short": "Acquisition workflow UX sequencing"},
    7: {"category": "Sole Source", "short": "Sole-source $280K software maintenance"},
    8: {"category": "Threshold+", "short": "SAT/MPT + NIH-specific policies"},
    9: {"category": "Case Law+", "short": "GAO B-302358 with KB search"},
    10: {"category": "Appropriations+", "short": "Bona fide needs + severable/non-severable"},
    11: {"category": "IDIQ+", "short": "Fair opportunity exceptions (enhanced)"},
    12: {"category": "Protest+", "short": "SBIR Phase II GAO protest + KB search"},
    13: {"category": "Document Gen", "short": "SOW generation for IT help desk"},
}

# Fallback question text (used if JSON doesn't include 'question' field)
QUESTION_TEXT: dict[int, str] = {}

TOOL_COLORS = {
    "query_compliance_matrix": ("#1565C0", "#E3F2FD"),
    "knowledge_search": ("#2E7D32", "#E8F5E9"),
    "knowledge_fetch": ("#1B5E20", "#C8E6C9"),
    "search_far": ("#6A1B9A", "#F3E5F5"),
    "research": ("#E65100", "#FFF3E0"),
    "legal_counsel": ("#AD1457", "#FCE4EC"),
    "web_search": ("#00838F", "#E0F7FA"),
    "web_fetch": ("#006064", "#B2EBF2"),
    "load_skill": ("#795548", "#EFEBE9"),
    "create_document": ("#37474F", "#ECEFF1"),
}

DOC_TYPE_COLORS = {
    "compliance-strategist": ("#1565C0", "#E3F2FD", "Compliance"),
    "legal-counselor": ("#AD1457", "#FCE4EC", "Legal"),
    "financial-advisor": ("#2E7D32", "#E8F5E9", "Financial"),
    "market-researcher": ("#E65100", "#FFF3E0", "Market"),
    "document-drafter": ("#6A1B9A", "#F3E5F5", "Drafting"),
    "supervisor-core": ("#37474F", "#ECEFF1", "Core"),
    "agents": ("#795548", "#EFEBE9", "Agents"),
}


def parse_ro_docs(ro_text: str) -> list[dict]:
    """Parse document references from RO response text.

    RO format: lines like 'path/to/file.txt' followed by 'NNNN chars'
    """
    docs = []
    lines = ro_text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        # Match KB-style paths (agent/category/file.txt)
        if re.match(r"^[\w-]+/[\w-]+/[\w._-]+\.\w+$", line):
            chars = 0
            if i + 1 < len(lines):
                m = re.match(r"^(\d+)\s+chars?", lines[i + 1].strip())
                if m:
                    chars = int(m.group(1))
                    i += 1
            docs.append({"path": line, "chars": chars})
        # Also match inline references like "exists at path/to/file.txt"
        elif "exists at " in line:
            m = re.search(r"exists at ([\w-]+/[\w-]+/[\w._-]+\.\w+)", line)
            if m:
                docs.append({"path": m.group(1), "chars": 0})
        i += 1
    return docs


def parse_eagle_docs(response: str) -> list[dict]:
    """Parse KB document references from EAGLE response text."""
    docs = []
    seen = set()
    # eagle-knowledge-base/approved/agent/category/file.txt
    for m in re.finditer(r"eagle-knowledge-base/approved/([\w-]+/[\w-]+/[\w._-]+\.\w+)", response):
        path = m.group(1).rstrip("`")
        if path not in seen:
            seen.add(path)
            docs.append({"path": path, "chars": 0})
    return docs


def parse_ro_response_body(ro_text: str) -> str:
    """Extract the actual response content from RO text (skip doc refs and 'Reasoning...' markers)."""
    lines = ro_text.split("\n")
    body_start = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        # Skip doc ref lines and char count lines
        if re.match(r"^[\w-]+/[\w-]+/[\w._-]+\.\w+$", stripped):
            body_start = i + 1
            continue
        if re.match(r"^\d+\s+chars?$", stripped):
            body_start = i + 1
            continue
        if stripped in ("Reasoning...", "Reasoning\u2026", "think", ""):
            body_start = i + 1
            continue
        if "exists at " in stripped and re.search(r"[\w-]+/[\w-]+/[\w._-]+\.\w+", stripped):
            body_start = i + 1
            continue
        if stripped.startswith("Let me pull"):
            body_start = i + 1
            continue
        break
    return "\n".join(lines[body_start:]).strip()


def doc_agent_label(path: str) -> tuple[str, str, str]:
    """Return (label, text_color, bg_color) for a doc path based on the agent prefix."""
    for prefix, (text, bg, label) in DOC_TYPE_COLORS.items():
        if path.startswith(prefix):
            return label, text, bg
    return "KB", "#424242", "#F5F5F5"


def doc_filename(path: str) -> str:
    """Extract just the filename from a KB path."""
    return path.rsplit("/", 1)[-1] if "/" in path else path


def build_html(results: dict, version: str, scores: dict | None = None,
               eagle_prompt: str = "", ro_prompt: str = "") -> str:
    """Build the full HTML report."""
    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    version_upper = version.upper() if not version[0].isupper() else version

    # Normalize scores keys to int for lookup
    if scores:
        scores = {int(k): v for k, v in scores.items()}

    # Aggregate stats
    total_eagle_docs = 0
    total_ro_docs = 0
    total_eagle_chars = 0
    total_ro_chars = 0
    all_tools = set()

    questions_html = []
    row_keys = sorted(results.keys(), key=lambda x: int(x))
    for row_str in row_keys:
        r = results[row_str]
        q_num = r["q_num"]
        meta = QUESTION_META.get(q_num, {"category": "?", "short": "?"})
        tools = r.get("tools", [])
        ro_text = r.get("ro_response", "")

        eagle_docs = parse_eagle_docs(r["response"])
        ro_docs = parse_ro_docs(ro_text)
        ro_body = parse_ro_response_body(ro_text)

        total_eagle_docs += len(eagle_docs)
        total_ro_docs += len(ro_docs)
        total_ro_chars += sum(d["chars"] for d in ro_docs)
        all_tools.update(tools)

        # Score data
        sc = scores.get(q_num, {}) if scores else {}

        # Build tool pills
        tool_pills = ""
        for t in tools:
            tc, bg = TOOL_COLORS.get(t, ("#424242", "#F5F5F5"))
            tool_pills += f'<span class="pill" style="background:{bg};color:{tc};border:1px solid {tc}22">{escape(t)}</span>\n'
        if not tools:
            tool_pills = '<span class="pill" style="background:#F5F5F5;color:#9E9E9E;border:1px solid #E0E0E0">no tools</span>'

        # Build EAGLE doc pills
        eagle_doc_pills = ""
        for d in eagle_docs:
            label, tc, bg = doc_agent_label(d["path"])
            fname = doc_filename(d["path"])
            eagle_doc_pills += (
                f'<div class="doc-row">'
                f'<span class="doc-badge" style="background:{bg};color:{tc}">{escape(label)}</span>'
                f'<span class="doc-name" title="{escape(d["path"])}">{escape(fname)}</span>'
                f'</div>\n'
            )
        if not eagle_docs:
            eagle_doc_pills = '<div class="doc-empty">No KB documents read</div>'

        # Build RO doc pills
        ro_doc_pills = ""
        for d in ro_docs:
            label, tc, bg = doc_agent_label(d["path"])
            fname = doc_filename(d["path"])
            chars_label = f' <span class="doc-chars">{d["chars"]:,} chars</span>' if d["chars"] else ""
            ro_doc_pills += (
                f'<div class="doc-row">'
                f'<span class="doc-badge" style="background:{bg};color:{tc}">{escape(label)}</span>'
                f'<span class="doc-name" title="{escape(d["path"])}">{escape(fname)}</span>'
                f'{chars_label}'
                f'</div>\n'
            )
        if not ro_docs:
            ro_doc_pills = '<div class="doc-empty">No KB documents referenced</div>'

        # Score display
        score_html = ""
        if sc:
            total = sc.get("total", 0)
            color = "#2E7D32" if total >= 19 else "#E65100" if total >= 16 else "#C62828"
            score_html = f"""
            <div class="score-grid">
                <div class="score-item"><div class="score-val">{sc.get('acc','—')}</div><div class="score-label">Accuracy</div></div>
                <div class="score-item"><div class="score-val">{sc.get('comp','—')}</div><div class="score-label">Completeness</div></div>
                <div class="score-item"><div class="score-val">{sc.get('src','—')}</div><div class="score-label">Sources</div></div>
                <div class="score-item"><div class="score-val">{sc.get('act','—')}</div><div class="score-label">Actionability</div></div>
                <div class="score-total" style="color:{color}"><span class="score-big">{total}</span>/20</div>
            </div>
            """
            if sc.get("verdict"):
                vclass = "verdict-win" if "> RO" in sc["verdict"] else "verdict-tie" if "= RO" in sc["verdict"] else "verdict-loss"
                score_html += f'<div class="verdict {vclass}">{escape(sc["verdict"])}</div>'

        # Doc count comparison
        eagle_doc_count = len(eagle_docs)
        ro_doc_count = len(ro_docs)
        doc_delta = eagle_doc_count - ro_doc_count
        delta_class = "delta-pos" if doc_delta > 0 else "delta-neg" if doc_delta < 0 else "delta-zero"
        delta_str = f"+{doc_delta}" if doc_delta > 0 else str(doc_delta)

        # Response lengths
        eagle_len = len(r["response"])
        ro_len = len(ro_text)

        # Get question text from JSON or fallback
        question_text = r.get("question", QUESTION_TEXT.get(q_num, ""))

        questions_html.append(f"""
        <div class="question-card">
            <div class="q-header">
                <div class="q-num">Q{q_num}</div>
                <div class="q-meta">
                    <span class="q-category">{escape(meta['category'])}</span>
                    <span class="q-title">{escape(meta['short'])}</span>
                </div>
                <div class="q-time">{r.get('elapsed_s', 0):.0f}s</div>
            </div>

            <div class="q-text">{escape(question_text)}</div>

            {score_html}

            <div class="section-label">EAGLE {version_upper} Tools</div>
            <div class="pills-row">{tool_pills}</div>

            <div class="docs-compare">
                <div class="docs-col">
                    <div class="docs-header">
                        <span class="docs-system eagle-label">EAGLE {version_upper}</span>
                        <span class="docs-count">{eagle_doc_count} doc{'s' if eagle_doc_count != 1 else ''} read</span>
                    </div>
                    <div class="docs-list">{eagle_doc_pills}</div>
                </div>
                <div class="docs-col">
                    <div class="docs-header">
                        <span class="docs-system ro-label">Research Optimizer</span>
                        <span class="docs-count">{ro_doc_count} doc{'s' if ro_doc_count != 1 else ''} read</span>
                    </div>
                    <div class="docs-list">{ro_doc_pills}</div>
                </div>
            </div>

            <div class="docs-delta {delta_class}">
                Doc delta: {delta_str} &nbsp;|&nbsp; EAGLE {eagle_len:,} chars &nbsp;|&nbsp; RO {ro_len:,} chars
            </div>

            <details class="response-toggle">
                <summary>View Responses</summary>
                <div class="responses-grid">
                    <div class="resp-col">
                        <div class="resp-label eagle-label">EAGLE {version_upper}</div>
                        <div class="resp-text">{escape(r['response'][:3000])}{'...' if len(r['response']) > 3000 else ''}</div>
                    </div>
                    <div class="resp-col">
                        <div class="resp-label ro-label">Research Optimizer</div>
                        <div class="resp-text">{escape(ro_body[:3000])}{'...' if len(ro_body) > 3000 else ''}</div>
                    </div>
                </div>
            </details>
        </div>
        """)

    # Summary stats
    total_score = sum(s.get("total", 0) for s in (scores or {}).values())
    max_score = len(scores or {}) * 20
    wins = sum(1 for s in (scores or {}).values() if "> RO" in s.get("verdict", ""))
    ties = sum(1 for s in (scores or {}).values() if "= RO" in s.get("verdict", ""))
    losses = sum(1 for s in (scores or {}).values() if "< RO" in s.get("verdict", ""))

    # Build score summary row for the top
    score_summary_items = ""
    if scores:
        for q in sorted(scores.keys()):
            sc = scores[q]
            total = sc.get("total", 0)
            color = "#2E7D32" if total >= 19 else "#E65100" if total >= 16 else "#C62828"
            score_summary_items += f'<div class="summary-q"><div class="summary-q-num">Q{q}</div><div class="summary-q-score" style="color:{color}">{total}/20</div></div>'

    # Unique docs across all questions
    all_eagle_docs = set()
    all_ro_docs = set()
    for row_str in row_keys:
        r = results[row_str]
        for d in parse_eagle_docs(r["response"]):
            all_eagle_docs.add(d["path"])
        for d in parse_ro_docs(r.get("ro_response", "")):
            all_ro_docs.add(d["path"])

    # Shared docs
    shared = all_eagle_docs & all_ro_docs
    eagle_only = all_eagle_docs - all_ro_docs
    ro_only = all_ro_docs - all_eagle_docs

    coverage_html = ""
    if shared:
        pills = "".join(
            f'<span class="pill coverage-shared" title="{escape(p)}">{escape(doc_filename(p))}</span>'
            for p in sorted(shared)
        )
        coverage_html += f'<div class="coverage-section"><div class="coverage-label shared-label">Both Systems ({len(shared)})</div><div class="pills-wrap">{pills}</div></div>'
    if eagle_only:
        pills = "".join(
            f'<span class="pill coverage-eagle" title="{escape(p)}">{escape(doc_filename(p))}</span>'
            for p in sorted(eagle_only)
        )
        coverage_html += f'<div class="coverage-section"><div class="coverage-label eagle-only-label">EAGLE Only ({len(eagle_only)})</div><div class="pills-wrap">{pills}</div></div>'
    if ro_only:
        pills = "".join(
            f'<span class="pill coverage-ro" title="{escape(p)}">{escape(doc_filename(p))}</span>'
            for p in sorted(ro_only)
        )
        coverage_html += f'<div class="coverage-section"><div class="coverage-label ro-only-label">RO Only ({len(ro_only)})</div><div class="pills-wrap">{pills}</div></div>'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>EAGLE {version_upper} Baseline Report</title>
<style>
:root {{
    --navy: #003366;
    --eagle-blue: #1565C0;
    --eagle-bg: #E3F2FD;
    --ro-purple: #6A1B9A;
    --ro-bg: #F3E5F5;
    --green: #2E7D32;
    --orange: #E65100;
    --red: #C62828;
    --gray-50: #FAFAFA;
    --gray-100: #F5F5F5;
    --gray-200: #EEEEEE;
    --gray-300: #E0E0E0;
    --gray-500: #9E9E9E;
    --gray-700: #616161;
    --gray-900: #212121;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: var(--gray-50); color: var(--gray-900); line-height: 1.5; }}

.header {{ background: var(--navy); color: white; padding: 32px 40px; }}
.header h1 {{ font-size: 24px; font-weight: 600; margin-bottom: 4px; }}
.header .subtitle {{ font-size: 14px; opacity: 0.8; }}

.container {{ max-width: 1200px; margin: 0 auto; padding: 24px 20px; }}

/* Summary bar */
.summary-bar {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 16px; margin-bottom: 32px; }}
.summary-card {{ background: white; border-radius: 12px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); text-align: center; }}
.summary-card .big {{ font-size: 32px; font-weight: 700; }}
.summary-card .label {{ font-size: 12px; color: var(--gray-500); text-transform: uppercase; letter-spacing: 0.5px; margin-top: 4px; }}
.summary-card.wins .big {{ color: var(--green); }}
.summary-card.ties .big {{ color: var(--eagle-blue); }}
.summary-card.losses .big {{ color: var(--red); }}

/* Score summary strip */
.score-strip {{ display: flex; gap: 12px; justify-content: center; margin-bottom: 32px; flex-wrap: wrap; }}
.summary-q {{ background: white; border-radius: 10px; padding: 12px 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); text-align: center; min-width: 80px; }}
.summary-q-num {{ font-size: 11px; color: var(--gray-500); text-transform: uppercase; letter-spacing: 0.5px; }}
.summary-q-score {{ font-size: 20px; font-weight: 700; }}

/* Question cards */
.question-card {{ background: white; border-radius: 12px; padding: 24px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
.q-header {{ display: flex; align-items: center; gap: 16px; margin-bottom: 16px; }}
.q-num {{ font-size: 18px; font-weight: 700; color: var(--navy); background: #E8EAF6; border-radius: 8px; padding: 4px 12px; flex-shrink: 0; }}
.q-meta {{ flex: 1; }}
.q-category {{ display: inline-block; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; color: var(--eagle-blue); background: var(--eagle-bg); padding: 2px 8px; border-radius: 4px; margin-right: 8px; }}
.q-title {{ font-size: 14px; color: var(--gray-700); }}
.q-time {{ font-size: 13px; color: var(--gray-500); font-variant-numeric: tabular-nums; }}
.q-text {{ font-size: 13px; color: var(--gray-700); background: var(--gray-100); border-left: 3px solid var(--navy); padding: 10px 14px; border-radius: 0 6px 6px 0; margin-bottom: 16px; line-height: 1.5; }}

/* Score grid */
.score-grid {{ display: flex; align-items: center; gap: 16px; margin-bottom: 16px; padding: 12px 16px; background: var(--gray-50); border-radius: 8px; flex-wrap: wrap; }}
.score-item {{ text-align: center; min-width: 60px; }}
.score-val {{ font-size: 20px; font-weight: 700; color: var(--navy); }}
.score-label {{ font-size: 10px; color: var(--gray-500); text-transform: uppercase; letter-spacing: 0.5px; }}
.score-total {{ margin-left: auto; text-align: center; }}
.score-big {{ font-size: 28px; font-weight: 800; }}
.verdict {{ font-size: 13px; font-weight: 600; padding: 6px 12px; border-radius: 6px; margin-bottom: 16px; display: inline-block; }}
.verdict-win {{ background: #E8F5E9; color: var(--green); }}
.verdict-tie {{ background: var(--eagle-bg); color: var(--eagle-blue); }}
.verdict-loss {{ background: #FFEBEE; color: var(--red); }}

/* Pills */
.pill {{ display: inline-block; font-size: 12px; font-weight: 500; padding: 3px 10px; border-radius: 20px; margin: 2px 4px 2px 0; white-space: nowrap; }}
.pills-row {{ margin-bottom: 16px; }}
.pills-wrap {{ display: flex; flex-wrap: wrap; gap: 4px; }}
.section-label {{ font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; color: var(--gray-500); margin-bottom: 6px; }}

/* Docs comparison */
.docs-compare {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 12px; }}
@media (max-width: 768px) {{ .docs-compare {{ grid-template-columns: 1fr; }} }}
.docs-col {{ background: var(--gray-50); border-radius: 8px; padding: 12px; }}
.docs-header {{ display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }}
.docs-system {{ font-size: 12px; font-weight: 700; padding: 3px 10px; border-radius: 6px; }}
.eagle-label {{ background: var(--eagle-bg); color: var(--eagle-blue); }}
.ro-label {{ background: var(--ro-bg); color: var(--ro-purple); }}
.docs-count {{ font-size: 11px; color: var(--gray-500); }}
.docs-list {{ display: flex; flex-direction: column; gap: 4px; }}
.doc-row {{ display: flex; align-items: center; gap: 6px; font-size: 12px; }}
.doc-badge {{ font-size: 10px; font-weight: 600; padding: 2px 6px; border-radius: 4px; flex-shrink: 0; }}
.doc-name {{ color: var(--gray-700); font-family: 'SF Mono', 'Fira Code', monospace; font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.doc-chars {{ font-size: 10px; color: var(--gray-500); flex-shrink: 0; }}
.doc-empty {{ font-size: 12px; color: var(--gray-500); font-style: italic; padding: 4px 0; }}

.docs-delta {{ font-size: 11px; padding: 6px 12px; border-radius: 6px; margin-bottom: 12px; text-align: center; }}
.delta-pos {{ background: #E8F5E9; color: var(--green); }}
.delta-neg {{ background: #FFEBEE; color: var(--red); }}
.delta-zero {{ background: var(--gray-100); color: var(--gray-500); }}

/* Response toggle */
.response-toggle {{ margin-top: 8px; }}
.response-toggle summary {{ font-size: 13px; color: var(--eagle-blue); cursor: pointer; font-weight: 500; padding: 6px 0; }}
.response-toggle summary:hover {{ text-decoration: underline; }}
.responses-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 12px; }}
@media (max-width: 768px) {{ .responses-grid {{ grid-template-columns: 1fr; }} }}
.resp-col {{ background: var(--gray-50); border-radius: 8px; padding: 12px; }}
.resp-label {{ font-size: 12px; font-weight: 700; padding: 3px 10px; border-radius: 6px; display: inline-block; margin-bottom: 8px; }}
.resp-text {{ font-size: 12px; color: var(--gray-700); white-space: pre-wrap; word-wrap: break-word; max-height: 400px; overflow-y: auto; line-height: 1.6; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}

/* KB Coverage section */
.coverage-card {{ background: white; border-radius: 12px; padding: 24px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
.coverage-card h2 {{ font-size: 16px; color: var(--navy); margin-bottom: 16px; }}
.coverage-section {{ margin-bottom: 16px; }}
.coverage-label {{ font-size: 12px; font-weight: 600; margin-bottom: 6px; }}
.shared-label {{ color: var(--green); }}
.eagle-only-label {{ color: var(--eagle-blue); }}
.ro-only-label {{ color: var(--ro-purple); }}
.coverage-shared {{ background: #E8F5E9; color: var(--green); border: 1px solid #C8E6C9; }}
.coverage-eagle {{ background: var(--eagle-bg); color: var(--eagle-blue); border: 1px solid #BBDEFB; }}
.coverage-ro {{ background: var(--ro-bg); color: var(--ro-purple); border: 1px solid #CE93D8; }}

/* System prompts */
.prompts-card {{ background: white; border-radius: 12px; padding: 24px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
.prompts-card h2 {{ font-size: 16px; color: var(--navy); margin-bottom: 16px; }}
.prompts-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
@media (max-width: 768px) {{ .prompts-grid {{ grid-template-columns: 1fr; }} }}
.prompt-col {{ background: var(--gray-50); border-radius: 8px; padding: 16px; }}
.prompt-col .resp-label {{ margin-bottom: 8px; }}
.prompt-text {{ font-size: 11px; color: var(--gray-700); white-space: pre-wrap; word-wrap: break-word; max-height: 500px; overflow-y: auto; line-height: 1.5; font-family: 'SF Mono', 'Fira Code', monospace; }}
.prompt-meta {{ display: flex; gap: 12px; font-size: 11px; color: var(--gray-500); margin-bottom: 12px; }}

.footer {{ text-align: center; padding: 24px; font-size: 12px; color: var(--gray-500); }}
</style>
</head>
<body>

<div class="header">
    <h1>EAGLE {version_upper} Baseline Evaluation</h1>
    <div class="subtitle">vs Research Optimizer (Gold Standard) &mdash; {today}</div>
</div>

<div class="container">

    <!-- Summary -->
    <div class="summary-bar">
        <div class="summary-card"><div class="big" style="color:var(--navy)">{total_score}/{max_score}</div><div class="label">Total Score</div></div>
        <div class="summary-card wins"><div class="big">{wins}</div><div class="label">EAGLE Wins</div></div>
        <div class="summary-card ties"><div class="big">{ties}</div><div class="label">Ties</div></div>
        <div class="summary-card losses"><div class="big">{losses}</div><div class="label">RO Wins</div></div>
        <div class="summary-card"><div class="big" style="color:var(--navy)">{total_eagle_docs}</div><div class="label">EAGLE Docs Read</div></div>
        <div class="summary-card"><div class="big" style="color:var(--ro-purple)">{total_ro_docs}</div><div class="label">RO Docs Read</div></div>
    </div>

    <!-- Per-Q scores strip -->
    <div class="score-strip">{score_summary_items}</div>

    <!-- KB Coverage -->
    <div class="coverage-card">
        <h2>Knowledge Base Coverage Comparison</h2>
        <p style="font-size:13px;color:var(--gray-700);margin-bottom:16px">
            Unique KB documents referenced across all {len(results)} questions.
            EAGLE {version_upper}: {len(all_eagle_docs)} unique &nbsp;|&nbsp;
            RO: {len(all_ro_docs)} unique &nbsp;|&nbsp;
            Shared: {len(shared)}
        </p>
        {coverage_html}
    </div>

    <!-- System Prompts -->
    {f'''<div class="prompts-card">
        <h2>Supervisor System Prompts</h2>
        <p style="font-size:13px;color:var(--gray-700);margin-bottom:16px">
            The system prompt given to each system's supervisor agent before processing queries.
        </p>
        <details class="response-toggle">
            <summary>View System Prompts ({len(eagle_prompt):,} chars EAGLE / {len(ro_prompt):,} chars RO)</summary>
            <div class="prompts-grid" style="margin-top:12px">
                <div class="prompt-col">
                    <div class="resp-label eagle-label">EAGLE {version_upper} Supervisor</div>
                    <div class="prompt-meta">{len(eagle_prompt):,} chars &bull; {len(eagle_prompt.splitlines())} lines</div>
                    <div class="prompt-text">{escape(eagle_prompt)}</div>
                </div>
                <div class="prompt-col">
                    <div class="resp-label ro-label">Research Optimizer Supervisor</div>
                    <div class="prompt-meta">{len(ro_prompt):,} chars &bull; {len(ro_prompt.splitlines())} lines</div>
                    <div class="prompt-text">{escape(ro_prompt)}</div>
                </div>
            </div>
        </details>
    </div>''' if eagle_prompt or ro_prompt else ''}

    <!-- Questions -->
    {"".join(questions_html)}

</div>

<div class="footer">
    EAGLE Baseline Report &mdash; Generated {today} &mdash; {len(results)} questions evaluated
</div>

</body>
</html>"""
    return html


def main():
    parser = argparse.ArgumentParser(description="Generate EAGLE baseline HTML report")
    parser.add_argument("--version", required=True, help="Version label (e.g., v8)")
    parser.add_argument("--json", default=None, help="Path to baseline JSON results")
    parser.add_argument("--output", default=None, help="Output HTML path")
    parser.add_argument("--scores", default=None, help="JSON string or file with scores")
    parser.add_argument("--eagle-prompt", default=None, help="Path to EAGLE supervisor agent.md")
    parser.add_argument("--ro-prompt", default=None, help="Path to RO supervisor agent.md")
    args = parser.parse_args()

    # Find JSON
    if args.json:
        json_path = Path(args.json)
    else:
        repo_root = Path(__file__).resolve().parent.parent.parent.parent.parent
        json_path = repo_root / "scripts" / f"baseline_{args.version}_results.json"

    if not json_path.exists():
        print(f"ERROR: Results file not found: {json_path}")
        sys.exit(1)

    with open(json_path, "r", encoding="utf-8") as f:
        results = json.load(f)

    # Parse scores if provided
    scores = None
    if args.scores:
        scores_path = Path(args.scores)
        if scores_path.exists():
            with open(scores_path, "r", encoding="utf-8") as f:
                scores = json.load(f)
        else:
            scores = json.loads(args.scores)

    # Output path
    if args.output:
        output_path = Path(args.output)
    else:
        repo_root = Path(__file__).resolve().parent.parent.parent.parent.parent
        output_path = repo_root / "scripts" / f"baseline_{args.version}_report.html"

    # Read system prompts
    eagle_prompt = ""
    ro_prompt = ""
    eagle_prompt_path = Path(args.eagle_prompt) if args.eagle_prompt else (
        Path(__file__).resolve().parent.parent.parent.parent.parent
        / "eagle-plugin" / "agents" / "supervisor" / "agent.md"
    )
    ro_prompt_path = Path(args.ro_prompt) if args.ro_prompt else (
        Path("C:/Users/blackga/Desktop/eagle/nci-webtools-ctri-arti/eagle-plugin/agents/supervisor/agent.md")
    )
    if eagle_prompt_path.exists():
        eagle_prompt = eagle_prompt_path.read_text(encoding="utf-8")
        print(f"  EAGLE prompt: {len(eagle_prompt):,} chars from {eagle_prompt_path.name}")
    if ro_prompt_path.exists():
        ro_prompt = ro_prompt_path.read_text(encoding="utf-8")
        print(f"  RO prompt: {len(ro_prompt):,} chars from {ro_prompt_path.name}")

    html = build_html(results, args.version, scores, eagle_prompt, ro_prompt)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Report generated: {output_path}")
    print(f"  Questions: {len(results)}")
    if scores:
        total = sum(s.get("total", 0) for s in scores.values())
        print(f"  Total score: {total}/{len(scores) * 20}")


if __name__ == "__main__":
    main()
