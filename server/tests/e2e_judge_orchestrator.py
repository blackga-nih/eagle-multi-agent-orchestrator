"""
E2E Judge Orchestrator — CLI entry point for the screenshot + vision judge pipeline.

Runs on the EC2 dev box inside the VPC against the deployed ALB URL.
Captures screenshots via Playwright, sends each to Sonnet for evaluation,
caches results, and produces a structured JSON + markdown report.

Usage:
    python -m tests.e2e_judge_orchestrator \
        --base-url http://EagleC-Front-XYZ.us-east-1.elb.amazonaws.com \
        --journeys chat,home,admin

Environment variables:
    BASE_URL              — Deployed ALB URL (default: http://localhost:3000)
    EAGLE_TEST_EMAIL      — Cognito test user email
    EAGLE_TEST_PASSWORD   — Cognito test user password
    E2E_JUDGE_MODEL       — Vision judge model (default: us.anthropic.claude-sonnet-4-6-20250514-v1:0)
    E2E_JUDGE_CACHE_TTL_DAYS — Cache TTL in days (default: 7)
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure tests/ is importable
_tests_dir = os.path.dirname(os.path.abspath(__file__))
_server_dir = os.path.dirname(_tests_dir)
if _tests_dir not in sys.path:
    sys.path.insert(0, _tests_dir)
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)

from tests.e2e_judge_cache import JudgeCache
from tests.e2e_judge_journeys import JOURNEY_REGISTRY, list_journeys
from tests.e2e_screenshot_capture import ScreenshotCapture
from tests.e2e_vision_judge import VisionJudge

logger = logging.getLogger("e2e-judge")


async def run_pipeline(
    base_url: str,
    journeys: list[str],
    auth_email: str = None,
    auth_password: str = None,
    headed: bool = False,
    purge_cache: bool = False,
    upload_s3: bool = False,
    output_dir: str = None,
) -> dict:
    """Execute the full E2E judge pipeline.

    1. Authenticate and start Playwright
    2. Run selected journeys (capture screenshots)
    3. Judge each screenshot via Bedrock Sonnet converse
    4. Aggregate results
    5. Generate report
    """
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    repo_root = Path(__file__).resolve().parent.parent.parent

    if output_dir is None:
        output_dir = str(repo_root / "data" / "e2e-judge" / "results")
    os.makedirs(output_dir, exist_ok=True)

    # --- Setup ---
    cache = JudgeCache()
    if purge_cache:
        removed = cache.purge()
        logger.info(f"Purged {removed} cached judgments")

    judge = VisionJudge(cache=cache)

    capture = ScreenshotCapture(
        base_url=base_url,
        run_id=run_id,
        headless=not headed,
        auth_email=auth_email,
        auth_password=auth_password,
    )

    # --- Phase 1: Capture screenshots ---
    print(f"\n{'='*60}")
    print(f"E2E Judge Pipeline — Run {run_id}")
    print(f"Target: {base_url}")
    print(f"Journeys: {', '.join(journeys)}")
    print(f"{'='*60}\n")

    await capture.start()

    all_screenshots = []
    journey_results = {}

    for journey_name in journeys:
        if journey_name not in JOURNEY_REGISTRY:
            print(f"  [orchestrator] Unknown journey: {journey_name} (skipping)")
            continue

        journey_def = JOURNEY_REGISTRY[journey_name]
        journey_fn = journey_def["function"]
        print(f"\n--- Journey: {journey_name} ---")

        page = await capture.new_page()
        try:
            screenshots = await journey_fn(page, capture, base_url)
            all_screenshots.extend(screenshots)
            journey_results[journey_name] = {
                "screenshots": screenshots,
                "judgments": [],
            }
        except Exception as e:
            logger.error(f"Journey {journey_name} failed: {e}")
            journey_results[journey_name] = {
                "screenshots": [],
                "judgments": [],
                "error": str(e),
            }
        finally:
            await page.context.close()

    await capture.stop()

    # --- Phase 2: Judge screenshots ---
    print(f"\n--- Judging {len(all_screenshots)} screenshots ---\n")

    all_judgments = []
    for ss in all_screenshots:
        with open(ss["path"], "rb") as f:
            screenshot_bytes = f.read()

        judgment = judge.evaluate(
            screenshot_bytes=screenshot_bytes,
            journey=ss["journey"],
            page_description=ss["description"],
            step_description=ss["step_name"],
            page_context=ss.get("page_context", ""),
        )
        all_judgments.append(judgment)

        # Associate judgment with journey
        if ss["journey"] in journey_results:
            from dataclasses import asdict
            journey_results[ss["journey"]]["judgments"].append(asdict(judgment))

        icon = {"pass": "+", "fail": "X", "warning": "!"}[judgment.verdict]
        print(f"  [{icon}] {ss['journey']}/{ss['step_name']}: {judgment.verdict} "
              f"(score={judgment.ui_quality_score}, cached={judgment.cached})")

    # --- Phase 3: Aggregate results ---
    passed = sum(1 for j in all_judgments if j.verdict == "pass")
    failed = sum(1 for j in all_judgments if j.verdict == "fail")
    warnings = sum(1 for j in all_judgments if j.verdict == "warning")
    avg_score = sum(j.ui_quality_score for j in all_judgments) / len(all_judgments) if all_judgments else 0

    results = {
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "judge_model": judge.model_id,
        "total_screenshots": len(all_screenshots),
        "passed": passed,
        "failed": failed,
        "warnings": warnings,
        "pass_rate": passed / len(all_judgments) if all_judgments else 0,
        "avg_quality_score": round(avg_score, 1),
        "cache_stats": judge.stats,
        "journeys": {},
    }

    for name, data in journey_results.items():
        j_judgments = data.get("judgments", [])
        results["journeys"][name] = {
            "total": len(j_judgments),
            "passed": sum(1 for j in j_judgments if j.get("verdict") == "pass"),
            "failed": sum(1 for j in j_judgments if j.get("verdict") == "fail"),
            "warnings": sum(1 for j in j_judgments if j.get("verdict") == "warning"),
            "steps": [
                {
                    "step_name": j.get("step_name", ""),
                    "verdict": j.get("verdict", ""),
                    "ui_quality_score": j.get("ui_quality_score", 0),
                    "reasoning": j.get("reasoning", ""),
                    "issues": j.get("issues", []),
                    "cached": j.get("cached", False),
                    "screenshot_path": ss["path"] if i < len(data.get("screenshots", [])) else "",
                }
                for i, (j, ss) in enumerate(
                    zip(j_judgments, data.get("screenshots", []))
                )
            ],
            "error": data.get("error"),
        }

    # --- Phase 4: Write results ---
    results_path = os.path.join(output_dir, f"{run_id}.json")
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)

    latest_path = os.path.join(output_dir, "latest.json")
    with open(latest_path, "w") as f:
        json.dump(results, f, indent=2)

    # --- Phase 5: Generate markdown report ---
    report = _generate_report(results)
    report_path = os.path.join(output_dir, f"{run_id}-report.md")
    with open(report_path, "w") as f:
        f.write(report)

    # --- Phase 6: Upload to S3 (optional) ---
    if upload_s3:
        _upload_to_s3(results_path, capture.output_dir, run_id)

    # --- Summary ---
    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed, {warnings} warnings")
    print(f"Avg quality score: {avg_score:.1f}/10")
    print(f"Cache: {judge.stats['cache_hits']}/{judge.stats['total_calls']} hits "
          f"({judge.stats['cache_hit_rate']:.0%})")
    print(f"Cost:   ${judge.stats['cost_usd']:.4f} "
          f"({judge.stats['input_tokens']} in / {judge.stats['output_tokens']} out tokens)")
    print(f"Report: {report_path}")
    print(f"JSON:   {results_path}")
    print(f"{'='*60}\n")

    return results


def _generate_report(results: dict) -> str:
    """Generate a markdown summary report from results JSON."""
    lines = [
        f"# E2E Judge Report — {results['run_id']}",
        "",
        f"**Target**: {results['base_url']}",
        f"**Judge Model**: {results['judge_model']}",
        f"**Timestamp**: {results['timestamp']}",
        "",
        "## Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total screenshots | {results['total_screenshots']} |",
        f"| Passed | {results['passed']} |",
        f"| Failed | {results['failed']} |",
        f"| Warnings | {results['warnings']} |",
        f"| Pass rate | {results['pass_rate']:.0%} |",
        f"| Avg quality score | {results['avg_quality_score']}/10 |",
        f"| Cache hit rate | {results['cache_stats']['cache_hit_rate']:.0%} |",
        f"| Input tokens | {results['cache_stats'].get('input_tokens', 0):,} |",
        f"| Output tokens | {results['cache_stats'].get('output_tokens', 0):,} |",
        f"| Judge cost | ${results['cache_stats'].get('cost_usd', 0):.4f} |",
        "",
    ]

    for name, data in results.get("journeys", {}).items():
        lines.append(f"## Journey: {name}")
        lines.append("")

        if data.get("error"):
            lines.append(f"**Error**: {data['error']}")
            lines.append("")
            continue

        lines.append(f"| Step | Verdict | Score | Reasoning |")
        lines.append(f"|------|---------|-------|-----------|")

        for step in data.get("steps", []):
            verdict_icon = {"pass": "PASS", "fail": "FAIL", "warning": "WARN"}.get(step["verdict"], "?")
            reasoning = step.get("reasoning", "")[:80]
            lines.append(f"| {step['step_name']} | {verdict_icon} | {step['ui_quality_score']}/10 | {reasoning} |")

        lines.append("")

        # List issues for failed steps
        failed_steps = [s for s in data.get("steps", []) if s["verdict"] == "fail"]
        if failed_steps:
            lines.append("### Issues")
            lines.append("")
            for step in failed_steps:
                lines.append(f"**{step['step_name']}**:")
                for issue in step.get("issues", []):
                    lines.append(f"- {issue}")
                lines.append("")

    return "\n".join(lines)


def _upload_to_s3(results_path: str, screenshots_dir: str, run_id: str):
    """Upload results and screenshots to S3 eval bucket."""
    try:
        import boto3

        s3 = boto3.client("s3")
        # Bucket name pattern from environments.ts
        account = boto3.client("sts").get_caller_identity()["Account"]
        bucket = f"eagle-eval-artifacts-{account}-dev"

        # Upload results JSON
        s3.upload_file(results_path, bucket, f"e2e-judge/results/{run_id}.json")
        s3.upload_file(results_path, bucket, "e2e-judge/latest.json")

        # Upload screenshots
        for root, dirs, files in os.walk(screenshots_dir):
            for fname in files:
                if fname.endswith(".png"):
                    filepath = os.path.join(root, fname)
                    rel = os.path.relpath(filepath, os.path.dirname(screenshots_dir))
                    s3_key = f"e2e-judge/screenshots/{rel}".replace("\\", "/")
                    s3.upload_file(filepath, bucket, s3_key)

        print(f"  [s3] Uploaded to s3://{bucket}/e2e-judge/")
    except Exception as e:
        print(f"  [s3] Upload failed (non-fatal): {e}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="E2E Judge — Screenshot + Vision evaluation pipeline for EAGLE"
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get(
            "BASE_URL",
            "http://internal-eaglec-front-teerfwosqs71-1457581412.us-east-1.elb.amazonaws.com",
        ),
        help="Target URL (deployed ALB or localhost)",
    )
    parser.add_argument(
        "--auth-email",
        default=os.environ.get("EAGLE_TEST_EMAIL"),
        help="Cognito login email",
    )
    parser.add_argument(
        "--auth-password",
        default=os.environ.get("EAGLE_TEST_PASSWORD"),
        help="Cognito login password",
    )
    parser.add_argument(
        "--journeys",
        default="all",
        help="Comma-separated journey names, or 'all' (default: all)",
    )
    parser.add_argument("--headed", action="store_true", help="Run with visible browser")
    parser.add_argument("--purge-cache", action="store_true", help="Clear judge cache before run")
    parser.add_argument("--upload-s3", action="store_true", help="Upload results to S3")
    parser.add_argument("--output", default=None, help="Output directory for results")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    journeys = list_journeys() if args.journeys == "all" else args.journeys.split(",")

    asyncio.run(
        run_pipeline(
            base_url=args.base_url,
            journeys=journeys,
            auth_email=args.auth_email,
            auth_password=args.auth_password,
            headed=args.headed,
            purge_cache=args.purge_cache,
            upload_s3=args.upload_s3,
            output_dir=args.output,
        )
    )


if __name__ == "__main__":
    main()
