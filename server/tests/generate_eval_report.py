"""
EAGLE MVP1 Eval Report Generator

Runs backend pytest suites, captures results, then generates a timestamped
markdown report in test-reports/{timestamp}/ with embedded screenshot
references from Playwright E2E runs.

Usage:
    python tests/generate_eval_report.py [--skip-e2e] [--skip-backend]
"""

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SERVER_DIR = REPO_ROOT / "server"
CLIENT_DIR = REPO_ROOT / "client"
REPORT_DIR = REPO_ROOT / "test-reports"

TIER1_TESTS = [
    "tests/test_compliance_matrix.py",
    "tests/test_chat_kb_flow.py",
    "tests/test_canonical_package_document_flow.py",
    "tests/test_document_pipeline.py",
]

TIER2_TESTS = [
    "tests/test_strands_multi_agent.py",
    "tests/test_strands_poc.py",
    "tests/test_strands_service_integration.py",
]

E2E_TESTS = [
    "tests/intake.spec.ts",
    "tests/chat.spec.ts",
    "tests/uc-micro-purchase.spec.ts",
    "tests/uc-intake.spec.ts",
    "tests/documents.spec.ts",
    "tests/admin-dashboard.spec.ts",
]

ENVIRONMENT = os.getenv("EAGLE_ENVIRONMENT", os.getenv("ENVIRONMENT", "dev"))


def _conversation_scorer():
    """Lazy import so `app.telemetry` resolves when the script is run from repo root."""
    p = str(SERVER_DIR.resolve())
    if p not in sys.path:
        sys.path.insert(0, p)
    from app.telemetry import conversation_scorer as cs

    return cs


def _tier_pass_rate(result: dict | None) -> float | None:
    if result is None:
        return None
    n = result["passed"] + result["failed"] + result.get("errors", 0)
    if n <= 0:
        return None
    return result["passed"] / n


def run_pytest(test_files: list[str], label: str, cwd: Path) -> dict:
    """Run pytest and return structured results."""
    start = time.time()
    cmd = [
        sys.executable, "-m", "pytest",
        *test_files,
        "-v", "--tb=short", "--no-header",
        f"--junitxml={cwd / f'.pytest-{label}.xml'}",
    ]
    env = {**os.environ, "AWS_PROFILE": "eagle"}
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(cwd), env=env)
    elapsed = time.time() - start

    # Parse pass/fail from output
    output = result.stdout + result.stderr
    passed = len(re.findall(r" PASSED", output))
    failed = len(re.findall(r" FAILED", output))
    errors = len(re.findall(r" ERROR", output))

    # Collect failure names
    failures = re.findall(r"FAILED (tests/\S+)", output)

    return {
        "label": label,
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "failures": failures,
        "elapsed": elapsed,
        "returncode": result.returncode,
        "output": output,
    }


def run_playwright(report_dir: Path) -> dict:
    """Run Playwright E2E tests with screenshots."""
    screenshot_dir = report_dir / "screenshots"
    screenshot_dir.mkdir(exist_ok=True)

    start = time.time()
    npx = r"C:\Program Files\nodejs\npx.cmd" if os.name == "nt" else "npx"
    cmd = [
        npx, "playwright", "test",
        *E2E_TESTS,
        "--project=chromium",
        "--reporter=list,html",
        f"--output={screenshot_dir}",
    ]
    env = {
        **os.environ,
        "BASE_URL": "http://localhost:3000",
        "PLAYWRIGHT_HTML_REPORT": str(report_dir / "playwright-report"),
    }
    result = subprocess.run(
        cmd, capture_output=True, text=True, cwd=str(CLIENT_DIR), env=env,
        timeout=300, shell=(os.name == "nt"),
    )
    elapsed = time.time() - start

    output = result.stdout + result.stderr
    # Parse summary line: "N passed" / "N failed" at end of output
    m_passed = re.search(r"(\d+) passed", output)
    m_failed = re.search(r"(\d+) failed", output)
    passed = int(m_passed.group(1)) if m_passed else 0
    failed = int(m_failed.group(1)) if m_failed else 0

    # Collect screenshot paths
    screenshots = sorted(screenshot_dir.glob("**/*.png"))

    return {
        "label": "E2E (Playwright)",
        "passed": passed,
        "failed": failed,
        "elapsed": elapsed,
        "returncode": result.returncode,
        "screenshots": [str(s.relative_to(report_dir)) for s in screenshots],
        "output": output,
    }


