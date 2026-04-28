"""
post_deploy_smoke.py — devbox-side post-deploy smoke harness.

Runs from inside the VPC against the deployed dev/qa ALB. Validates the
backend wire contract for the research tool, drives the frontend chat UI
end-to-end, captures screenshots at key moments, and uploads everything to
the eval-artifacts S3 bucket so reviewers can audit a deploy without VPN.

Pattern alignment:
- Sibling of e2e_judge_orchestrator (Playwright + vision) and the Q4/Q5
  rerun harness (deployed-backend probes).
- Self-contained — no imports from app/, so it works from a fresh checkout
  on the devbox.

Usage (on the devbox):
    python -m tests.post_deploy_smoke \
        --backend-url http://internal-EagleC-Backe-...elb.amazonaws.com \
        --frontend-url http://internal-EagleC-Front-...elb.amazonaws.com \
        --scenario research_source_transparency \
        --upload

Optional auth (when DEV_MODE is off):
    EAGLE_TEST_EMAIL=... EAGLE_TEST_PASSWORD=... COGNITO_CLIENT_ID=... \
        python -m tests.post_deploy_smoke ... --auth

Exits 0 on PASS, 1 on FAIL. Writes structured JSON to --out (default
/tmp/post_deploy_smoke.json) so the SSM driver can pull it back.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

# ── Scenario registry ─────────────────────────────────────────────────────────
# Each scenario is a self-contained probe: the query to send, optional
# wire-shape assertions, and Playwright moments to screenshot.
# Add new scenarios here as feature changes ship.

SCENARIOS: dict[str, dict[str, Any]] = {
    "research_source_transparency": {
        "label": "Research source transparency (PR #161)",
        "query": (
            "What are the special rules for issuing a sole source on a "
            "multi-award IDIQ under FAR 16.505?"
        ),
        "expects": {
            # The new wire fields the frontend Sources table reads. Each must
            # appear on every entry of fetched_documents/kb_results in the
            # research tool_result payload.
            "research_packet_fields": [
                "lane",
                "score",
                "score_pct",
                "rationale",
                "read",
            ],
            "meta_fields": ["lane_breakdown", "total_surfaced"],
            "min_total_surfaced": 4,
        },
    },
}


# ── Pass/fail tracking ────────────────────────────────────────────────────────


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class SmokeResult:
    scenario: str
    started_at: str
    finished_at: str = ""
    backend_url: str = ""
    frontend_url: str = ""
    git_sha: str = ""
    checks: list[CheckResult] = field(default_factory=list)
    screenshots: list[dict[str, str]] = field(default_factory=list)
    s3_prefix: str = ""
    backend_response_status: int = 0
    research_packet_summary: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks) and not self.error

    def add_check(self, name: str, passed: bool, detail: str = "") -> None:
        self.checks.append(CheckResult(name, passed, detail))
        marker = "PASS" if passed else "FAIL"
        print(f"  [{marker}] {name}{(' — ' + detail) if detail else ''}")

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["passed"] = self.passed
        return d


# ── Cognito (optional) ────────────────────────────────────────────────────────


def cognito_login(email: str, password: str) -> str:
    """Return a Cognito IdToken via USER_PASSWORD_AUTH. Requires COGNITO_CLIENT_ID env."""
    import boto3  # local import: only used in --auth path

    client_id = os.environ.get("COGNITO_CLIENT_ID")
    if not client_id:
        raise RuntimeError("COGNITO_CLIENT_ID is required when --auth is set")
    region = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
    cog = boto3.client("cognito-idp", region_name=region)
    resp = cog.initiate_auth(
        ClientId=client_id,
        AuthFlow="USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": email, "PASSWORD": password},
    )
    return resp["AuthenticationResult"]["IdToken"]


# ── Backend probe ─────────────────────────────────────────────────────────────


def probe_backend(result: SmokeResult, backend_url: str, scenario: dict, *, token: str | None) -> dict:
    """POST /api/chat/stream and parse SSE; validate the research wire shape.

    REST `/api/chat` returns only the final text + tools_called list — no
    tool_result bodies — so we hit the SSE endpoint and walk the event stream
    for `tool_use`/`tool_result` events that carry the research packet.
    """
    headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    body = {
        "message": scenario["query"],
        "session_id": f"smoke-{uuid.uuid4().hex[:12]}",
    }
    url = f"{backend_url}/api/chat/stream"
    print(f"\n=== Backend probe: POST {url} (SSE) ===")
    print(f"    query: {scenario['query'][:80]}...")

    events: list[dict] = []
    raw_lines = 0
    t0 = time.monotonic()
    status = 0
    try:
        with httpx.Client(timeout=300.0, follow_redirects=True) as client:
            with client.stream("POST", url, json=body, headers=headers) as resp:
                status = resp.status_code
                if resp.is_success:
                    for line in resp.iter_lines():
                        raw_lines += 1
                        if not line or not line.startswith("data:"):
                            continue
                        payload = line[5:].strip()
                        if not payload or payload == "[DONE]":
                            continue
                        try:
                            events.append(json.loads(payload))
                        except json.JSONDecodeError:
                            # Tolerate non-JSON data lines (e.g. comments)
                            pass
    except httpx.HTTPError as exc:
        result.add_check("backend_2xx", False, f"http error: {exc}")
        return {}
    elapsed = time.monotonic() - t0

    result.backend_response_status = status
    print(f"    status: {status}  elapsed: {elapsed:.1f}s  events: {len(events)}  raw_lines: {raw_lines}")
    result.add_check(
        "backend_2xx",
        200 <= status < 300,
        f"status={status}, elapsed={elapsed:.1f}s",
    )
    if not (200 <= status < 300):
        return {}

    result.add_check(
        "backend_sse_events_parsed",
        len(events) > 0,
        f"{len(events)} JSON events from {raw_lines} raw lines",
    )

    # Persist a sample of events for offline inspection — invaluable when the
    # walker can't find what it's looking for. Sample = first 20 events +
    # any event whose serialized form is "research-shaped".
    try:
        sample = list(events[:20])
        for e in events:
            blob = json.dumps(e)[:2000]
            if "kb_results" in blob or "fetched_documents" in blob or "tool_use" in blob.lower():
                sample.append(e)
                if len(sample) >= 60:
                    break
        sample_path = Path("/tmp/post_deploy_smoke_events.json")
        sample_path.write_text(json.dumps(sample[:60], indent=2, default=str))
        print(f"    event sample (60 max) -> {sample_path}")
    except Exception as exc:  # noqa: BLE001
        print(f"    event sample dump failed: {exc}")

    # The SSE tool_result for `research` carries the *emit summary* — that's
    # what the backend pushes through MultiAgentStreamWriter via
    # `_emit("research", {...})`. Per-entry lane/score/rationale/read fields
    # are LLM-only (they're in the @tool's json.dumps return, not in the
    # SSE summary). What we CAN prove from the summary:
    #   - the new lane_breakdown dict is populated
    #   - total_surfaced > legacy 8 cap when enough candidates exist
    # That proves the transparency feature is live on the deployed backend.
    research_summary = _extract_research_summary(events)
    if research_summary is None:
        type_counts: dict[str, int] = {}
        for e in events:
            t = e.get("type") or e.get("event") or e.get("kind") or "(none)"
            type_counts[str(t)] = type_counts.get(str(t), 0) + 1
        top_types = sorted(type_counts.items(), key=lambda kv: -kv[1])[:6]
        result.add_check(
            "research_tool_invoked",
            False,
            "no research tool_result — top event types: "
            + ", ".join(f"{k}={v}" for k, v in top_types),
        )
        return {"events": events}
    result.add_check("research_tool_invoked", True)

    expects = scenario.get("expects", {})

    # lane_breakdown must be present and non-empty
    lane_breakdown = research_summary.get("lane_breakdown") or {}
    result.add_check(
        "research_lane_breakdown_populated",
        bool(lane_breakdown) and isinstance(lane_breakdown, dict),
        f"lane_breakdown={lane_breakdown}",
    )

    # total_surfaced clears the runner-up bar
    min_surfaced = expects.get("min_total_surfaced", 0)
    total_surfaced = research_summary.get("total_surfaced", 0)
    result.add_check(
        "research_surfaces_runner_ups",
        total_surfaced >= min_surfaced,
        f"total_surfaced={total_surfaced} (min={min_surfaced})",
    )

    # `sources` per-entry array (PR #164) — the slim records the frontend
    # Sources table actually renders. Each row must carry the display fields.
    sources = research_summary.get("sources") or []
    required_row_fields = ["title", "lane", "score_pct", "read"]
    rows_with_all = [
        r for r in sources
        if isinstance(r, dict) and all(f in r for f in required_row_fields)
    ]
    result.add_check(
        "research_sources_array_present",
        isinstance(sources, list) and len(sources) > 0,
        f"len(sources)={len(sources)}",
    )
    result.add_check(
        "research_sources_rows_well_formed",
        len(rows_with_all) == len(sources) and len(sources) > 0,
        f"{len(rows_with_all)}/{len(sources)} rows carry {required_row_fields}",
    )

    # Summary captured on the result for the JSON artifact
    result.research_packet_summary = {
        "fetched_count": research_summary.get("fetched_count"),
        "kb_results_count": research_summary.get("kb_results_count"),
        "lane_breakdown": lane_breakdown,
        "total_surfaced": total_surfaced,
        "sources_len": len(sources),
        "first_3_sources": [
            {
                "title": (r.get("title") or "")[:80],
                "lane": r.get("lane"),
                "score_pct": r.get("score_pct"),
                "read": r.get("read"),
            }
            for r in sources[:3] if isinstance(r, dict)
        ],
        "semantic_hit_count": research_summary.get("semantic_hit_count"),
        "semantic_fetched_count": research_summary.get("semantic_fetched_count"),
        "duration_seconds": research_summary.get("duration_seconds"),
    }
    return {"events": events, "research_summary": research_summary}


def _extract_research_packet(payload: Any) -> dict | None:
    """Walk a response payload looking for a research tool_result body.

    Different response wrappers flow through depending on whether the call
    hit /api/chat (REST) or an SSE wrapper. We look for any dict that
    contains both `kb_results` and `fetched_documents` (the research packet
    signature) and return the first one we find.
    """

    def walk(node: Any) -> dict | None:
        if isinstance(node, dict):
            if "kb_results" in node and "fetched_documents" in node:
                return node
            for v in node.values():
                hit = walk(v)
                if hit is not None:
                    return hit
            # tool_results often store the body as a JSON string
            for key in ("content", "tool_result", "result", "body"):
                if isinstance(node.get(key), str):
                    try:
                        parsed = json.loads(node[key])
                    except (ValueError, TypeError):
                        continue
                    hit = walk(parsed)
                    if hit is not None:
                        return hit
        elif isinstance(node, list):
            for item in node:
                hit = walk(item)
                if hit is not None:
                    return hit
        return None

    return walk(payload)


def _extract_research_summary(events: list[dict]) -> dict | None:
    """Find the SSE tool_result for `research` and return its summary dict.

    Backend SSE shape (from MultiAgentStreamWriter):
        {"type": "tool_result",
         "tool_result": {"name": "research", "result": {...summary dict...}}}

    The summary dict carries `kb_results_count`, `fetched_count`,
    `lane_breakdown`, `total_surfaced`, etc. — the fields that prove the
    source-transparency feature is live on the deployed container.

    If multiple `research` tool_results exist (e.g. supervisor + subagent),
    return the LAST one — that's the one with the most complete summary.
    """
    last: dict | None = None
    for e in events:
        if not isinstance(e, dict):
            continue
        if e.get("type") != "tool_result":
            continue
        tr = e.get("tool_result") or {}
        if tr.get("name") != "research":
            continue
        body = tr.get("result")
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except (ValueError, TypeError):
                continue
        if isinstance(body, dict):
            last = body
    return last


# ── Frontend probe (Playwright) ───────────────────────────────────────────────


async def probe_frontend(
    result: SmokeResult,
    frontend_url: str,
    scenario: dict,
    out_dir: Path,
    *,
    token: str | None,
) -> None:
    """Drive the chat UI through the scenario, capture 4 screenshots."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        result.add_check(
            "frontend_playwright_available",
            False,
            "playwright not installed on devbox — pip install playwright && playwright install chromium",
        )
        return
    result.add_check("frontend_playwright_available", True)

    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n=== Frontend probe: Playwright @ {frontend_url} ===")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(viewport={"width": 1440, "height": 900})

        # If a token is supplied, prime localStorage for the dev-mode auth path.
        # Frontend reads `eagle.idToken` for Bearer-auth requests in non-DEV envs.
        if token:
            await context.add_init_script(
                f"window.localStorage.setItem('eagle.idToken', {json.dumps(token)});"
            )

        page = await context.new_page()
        try:
            await page.goto(frontend_url, wait_until="networkidle", timeout=60_000)
        except Exception as exc:
            result.add_check("frontend_loads", False, str(exc)[:200])
            await browser.close()
            return
        result.add_check("frontend_loads", True, await page.title())

        await _shot(result, page, out_dir, "01-empty")

        # Sign-in handling — the deployed dev/qa frontend gates the chat behind
        # the Cognito sign-in form. If we land on it, fill EAGLE_TEST_EMAIL +
        # EAGLE_TEST_PASSWORD and submit. The orchestrator's --auth path
        # already minted a JWT for the backend; the frontend has its own
        # email+password form which we drive here.
        signin_visible = await page.get_by_text("Sign in", exact=False).count() > 0
        if signin_visible:
            email_env = os.environ.get("EAGLE_TEST_EMAIL")
            pw_env = os.environ.get("EAGLE_TEST_PASSWORD")
            if not (email_env and pw_env):
                result.add_check(
                    "frontend_signin_credentials",
                    False,
                    "EAGLE_TEST_EMAIL/PASSWORD not set; cannot pass sign-in gate",
                )
                await browser.close()
                return
            try:
                await page.get_by_placeholder("you@nih.gov").fill(email_env)
                await page.get_by_placeholder("••••••••").fill(pw_env)
                await page.get_by_role("button", name="Sign in").click()
                # Wait for the Sign-in form to disappear (auth successful and
                # the app navigated). networkidle alone returns early during
                # the brief gap between the auth POST and the chat-app fetch
                # — wait for an actual signal of post-auth UI.
                try:
                    await page.locator("text=Sign in").first.wait_for(
                        state="detached", timeout=45_000,
                    )
                except Exception:
                    # Some app shells re-use "Sign in" elsewhere; fall back to
                    # waiting for the chat textarea or any chat marker to
                    # appear. We swallow exceptions — the textarea check
                    # below is the source of truth.
                    pass
                await page.wait_for_load_state("networkidle", timeout=30_000)
                # Small settle buffer so the screenshot captures the
                # post-redirect state, not the spinner.
                await page.wait_for_timeout(2000)
            except Exception as exc:
                result.add_check("frontend_signin", False, str(exc)[:200])
                await _shot(result, page, out_dir, "01b-post-signin")
                await browser.close()
                return
            result.add_check("frontend_signin", True)
            await _shot(result, page, out_dir, "01b-post-signin")

        # Post-signin lands on the home page (nav cards: Chat / Packages /
        # Documents / Knowledge Base). Click the Chat nav link to reach the
        # textarea. The link appears both in the top nav and as a card; use
        # the nav locator since it's stable.
        try:
            chat_nav = page.get_by_role("link", name="Chat", exact=True)
            if await chat_nav.count() > 0:
                await chat_nav.first.click()
                await page.wait_for_load_state("networkidle", timeout=20_000)
                await page.wait_for_timeout(1500)
        except Exception:
            pass

        # Find the chat textarea by placeholder fragment
        textarea = page.get_by_placeholder("Ask EAGLE", exact=False)
        try:
            await textarea.wait_for(timeout=60_000)
        except Exception as exc:
            # Capture where the page actually ended up — invaluable when the
            # post-signin redirect lands somewhere unexpected.
            try:
                stuck_url = page.url
            except Exception:
                stuck_url = "?"
            await _shot(result, page, out_dir, "02-textarea-timeout")
            result.add_check(
                "chat_textarea_present",
                False,
                f"timeout @ url={stuck_url}: {str(exc)[:160]}",
            )
            await browser.close()
            return
        result.add_check("chat_textarea_present", True)

        await textarea.fill(scenario["query"])
        await _shot(result, page, out_dir, "02-typed")

        await textarea.press("Enter")

        # Streaming snapshot — wait briefly for the tool card to appear
        try:
            await page.wait_for_timeout(10_000)
            await _shot(result, page, out_dir, "03-streaming")
        except Exception:
            pass

        # Wait for streaming to finish. The textarea is `disabled` while
        # streaming (placeholder = "Waiting for response…"); when streaming
        # completes it re-enables and placeholder reverts to "Ask EAGLE…".
        # That's our completion signal. Cap at 4 minutes — backend SSE probe
        # above ran 150–220s, UI needs the same plus a few seconds of
        # post-stream rendering.
        deadline = time.monotonic() + 240
        complete = False
        last_signal = ""
        while time.monotonic() < deadline:
            try:
                # Streaming = textarea is disabled. When re-enabled, stream is done.
                ta = page.get_by_placeholder("Ask EAGLE", exact=False)
                if await ta.count() > 0:
                    is_disabled = await ta.first.is_disabled()
                    if not is_disabled:
                        complete = True
                        last_signal = "textarea re-enabled (stream complete)"
                        break
            except Exception:
                pass
            await page.wait_for_timeout(3_000)

        result.add_check(
            "stream_completed",
            complete,
            (last_signal or "timeout waiting 240s for stream completion"),
        )
        # Settle buffer so any final renders / animations land.
        await page.wait_for_timeout(3_000)
        await _shot(result, page, out_dir, "04-complete")

        # Find the Research tool chip in the chat thread. The chip is rendered
        # by ToolUseDisplay with data-testid="tool-chip" and label "Research".
        # Click it to open the modal that contains ResearchResultPanel — that's
        # where the Sources table lives.
        chip_clicked = False
        try:
            research_chip = page.locator('[data-testid="tool-chip"]').filter(
                has_text="Research"
            ).first
            await research_chip.wait_for(state="visible", timeout=15_000)
            await research_chip.scroll_into_view_if_needed()
            await page.wait_for_timeout(300)
            await research_chip.click()
            chip_clicked = True
        except Exception as exc:
            print(f"    chip click FAILED: {exc}")

        result.add_check(
            "research_chip_clicked",
            chip_clicked,
            "Research chip located + clicked" if chip_clicked else "chip not found",
        )

        if chip_clicked:
            # Wait for the modal to render (heading "📖 Research")
            try:
                modal_heading = page.get_by_text("📖 Research", exact=False).first
                await modal_heading.wait_for(state="visible", timeout=10_000)
                await page.wait_for_timeout(1500)
                await _shot(result, page, out_dir, "05-modal-research")
            except Exception as exc:
                print(f"    modal capture FAILED: {exc}")
                await _shot(result, page, out_dir, "05-modal-research")

            # Try to clip directly to the Sources table inside the modal.
            try:
                sources_header = page.locator("text=/Sources \\(\\d+\\)/").first
                if await sources_header.count() > 0:
                    await sources_header.scroll_into_view_if_needed()
                    await page.wait_for_timeout(400)
                    # The table is the parent flex container with the rows;
                    # clip to it via the surrounding card.
                    table_card = sources_header.locator(
                        "xpath=ancestor::div[contains(@class,'px-3') and contains(@class,'py-2')][1]",
                    )
                    box = await table_card.bounding_box()
                    if box:
                        shot_path = out_dir / "06-sources-table.png"
                        # Don't clip below viewport — page screenshot honors clip
                        # but if the card extends past viewport we want a full
                        # capture so the rows are visible. Use full_page=True
                        # then we still get clip.
                        await page.screenshot(
                            path=str(shot_path),
                            full_page=True,
                            clip={
                                "x": max(0, box["x"] - 8),
                                "y": max(0, box["y"] - 8),
                                "width": min(1440, box["width"] + 16),
                                "height": box["height"] + 16,
                            },
                        )
                        result.screenshots.append({
                            "name": "06-sources-table",
                            "path": str(shot_path),
                        })
                        print(f"    snap: 06-sources-table -> {shot_path.name} (clipped)")
                else:
                    # If no Sources(N) header, capture whatever the modal shows
                    # so we can debug what the panel rendered.
                    print("    no 'Sources (N)' header found; capturing whole modal")
            except Exception as exc:
                print(f"    snap 06-sources-table FAILED: {exc}")

        await browser.close()


