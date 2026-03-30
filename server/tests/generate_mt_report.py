#!/usr/bin/env python3
"""Generate an interactive HTML eval report from latest-strands.json.

Includes multi-turn token breakdowns, indicator analysis, and
Langfuse/CloudWatch observability sections when trace data is present.

Usage:
    python tests/generate_mt_report.py                       # all tests in JSON
    python tests/generate_mt_report.py --tests 129-137       # multi-turn only
    python tests/generate_mt_report.py --open                # generate and open
"""
import json
import os
import re
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
_RESULTS_DIR = _ROOT / "data" / "eval" / "results"
_DEFAULT_JSON = _RESULTS_DIR / "latest-strands.json"

# ── Metadata for indicator display ───────────────────────────
_TEST_META = {
    129: {"uc": "UC-2",   "title": "GSA Schedule Purchase",       "sub": "$45K confocal microscope",              "turns": 3, "skill": "oa-intake"},
    130: {"uc": "UC-2.1", "title": "Micro Purchase",              "sub": "$14K lab supplies, purchase card",      "turns": 2, "skill": "oa-intake"},
    131: {"uc": "UC-3",   "title": "Sole Source J&amp;A",         "sub": "$280K Illumina software maintenance",   "turns": 3, "skill": "oa-intake"},
    132: {"uc": "UC-4",   "title": "Competitive Range Advisory",  "sub": "$2.1M FAR Part 15, 7 proposals",        "turns": 3, "skill": "legal-counsel"},
    133: {"uc": "UC-10",  "title": "IGCE Development",            "sub": "$4.5M clinical research, 4 labor cats",  "turns": 3, "skill": "oa-intake"},
    134: {"uc": "UC-13",  "title": "Small Business Set-Aside",    "sub": "$450K IT services, Rule of Two",        "turns": 3, "skill": "market-intelligence"},
    135: {"uc": "UC-16",  "title": "Tech to Contract Language",   "sub": "Genomic sequencing SOW translation",    "turns": 3, "skill": "tech-translator"},
    136: {"uc": "UC-29",  "title": "E2E Acquisition",             "sub": "$3.5M R&amp;D bioinformatics, 5-turn",  "turns": 5, "skill": "supervisor"},
    137: {"uc": "UC-29",  "title": "E2E + Package Finalize",      "sub": "$3.5M R&amp;D, 6-turn validation",      "turns": 6, "skill": "supervisor"},
}


def _parse_indicators(logs: list[str]) -> dict:
    for line in logs:
        m = re.search(r"Indicators:\s*(\d+)/(\d+)\s*->\s*(\{.*\})", line)
        if m:
            hit, total = int(m.group(1)), int(m.group(2))
            try:
                raw = m.group(3).replace("True", "true").replace("False", "false")
                detail = json.loads(raw.replace("'", '"'))
            except Exception:
                detail = {}
            return {"hit": hit, "total": total, "detail": detail}
    return {"hit": 0, "total": 0, "detail": {}}


def _parse_tokens(logs: list[str]) -> dict:
    turns = []
    total_in = total_out = 0
    for line in logs:
        m = re.search(r"\[Turn (\d+)\] Response:\s*(\d+)\s*chars,\s*([\d,]+)\s*in\s*/\s*([\d,]+)\s*out", line)
        if m:
            t_in = int(m.group(3).replace(",", ""))
            t_out = int(m.group(4).replace(",", ""))
            turns.append({"turn": int(m.group(1)), "chars": int(m.group(2)), "input": t_in, "output": t_out})
            total_in += t_in
            total_out += t_out
    return {"turns": turns, "total_input": total_in, "total_output": total_out}