def generate_report(
    timestamp: str,
    report_dir: Path,
    tier1: dict | None,
    tier2: dict | None,
    e2e: dict | None,
) -> str:
    """Generate markdown report."""
    lines = [
        f"# EAGLE MVP1 Eval Report",
        f"",
        f"**Date:** {timestamp}  ",
        f"**Environment:** {ENVIRONMENT}  ",
        f"**Branch:** main  ",
        f"**Commit:** {_git_short_sha()}  ",
        f"",
        f"---",
        f"",
        f"## Summary",
        f"",
        f"| Tier | Suite | Tests | Passed | Failed | Time |",
        f"|------|-------|-------|--------|--------|------|",
    ]

    total_tests = total_passed = total_failed = 0
    total_time = 0.0

    for result, tier_name in [
        (tier1, "1 - Unit"),
        (tier2, "2 - Integration"),
        (e2e, "3 - E2E"),
    ]:
        if result is None:
            lines.append(f"| {tier_name} | {result and result['label'] or 'skipped'} | - | - | - | skipped |")
            continue
        tests = result["passed"] + result["failed"] + result.get("errors", 0)
        status = "PASS" if result["failed"] == 0 and result.get("errors", 0) == 0 else "FAIL"
        lines.append(
            f"| {tier_name} | {result['label']} | {tests} | "
            f"**{result['passed']}** | {result['failed']} | "
            f"{result['elapsed']:.0f}s |"
        )
        total_tests += tests
        total_passed += result["passed"]
        total_failed += result["failed"]
        total_time += result["elapsed"]

    overall = "PASS" if total_failed == 0 else "FAIL"
    lines.extend([
        f"| **Total** | | **{total_tests}** | **{total_passed}** | **{total_failed}** | **{total_time:.0f}s** |",
        f"",
        f"**Overall: {overall}**",
        f"",
    ])

    # Tier details
    for result, tier_name in [
        (tier1, "Tier 1 — Unit Tests"),
        (tier2, "Tier 2 — Integration Tests"),
    ]:
        if result is None:
            continue
        lines.extend([
            f"---",
            f"",
            f"## {tier_name}",
            f"",
        ])
        if result["failures"]:
            lines.append("### Failures")
            lines.append("```")
            for f in result["failures"]:
                lines.append(f"FAILED {f}")
            lines.append("```")
            lines.append("")

    # E2E section with screenshots
    if e2e:
        lines.extend([
            f"---",
            f"",
            f"## Tier 3 — E2E Screenshots",
            f"",
        ])
        if e2e.get("screenshots"):
            for ss in e2e["screenshots"]:
                name = Path(ss).stem.replace("-", " ").replace("_", " ").title()
                lines.append(f"### {name}")
                lines.append(f"![{name}]({ss})")
                lines.append("")
        else:
            lines.append("*No screenshots captured — see raw output below.*")
            lines.append("")

        if e2e["failed"] > 0:
            lines.extend([
                "### E2E Output",
                "```",
                e2e["output"][-2000:] if len(e2e["output"]) > 2000 else e2e["output"],
                "```",
                "",
            ])

    # Raw logs
    lines.extend([
        f"---",
        f"",
        f"## Raw Test Output",
        f"",
    ])
    for result in [tier1, tier2]:
        if result is None:
            continue
        lines.extend([
            f"<details>",
            f"<summary>{result['label']} output</summary>",
            f"",
            f"```",
            result["output"][-5000:] if len(result["output"]) > 5000 else result["output"],
            f"```",
            f"</details>",
            f"",
        ])

    return "\n".join(lines)


def _copy_playwright_screenshots(report_dir: Path) -> None:
    """Copy screenshots from report screenshots/ and client/test-results/."""
    import shutil

    # Copy from the --output dir (already inside report_dir/screenshots/)
    screenshot_dir = report_dir / "screenshots"
    count = 0
    if screenshot_dir.exists():
        count = len(list(screenshot_dir.glob("**/*.png")))

    # Also copy from client/test-results/ (default Playwright output)
    src_dir = CLIENT_DIR / "test-results"
    if src_dir.exists():
        screenshot_dir.mkdir(exist_ok=True)
        for png in sorted(src_dir.glob("**/*.png")):
            parent = png.parent.name
            dst = screenshot_dir / f"{parent}--{png.name}"
            if not dst.exists():
                shutil.copy2(png, dst)
                count += 1

    print(f"  >{count} total screenshots in {screenshot_dir}")