async def _shot(
    result: SmokeResult,
    page: Any,
    out_dir: Path,
    stem: str,
) -> None:
    path = out_dir / f"{stem}.png"
    try:
        await page.screenshot(path=str(path), full_page=False)
        result.screenshots.append({"name": stem, "path": str(path)})
        print(f"    snap: {stem} -> {path.name}")
    except Exception as exc:
        print(f"    snap FAILED: {stem}: {exc}")


# ── S3 upload ─────────────────────────────────────────────────────────────────


def upload_artifacts(result: SmokeResult, out_dir: Path, bucket: str, prefix: str) -> None:
    """Upload all PNGs + the result JSON to s3://{bucket}/{prefix}/."""
    import boto3

    s3 = boto3.client("s3", region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
    print(f"\n=== Uploading to s3://{bucket}/{prefix}/ ===")

    for shot in result.screenshots:
        local = Path(shot["path"])
        if not local.exists():
            continue
        key = f"{prefix}/{local.name}"
        s3.upload_file(
            str(local),
            bucket,
            key,
            ExtraArgs={"ContentType": "image/png"},
        )
        shot["s3_uri"] = f"s3://{bucket}/{key}"
        print(f"    up: {key}")

    # Event sample dump (when present) — useful for debugging walker misses
    events_dump = Path("/tmp/post_deploy_smoke_events.json")
    if events_dump.exists():
        s3.upload_file(
            str(events_dump),
            bucket,
            f"{prefix}/events_sample.json",
            ExtraArgs={"ContentType": "application/json"},
        )
        print(f"    up: {prefix}/events_sample.json")

    # Upload result JSON last, with screenshots' s3 URIs already populated
    result.s3_prefix = f"s3://{bucket}/{prefix}/"
    s3.put_object(
        Bucket=bucket,
        Key=f"{prefix}/result.json",
        Body=json.dumps(result.to_dict(), indent=2, default=str).encode(),
        ContentType="application/json",
    )
    print(f"    up: {prefix}/result.json")


# ── Main ──────────────────────────────────────────────────────────────────────


def _git_sha() -> str:
    try:
        sha = (
            (Path(__file__).resolve().parents[2] / ".git" / "HEAD").read_text().strip()
        )
        if sha.startswith("ref: "):
            ref = sha[5:]
            sha = (
                (Path(__file__).resolve().parents[2] / ".git" / ref).read_text().strip()
            )
        return sha[:12]
    except Exception:
        return "unknown"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--backend-url", required=True)
    p.add_argument("--frontend-url", required=True)
    p.add_argument(
        "--scenario",
        default="research_source_transparency",
        choices=sorted(SCENARIOS.keys()),
    )
    p.add_argument("--auth", action="store_true", help="Mint a Cognito IdToken (requires EAGLE_TEST_EMAIL/PASSWORD + COGNITO_CLIENT_ID).")
    p.add_argument("--upload", action="store_true", help="Upload artifacts to the eval bucket.")
    p.add_argument(
        "--bucket",
        default=os.environ.get("EAGLE_EVAL_BUCKET", "eagle-eval-artifacts-695681773636-dev"),
    )
    p.add_argument("--prefix", default="", help="S3 key prefix override; default smoke/{scenario}/{ts}/")
    p.add_argument("--out", default="/tmp/post_deploy_smoke.json")
    p.add_argument("--shots-dir", default="/tmp/post_deploy_smoke_shots")
    args = p.parse_args()

    scenario = SCENARIOS[args.scenario]
    started = datetime.now(timezone.utc).isoformat()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    prefix = args.prefix or f"smoke/{args.scenario}/{ts}"

    result = SmokeResult(
        scenario=args.scenario,
        started_at=started,
        backend_url=args.backend_url,
        frontend_url=args.frontend_url,
        git_sha=_git_sha(),
    )

    print(f"=== post-deploy smoke: {scenario['label']} ===")
    print(f"    backend  = {args.backend_url}")
    print(f"    frontend = {args.frontend_url}")
    print(f"    git_sha  = {result.git_sha}")

    token = None
    if args.auth:
        email = os.environ.get("EAGLE_TEST_EMAIL")
        pwd = os.environ.get("EAGLE_TEST_PASSWORD")
        if not (email and pwd):
            print("ERROR: --auth requires EAGLE_TEST_EMAIL and EAGLE_TEST_PASSWORD env vars")
            return 2
        try:
            token = cognito_login(email, pwd)
            print("    cognito IdToken acquired")
        except Exception as exc:
            result.error = f"cognito_login_failed: {exc}"
            print(f"ERROR: {result.error}")

    try:
        probe_backend(result, args.backend_url, scenario, token=token)
    except Exception as exc:
        result.error = f"backend_probe_failed: {exc}"
        result.add_check("backend_probe_no_exception", False, str(exc)[:200])

    shots_dir = Path(args.shots_dir) / args.scenario / ts
    try:
        asyncio.run(probe_frontend(result, args.frontend_url, scenario, shots_dir, token=token))
    except Exception as exc:
        result.error = f"frontend_probe_failed: {exc}"
        result.add_check("frontend_probe_no_exception", False, str(exc)[:200])

    if args.upload:
        try:
            upload_artifacts(result, shots_dir, args.bucket, prefix)
        except Exception as exc:
            print(f"WARN: upload failed: {exc}")

    result.finished_at = datetime.now(timezone.utc).isoformat()

    # Write structured result
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result.to_dict(), indent=2, default=str))
    print(f"\n=== result -> {out_path} ===")
    passed = sum(1 for c in result.checks if c.passed)
    failed = sum(1 for c in result.checks if not c.passed)
    print(f"    {passed} passed, {failed} failed; overall = {'PASS' if result.passed else 'FAIL'}")
    if result.s3_prefix:
        print(f"    artifacts: {result.s3_prefix}")

    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