def generate_html(data: dict, test_filter: set[int] | None = None) -> str:
    run_ts = data.get("timestamp", "unknown")
    run_id = data.get("run_id", "unknown")

    results = data.get("results", {})
    if test_filter:
        results = {k: v for k, v in results.items() if int(k) in test_filter}

    total = len(results)
    passed = sum(1 for v in results.values() if v.get("status") == "pass")
    failed = total - passed
    total_turns = 0
    total_ind_hit = 0
    total_ind = 0

    test_rows = []
    for tid_str, entry in sorted(results.items(), key=lambda x: int(x[0])):
        tid = int(tid_str)
        meta = _TEST_META.get(tid, {"uc": "?", "title": tid_str, "sub": "", "turns": 1, "skill": "?"})
        logs = entry.get("logs", [])
        status = entry.get("status", "fail")
        indicators = _parse_indicators(logs)
        tokens = _parse_tokens(logs)
        lf = entry.get("langfuse", {})

        total_turns += meta["turns"]
        total_ind_hit += indicators["hit"]
        total_ind += indicators["total"]

        test_rows.append({
            "id": tid, "meta": meta, "status": status,
            "indicators": indicators, "tokens": tokens,
            "logs": logs, "langfuse": lf,
        })

    has_langfuse = any(r["langfuse"] for r in test_rows)
    grand_in = sum(r["tokens"]["total_input"] for r in test_rows)
    grand_out = sum(r["tokens"]["total_output"] for r in test_rows)

    # ── Build HTML ───────────────────────────────────────────
    parts = []
    parts.append(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>EAGLE Eval — Multi-Turn UC Tests</title>
<style>
:root{{--pass:#16a34a;--pass-bg:#dcfce7;--pass-b:#86efac;--fail:#dc2626;--fail-bg:#fee2e2;--fail-b:#fca5a5;--warn:#d97706;--warn-bg:#fef3c7;--warn-b:#fde68a;--blue:#003366;--blue-l:#e8f0fe;--blue-b:#93c5fd;--purple:#7c3aed;--purple-bg:#f3e8ff;--purple-b:#c4b5fd;--g50:#f9fafb;--g100:#f3f4f6;--g200:#e5e7eb;--g300:#d1d5db;--g600:#4b5563;--g800:#1f2937}}
*{{box-sizing:border-box;margin:0;padding:0}}body{{font-family:'Segoe UI',system-ui,sans-serif;background:var(--g50);color:var(--g800);line-height:1.5}}.ctr{{max-width:1200px;margin:0 auto;padding:24px}}
.hdr{{background:var(--blue);color:#fff;padding:28px 32px;border-radius:12px;margin-bottom:24px}}.hdr h1{{font-size:1.5rem;font-weight:700;margin-bottom:4px}}.hdr .sub{{opacity:.85;font-size:.9rem}}.hdr .meta{{display:flex;gap:20px;margin-top:12px;font-size:.82rem;opacity:.8;flex-wrap:wrap}}
.sum{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:14px;margin-bottom:24px}}.cd{{background:#fff;border-radius:10px;padding:18px;border:1px solid var(--g200);text-align:center}}.cd .v{{font-size:1.8rem;font-weight:800}}.cd .l{{font-size:.75rem;color:var(--g600);text-transform:uppercase;letter-spacing:.05em;margin-top:4px}}.cd.p .v{{color:var(--pass)}}.cd.f .v{{color:var(--fail)}}.cd.i .v{{color:var(--blue)}}.cd.u .v{{color:var(--purple)}}
.obs{{display:flex;gap:16px;margin-bottom:16px;padding:16px;border-radius:10px;align-items:flex-start;flex-wrap:wrap}}.obs h3{{font-size:.9rem;font-weight:700}}.obs p{{font-size:.82rem;color:var(--g600)}}.obs-links{{display:flex;gap:8px;flex-wrap:wrap;margin-top:6px}}.obs-links a{{font-size:.75rem;text-decoration:none;padding:3px 10px;border-radius:6px}}
table{{width:100%;border-collapse:separate;border-spacing:0;background:#fff;border-radius:10px;border:1px solid var(--g200);overflow:hidden;margin-bottom:24px}}thead{{background:var(--g100)}}th{{padding:10px 14px;text-align:left;font-size:.75rem;text-transform:uppercase;letter-spacing:.05em;color:var(--g600);font-weight:600;border-bottom:2px solid var(--g200)}}td{{padding:10px 14px;border-bottom:1px solid var(--g100);font-size:.85rem;vertical-align:top}}tr:last-child td{{border-bottom:none}}tr.ck:hover{{background:var(--g50);cursor:pointer}}
.bd{{display:inline-block;padding:2px 10px;border-radius:9999px;font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.03em}}.bd.pass{{background:var(--pass-bg);color:var(--pass);border:1px solid var(--pass-b)}}.bd.fail{{background:var(--fail-bg);color:var(--fail);border:1px solid var(--fail-b)}}
.ind{{display:flex;flex-wrap:wrap;gap:3px}}.pill{{display:inline-block;padding:1px 7px;border-radius:6px;font-size:.68rem;font-weight:600}}.pill.h{{background:var(--pass-bg);color:var(--pass)}}.pill.m{{background:var(--fail-bg);color:var(--fail);text-decoration:line-through;opacity:.7}}
.trn{{display:flex;gap:4px;align-items:center}}.td2{{width:20px;height:20px;border-radius:50%;background:var(--pass-bg);border:2px solid var(--pass);display:flex;align-items:center;justify-content:center;font-size:.6rem;font-weight:800;color:var(--pass)}}.ta{{color:var(--g300);font-size:.65rem}}
.dc{{display:none}}.dc.open{{display:table-row}}.di{{padding:16px}}.dg{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}@media(max-width:768px){{.dg{{grid-template-columns:1fr}}}}.ds{{background:var(--g50);border:1px solid var(--g200);border-radius:8px;padding:12px}}.ds h4{{font-size:.78rem;text-transform:uppercase;color:var(--g600);margin-bottom:8px;letter-spacing:.04em}}
.lb{{background:var(--g800);color:#e5e7eb;padding:12px 16px;border-radius:8px;font-family:'Cascadia Code','Fira Code',monospace;font-size:.72rem;line-height:1.5;overflow-x:auto;white-space:pre-wrap;max-height:350px;overflow-y:auto}}
.tr2{{display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid var(--g200);font-size:.8rem}}.tr2:last-child{{border-bottom:none}}.tr2 .tl{{color:var(--g600)}}.tr2 .tv{{font-weight:700}}
.lfb{{margin-top:10px;padding:8px;background:var(--purple-bg);border-radius:6px;font-size:.75rem}}.lfb strong{{color:var(--purple)}}.lfb a{{color:var(--purple)}}
.ft{{text-align:center;padding:20px;font-size:.78rem;color:var(--g600)}}
</style>
</head>
<body>
<div class="ctr">

<div class="hdr">
  <h1>EAGLE Multi-Turn UC Eval Report</h1>
  <div class="sub">Category 15: Demo Script Multi-Turn — Conversation replays from EAGLE-DEMO-SCRIPT.md</div>
  <div class="meta">
    <span>Run: {run_ts[:19]}Z</span>
    <span>ID: {run_id}</span>
    <span>Backend: Strands SDK / Bedrock</span>
  </div>
</div>

<div class="sum">
  <div class="cd {'p' if failed==0 else 'f'}"><div class="v">{passed}/{total}</div><div class="l">Tests Passed</div></div>
  <div class="cd {'p' if failed==0 else 'f'}"><div class="v">{round(passed/total*100) if total else 0}%</div><div class="l">Pass Rate</div></div>
  <div class="cd i"><div class="v">{total_turns}</div><div class="l">Total Turns</div></div>
  <div class="cd i"><div class="v">{total_ind_hit}/{total_ind}</div><div class="l">Indicators Hit</div></div>
  <div class="cd u"><div class="v">{grand_in:,}</div><div class="l">Input Tokens</div></div>
  <div class="cd u"><div class="v">{grand_out:,}</div><div class="l">Output Tokens</div></div>
</div>
""")

    # Langfuse observability banner
    if has_langfuse:
        lf_all = [r["langfuse"] for r in test_rows if r["langfuse"]]
        lf_cp = sum(t.get("checks_passed", 0) for t in lf_all)
        lf_ct = sum(t.get("checks_total", 0) for t in lf_all)
        parts.append(f'<div class="obs" style="background:var(--purple-bg);border:1px solid var(--purple-b)">\n  <div>\n    <h3 style="color:var(--purple)">Langfuse Trace Validation</h3>\n    <p>{len(lf_all)} traces | {lf_cp}/{lf_ct} checks passed</p>\n    <div class="obs-links">\n')
        for r in test_rows:
            if r["langfuse"] and r["langfuse"].get("trace_url"):
                parts.append(f'      <a href="{r["langfuse"]["trace_url"]}" target="_blank" style="color:var(--purple);border:1px solid var(--purple-b)">Test {r["id"]}</a>\n')
        parts.append("    </div>\n  </div>\n</div>\n")
    else:
        parts.append('<div class="obs" style="background:var(--warn-bg);border:1px solid var(--warn-b)">\n  <div>\n    <h3 style="color:var(--warn)">Langfuse Not Enabled</h3>\n    <p>Run with <code>--validate-traces</code> for Langfuse trace links &amp; checks in this report.</p>\n  </div>\n</div>\n')

    # CloudWatch banner
    parts.append('<div class="obs" style="background:var(--blue-l);border:1px solid var(--blue-b)">\n  <div>\n    <h3 style="color:var(--blue)">CloudWatch Telemetry</h3>\n    <p>With <code>--emit-cloudwatch</code>, each test emits to <code>/eagle/eval/test-results</code>. Query via <code>/check-cloudwatch-logs</code>.</p>\n  </div>\n</div>\n')

    # Table
    parts.append('<table>\n<thead><tr><th>#</th><th>Test</th><th>UC</th><th>Turns</th><th>Skill</th><th>Tokens</th><th>Status</th><th>Indicators</th></tr></thead>\n<tbody>\n')

    for r in test_rows:
        tid = r["id"]
        m = r["meta"]
        s = r["status"]
        ind = r["indicators"]
        tok = r["tokens"]

        dots = ""
        for i in range(1, m["turns"] + 1):
            if i > 1:
                dots += '<span class="ta">&#8594;</span>'
            dots += f'<div class="td2">{i}</div>'

        pills = ""
        for name, hit in ind["detail"].items():
            pills += f'<span class="pill {"h" if hit else "m"}">{name}</span>'

        lf_tag = ""
        if r["langfuse"] and r["langfuse"].get("trace_url"):
            lf_tag = f' <a href="{r["langfuse"]["trace_url"]}" target="_blank" style="font-size:.7rem;color:var(--purple)">[LF]</a>'

        parts.append(f'<tr class="ck" onclick="toggle(\'d{tid}\')"><td>{tid}</td><td><strong>{m["title"]}</strong><br><small>{m["sub"]}</small></td><td>{m["uc"]}</td><td><div class="trn">{dots}</div></td><td>{m["skill"]}</td><td><small>{tok["total_input"]:,} in<br>{tok["total_output"]:,} out</small></td><td><span class="bd {s}">{s.upper()}</span>{lf_tag}</td><td><div class="ind">{pills}</div><small style="color:var(--g600)">{ind["hit"]}/{ind["total"]}</small></td></tr>\n')

        # Detail row
        parts.append(f'<tr class="dc" id="d{tid}"><td colspan="8"><div class="di"><div class="dg">\n')

        # Left: tokens
        parts.append('<div class="ds"><h4>Token Breakdown</h4>\n')
        for t in tok["turns"]:
            parts.append(f'<div class="tr2"><span class="tl">Turn {t["turn"]}</span><span class="tv">{t["input"]:,} in / {t["output"]:,} out ({t["chars"]} chars)</span></div>\n')
        parts.append(f'<div class="tr2" style="border-top:2px solid var(--g300)"><span class="tl"><strong>Total</strong></span><span class="tv"><strong>{tok["total_input"]:,} in / {tok["total_output"]:,} out</strong></span></div>\n')

        if r["langfuse"]:
            lf = r["langfuse"]
            parts.append(f'<div class="lfb"><strong>Langfuse</strong><br>Trace: <code>{lf.get("trace_id","N/A")}</code><br>Generations: {lf.get("generations",0)} | Spans: {lf.get("spans",0)}<br>Checks: {lf.get("checks_passed",0)}/{lf.get("checks_total",0)} passed')
            if lf.get("trace_url"):
                parts.append(f'<br><a href="{lf["trace_url"]}" target="_blank">View Trace &#8599;</a>')
            parts.append("</div>\n")

        parts.append("</div>\n")

        # Right: logs
        log_text = "\n".join(r["logs"]).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        parts.append(f'<div class="ds"><h4>Raw Logs</h4>\n<div class="lb">{log_text}</div></div>\n')

        parts.append("</div></div></td></tr>\n")

    parts.append("</tbody></table>\n")
    parts.append(f'<div class="ft">EAGLE Eval Suite — Multi-Turn UC Tests | Generated {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")} UTC</div>\n')
    parts.append("</div>\n<script>function toggle(id){document.getElementById(id).classList.toggle('open')}</script>\n</body></html>")

    return "".join(parts)


def main():
    parser = argparse.ArgumentParser(description="Generate HTML eval report from JSON results")
    parser.add_argument("--json", default=str(_DEFAULT_JSON), help="Path to JSON results")
    parser.add_argument("--tests", help="Test IDs (e.g., 129-137 or 129,130)")
    parser.add_argument("--output", help="Output HTML path")
    parser.add_argument("--open", action="store_true", help="Open in browser after generating")
    args = parser.parse_args()

    with open(args.json, encoding="utf-8") as f:
        data = json.load(f)

    test_filter = None
    if args.tests:
        test_filter = set()
        for part in args.tests.split(","):
            if "-" in part:
                lo, hi = part.split("-", 1)
                test_filter.update(range(int(lo), int(hi) + 1))
            else:
                test_filter.add(int(part))

    html = generate_html(data, test_filter)

    if args.output:
        out_path = Path(args.output)
    else:
        out_path = _RESULTS_DIR / "multi-turn-report.html"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"Report: {out_path}")

    if args.open:
        import subprocess
        subprocess.Popen(["start", "", str(out_path)], shell=True)

    return str(out_path)


if __name__ == "__main__":
    main()