def generate_html_report(
    timestamp: str,
    report_dir: Path,
    tier1: dict | None,
    tier2: dict | None,
    e2e: dict | None,
) -> str:
    """Generate a self-contained HTML report with embedded screenshots."""
    import base64

    commit = _git_short_sha()

    # Collect all tier results for summary
    tiers = []
    total_tests = total_passed = total_failed = 0
    total_time = 0.0
    for result, name in [(tier1, "Tier 1 - Unit"), (tier2, "Tier 2 - Integration"), (e2e, "Tier 3 - E2E")]:
        if result is None:
            tiers.append({"name": name, "label": "skipped", "tests": 0, "passed": 0, "failed": 0, "time": 0})
            continue
        tests = result["passed"] + result["failed"] + result.get("errors", 0)
        tiers.append({
            "name": name, "label": result["label"],
            "tests": tests, "passed": result["passed"],
            "failed": result["failed"], "time": result["elapsed"],
        })
        total_tests += tests
        total_passed += result["passed"]
        total_failed += result["failed"]
        total_time += result["elapsed"]

    overall = "PASS" if total_failed == 0 else "FAIL"

    cs = _conversation_scorer()
    tier_scores: list[float] = []
    for res in (tier1, tier2):
        tr = _tier_pass_rate(res)
        if tr is not None:
            tier_scores.append(100.0 * tr)
    overall_pass_rate = (total_passed / total_tests) if total_tests else 0.0
    backend_rollup = cs.rollup_eval_backend_only(
        tier_scores_0_100=tier_scores,
        overall_pass_rate=overall_pass_rate,
    )
    e2e_rate = _tier_pass_rate(e2e)
    rollup = cs.rollup_eval_full_stack(backend_rollup, e2e_pass_rate=e2e_rate)
    run_conf = cs.eval_run_confidence_from_tiers(tier1=tier1, tier2=tier2, e2e=e2e)
    quality_band = cs.score_band_label(rollup["score"])
    quality_blurb = cs.score_band_description(rollup["score"])
    conf_band = cs.score_band_label(run_conf["score"])

    # Build summary rows
    summary_rows = ""
    for t in tiers:
        if t["label"] == "skipped":
            summary_rows += f'<tr><td>{t["name"]}</td><td>skipped</td><td>-</td><td>-</td><td>-</td><td>-</td></tr>\n'
        else:
            status_cls = "pass" if t["failed"] == 0 else "fail"
            summary_rows += (
                f'<tr class="{status_cls}"><td>{t["name"]}</td><td>{t["label"]}</td>'
                f'<td>{t["tests"]}</td><td><strong>{t["passed"]}</strong></td>'
                f'<td>{t["failed"]}</td><td>{t["time"]:.0f}s</td></tr>\n'
            )

    # Embed screenshots as base64
    screenshot_html = ""
    screenshot_dir = report_dir / "screenshots"
    if screenshot_dir.exists():
        pngs = sorted(screenshot_dir.glob("**/*.png"))
        if pngs:
            screenshot_html += '<h2>E2E Screenshots</h2>\n<div class="screenshots">\n'
            for png in pngs:
                b64 = base64.b64encode(png.read_bytes()).decode()
                name = png.stem.replace("--", " > ").replace("-", " ").title()
                screenshot_html += (
                    f'<div class="screenshot-card">\n'
                    f'  <h3>{name}</h3>\n'
                    f'  <img src="data:image/png;base64,{b64}" alt="{name}" />\n'
                    f'</div>\n'
                )
            screenshot_html += '</div>\n'

    # Failure details
    failure_html = ""
    for result, name in [(tier1, "Tier 1"), (tier2, "Tier 2")]:
        if result and result.get("failures"):
            failure_html += f'<h3>{name} Failures</h3>\n<pre>'
            for f in result["failures"]:
                failure_html += f"FAILED {f}\n"
            failure_html += '</pre>\n'

    if e2e and e2e.get("failed", 0) > 0:
        output_tail = e2e["output"][-3000:] if len(e2e["output"]) > 3000 else e2e["output"]
        failure_html += f'<h3>E2E Failures</h3>\n<pre>{_html_escape(output_tail)}</pre>\n'

    hero_band_class = " low" if rollup["score"] < 60 else (" mid" if rollup["score"] < 85 else "")
    hero_e2e_line = f"E2E pass {e2e_rate:.0%}" if e2e_rate is not None else "Backend tiers only"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>EAGLE MVP1 Eval Report - {timestamp}</title>
