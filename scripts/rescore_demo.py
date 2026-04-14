"""Rescore an existing demo run without re-replaying the turns.

Loads the most recent (or specified) demo_eval_results/<run>/results.json,
calls run_demo.score_all_turns(), saves a fresh scores.json, and rebuilds
the HTML report. Used to retry scoring after fixing the Bedrock credential
path without burning another ~200s of API replay.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SKILL_SCRIPTS = REPO / ".claude" / "skills" / "baseline-questions" / "scripts"

# Load server/.env so AWS_PROFILE propagates to the Bedrock client.
try:
    from dotenv import load_dotenv
    load_dotenv(REPO / "server" / ".env", override=False)
except Exception:
    pass

sys.path.insert(0, str(SKILL_SCRIPTS))
sys.path.insert(0, str(REPO / "server"))

import run_demo  # type: ignore  # noqa: E402

RUN_ID = sys.argv[1] if len(sys.argv) > 1 else "20260413-034221"
RUN_DIR = REPO / "scripts" / "demo_eval_results" / RUN_ID

results_path = RUN_DIR / "results.json"
turns_path = RUN_DIR / "demo_turns.json"

print(f"Rescoring run: {RUN_ID}")
print(f"Run dir:       {RUN_DIR}")
print(f"AWS_PROFILE:   {os.environ.get('AWS_PROFILE', '(unset)')}")

with open(results_path, "r", encoding="utf-8") as f:
    results_doc = json.load(f)

# results.json from run_demo has shape
#   { "session_id": ..., "server": ..., "turns": [...] }
# Be defensive across minor version drift.
if isinstance(results_doc, dict):
    results = results_doc.get("turns") or results_doc.get("results") or []
    session_id = results_doc.get("session_id", "")
else:
    results = results_doc
    session_id = ""

print(f"Loaded {len(results)} turns from results.json")

# Exercise the fixed scorer
scores = run_demo.score_all_turns(results)

scores_path = RUN_DIR / "scores.json"
with open(scores_path, "w", encoding="utf-8") as f:
    json.dump({str(k): v for k, v in scores.items()}, f, indent=2, ensure_ascii=False)
print(f"\nScores saved to {scores_path}")

# Rebuild the HTML report with fresh scores
html = run_demo.build_demo_report(
    run_id=RUN_ID,
    demo_path="(rescore)",
    session_id=session_id,
    results=results,
    scores=scores,
    screenshots_by_turn={},
    server_url="http://localhost:8000",
)
report_path = RUN_DIR / "demo_report.html"
with open(report_path, "w", encoding="utf-8") as f:
    f.write(html)
print(f"Report rebuilt: {report_path}")

# Summary
total = sum(s.get("total", 0) for s in scores.values())
max_score = len(scores) * 20
print(f"\nTotal score: {total}/{max_score}")
for turn_num, sc in sorted(scores.items()):
    print(f"  Turn {turn_num}: {sc.get('total', 0)}/20 - {sc.get('verdict', '')[:80]}")