<style>
  :root {{ --bg: #0f172a; --card: #1e293b; --border: #334155; --text: #e2e8f0; --muted: #94a3b8; --green: #22c55e; --red: #ef4444; --blue: #3b82f6; }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: var(--bg); color: var(--text); padding: 2rem; }}
  .container {{ max-width: 1200px; margin: 0 auto; }}
  h1 {{ font-size: 2rem; margin-bottom: 0.5rem; }}
  h2 {{ font-size: 1.4rem; margin: 2rem 0 1rem; border-bottom: 1px solid var(--border); padding-bottom: 0.5rem; }}
  h3 {{ font-size: 1.1rem; margin: 1rem 0 0.5rem; color: var(--muted); }}
  .meta {{ color: var(--muted); margin-bottom: 2rem; }}
  .meta span {{ margin-right: 2rem; }}
  .badge {{ display: inline-block; padding: 0.25rem 0.75rem; border-radius: 9999px; font-weight: 700; font-size: 0.9rem; }}
  .badge.pass {{ background: #166534; color: var(--green); }}
  .badge.fail {{ background: #7f1d1d; color: var(--red); }}
  table {{ width: 100%; border-collapse: collapse; margin: 1rem 0; }}
  th, td {{ padding: 0.75rem 1rem; text-align: left; border-bottom: 1px solid var(--border); }}
  th {{ background: var(--card); color: var(--muted); font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.05em; }}
  tr.pass td:nth-child(4) {{ color: var(--green); font-weight: 700; }}
  tr.fail td:nth-child(5) {{ color: var(--red); font-weight: 700; }}
  .stat-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin: 1.5rem 0; }}
  .stat-card {{ background: var(--card); border: 1px solid var(--border); border-radius: 0.5rem; padding: 1.25rem; }}
  .stat-card .value {{ font-size: 2rem; font-weight: 700; }}
  .stat-card .label {{ color: var(--muted); font-size: 0.85rem; margin-top: 0.25rem; }}
  .screenshots {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(500px, 1fr)); gap: 1.5rem; }}
  .screenshot-card {{ background: var(--card); border: 1px solid var(--border); border-radius: 0.5rem; overflow: hidden; }}
  .screenshot-card h3 {{ padding: 0.75rem 1rem; margin: 0; font-size: 0.9rem; }}
  .screenshot-card img {{ width: 100%; height: auto; display: block; }}
  pre {{ background: var(--card); border: 1px solid var(--border); border-radius: 0.5rem; padding: 1rem; overflow-x: auto; font-size: 0.85rem; color: var(--muted); white-space: pre-wrap; word-break: break-all; }}
  details {{ margin: 1rem 0; }}
  summary {{ cursor: pointer; color: var(--blue); font-weight: 600; }}
  .hero {{ background: linear-gradient(135deg, #1e3a5f 0%, #0f172a 100%); border: 1px solid var(--border); border-radius: 0.75rem; padding: 1.5rem 1.75rem; margin-bottom: 1.75rem; }}
  .hero h2 {{ font-size: 1rem; color: var(--muted); font-weight: 600; margin-bottom: 0.75rem; text-transform: uppercase; letter-spacing: 0.06em; border: none; padding: 0; }}
  .hero-score {{ font-size: 2.75rem; font-weight: 800; color: #f8fafc; line-height: 1.1; }}
  .hero-band {{ display: inline-block; margin-top: 0.5rem; padding: 0.2rem 0.65rem; border-radius: 9999px; font-size: 0.85rem; font-weight: 700; background: rgba(34, 197, 94, 0.2); color: var(--green); }}
  .hero-band.mid {{ background: rgba(234, 179, 8, 0.2); color: #eab308; }}
  .hero-band.low {{ background: rgba(239, 68, 68, 0.2); color: var(--red); }}
  .hero p {{ color: var(--muted); font-size: 0.95rem; margin-top: 0.75rem; max-width: 52rem; line-height: 1.55; }}
  .hero-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin-top: 1.25rem; }}
  .hero-mini {{ background: rgba(30, 41, 59, 0.8); border: 1px solid var(--border); border-radius: 0.5rem; padding: 1rem; }}
  .hero-mini .mv {{ font-size: 1.5rem; font-weight: 700; color: #e2e8f0; }}
  .hero-mini .ml {{ font-size: 0.78rem; color: var(--muted); margin-top: 0.25rem; text-transform: uppercase; letter-spacing: 0.04em; }}
  .band-key {{ font-size: 0.82rem; color: var(--muted); margin: 1rem 0 0.5rem; line-height: 1.5; }}
  .band-key code {{ background: var(--card); padding: 0.1rem 0.4rem; border-radius: 4px; font-size: 0.78rem; }}
</style>
</head>
<body>
<div class="container">

<h1>EAGLE MVP1 Eval Report</h1>
<div class="meta">
  <span>Date: {timestamp}</span>
  <span>Env: {ENVIRONMENT}</span>
  <span>Branch: main</span>
  <span>Commit: {commit}</span>
  <span class="badge {overall.lower()}">{overall}</span>
</div>

<div class="hero">
  <h2>Derived eval quality (pytest / Playwright)</h2>
  <div class="hero-score">{rollup["score"]}<span style="font-size:1.2rem;font-weight:600;color:var(--muted);margin-left:6px">/100</span></div>
  <div class="hero-band{hero_band_class}">{quality_band}</div>
  <p><strong>{quality_blurb}</strong> Rollup mixes per-tier pass rates with overall pass rate
  ({overall_pass_rate:.0%}); when E2E ran, it is weighted into the same score. This is a coarse signal — unlike multi-turn JSON reports, individual test assertions are not rescored here.</p>
  <div class="hero-grid">
    <div class="hero-mini"><div class="mv">{run_conf["score"]}</div><div class="ml">Run confidence</div><div class="ml" style="margin-top:6px;text-transform:none;color:#94a3b8">{conf_band} — tiers run, volume, stability</div></div>
    <div class="hero-mini"><div class="mv">{rollup.get("stack", "backend")}</div><div class="ml">Stack mode</div><div class="ml" style="margin-top:6px;text-transform:none;color:#94a3b8">{hero_e2e_line}</div></div>
    <div class="hero-mini"><div class="mv">{overall_pass_rate:.0%}</div><div class="ml">Overall pass rate</div><div class="ml" style="margin-top:6px;text-transform:none;color:#94a3b8">{total_passed} / {total_tests} tests</div></div>
  </div>
  <p class="band-key">Bands: <code>90+</code> Excellent · <code>75–89</code> Strong · <code>60–74</code> Adequate · <code>40–59</code> Weak · <code>&lt;40</code> Critical</p>
</div>

<div class="stat-grid">
  <div class="stat-card"><div class="value">{total_tests}</div><div class="label">Total Tests</div></div>
  <div class="stat-card"><div class="value" style="color:var(--green)">{total_passed}</div><div class="label">Passed</div></div>
  <div class="stat-card"><div class="value" style="color:{'var(--red)' if total_failed else 'var(--muted)'}">{total_failed}</div><div class="label">Failed</div></div>
  <div class="stat-card"><div class="value">{total_time:.0f}s</div><div class="label">Total Time</div></div>
</div>

<h2>Summary</h2>
<table>
<tr><th>Tier</th><th>Suite</th><th>Tests</th><th>Passed</th><th>Failed</th><th>Time</th></tr>
{summary_rows}
<tr style="font-weight:700;border-top:2px solid var(--border)">
  <td>Total</td><td></td><td>{total_tests}</td><td>{total_passed}</td><td>{total_failed}</td><td>{total_time:.0f}s</td>
</tr>
</table>

{screenshot_html}

{failure_html}

<h2>Raw Output</h2>
{''.join(_raw_output_details(r) for r in [tier1, tier2] if r)}

</div>
</body>
</html>"""


def _html_escape(text: str) -> str:
    """Escape HTML special characters."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _raw_output_details(result: dict) -> str:
    """Generate collapsible raw output section."""
    output = result["output"][-5000:] if len(result["output"]) > 5000 else result["output"]
    return (
        f'<details>\n'
        f'<summary>{result["label"]} output ({result["passed"]} passed, {result["failed"]} failed)</summary>\n'
        f'<pre>{_html_escape(output)}</pre>\n'
        f'</details>\n'
    )


def _git_short_sha() -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=str(REPO_ROOT),
        )
        return r.stdout.strip()
    except Exception:
        return "unknown"


def main():
    skip_e2e = "--skip-e2e" in sys.argv
    skip_backend = "--skip-backend" in sys.argv

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    report_dir = REPORT_DIR / timestamp
    report_dir.mkdir(parents=True, exist_ok=True)

    print(f"[EAGLE Eval] Report dir: {report_dir}")
    print(f"[EAGLE Eval] Timestamp: {timestamp}")
    print()

    # ── Tier 1 ──
    tier1 = None
    if not skip_backend:
        print("[EAGLE Eval] Running Tier 1 — Unit tests...")
        tier1 = run_pytest(TIER1_TESTS, "tier1", SERVER_DIR)
        print(f"  >{tier1['passed']} passed, {tier1['failed']} failed ({tier1['elapsed']:.0f}s)")
        # Save raw output
        (report_dir / "01-tier1-unit.txt").write_text(tier1["output"], encoding="utf-8")

    # ── Tier 2 ──
    tier2 = None
    if not skip_backend:
        print("[EAGLE Eval] Running Tier 2 — Integration tests (Bedrock)...")
        tier2 = run_pytest(TIER2_TESTS, "tier2", SERVER_DIR)
        print(f"  >{tier2['passed']} passed, {tier2['failed']} failed ({tier2['elapsed']:.0f}s)")
        (report_dir / "02-tier2-integration.txt").write_text(tier2["output"], encoding="utf-8")

    # ── Tier 3 (E2E) ──
    e2e = None
    if not skip_e2e:
        print("[EAGLE Eval] Running Tier 3 — Playwright E2E...")
        try:
            e2e = run_playwright(report_dir)
            print(f"  >{e2e['passed']} passed, {e2e['failed']} failed ({e2e['elapsed']:.0f}s)")
            print(f"  >{len(e2e.get('screenshots', []))} screenshots captured")
            (report_dir / "03-tier3-e2e.txt").write_text(e2e["output"], encoding="utf-8")
        except subprocess.TimeoutExpired:
            print("  >E2E timed out (300s)")
        except Exception as exc:
            print(f"  >E2E failed: {exc}")

    # ── Generate report ──
    print()
    print("[EAGLE Eval] Generating report...")
    report_md = generate_report(timestamp, report_dir, tier1, tier2, e2e)
    report_path = report_dir / "eval-report.md"
    report_path.write_text(report_md, encoding="utf-8")
    print(f"[EAGLE Eval] Report: {report_path}")

    # Also write a summary JSON for programmatic use
    summary = {
        "timestamp": timestamp,
        "environment": ENVIRONMENT,
        "commit": _git_short_sha(),
        "tier1": {"passed": tier1["passed"], "failed": tier1["failed"], "time": tier1["elapsed"]} if tier1 else None,
        "tier2": {"passed": tier2["passed"], "failed": tier2["failed"], "time": tier2["elapsed"]} if tier2 else None,
        "e2e": {"passed": e2e["passed"], "failed": e2e["failed"], "time": e2e["elapsed"]} if e2e else None,
    }
    (report_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    # ── HTML report with inline screenshots ──
    print("[EAGLE Eval] Generating HTML report...")
    html = generate_html_report(timestamp, report_dir, tier1, tier2, e2e)
    html_path = report_dir / "eval-report.html"
    html_path.write_text(html, encoding="utf-8")
    print(f"[EAGLE Eval] HTML Report: {html_path}")

    # Also copy screenshots from client/test-results/ into report dir
    _copy_playwright_screenshots(report_dir)

    return 0 if all(
        r is None or (r["failed"] == 0 and r.get("errors", 0) == 0)
        for r in [tier1, tier2, e2e]
    ) else 1


if __name__ == "__main__":
    sys.exit(main())
