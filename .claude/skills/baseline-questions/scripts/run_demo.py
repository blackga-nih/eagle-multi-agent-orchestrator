"""Run an EAGLE demo scenario end-to-end against a live server.

Extends the baseline-questions skill for multi-turn demo evaluation:

  1. Parse a demo-script .docx into discrete user turns + reference EAGLE responses
  2. Replay the user turns against the live backend in ONE session (multi-turn)
  3. Optionally capture Playwright screenshots of the chat UI at each turn
  4. Score each EAGLE response vs the reference on 4 dimensions via Bedrock/Sonnet
  5. Emit a self-contained HTML report with side-by-side comparison + screenshots

Output layout:
    scripts/demo_eval_results/{run_id}/
        demo_turns.json      — parsed turns from the docx (for inspection/edit)
        results.json         — per-turn API responses + metadata
        scores.json          — per-turn scores + verdicts
        screenshots/         — per-turn PNGs (if --screenshots)
        demo_report.html     — final report

Usage:
    python .claude/skills/baseline-questions/scripts/run_demo.py \\
        --demo-script "c:/Users/blackga/Downloads/EAGLE Demo Script 20260409.docx" \\
        --server https://DEV-ALB-URL \\
        --screenshots

Env vars:
    EAGLE_TEST_EMAIL, EAGLE_TEST_PASSWORD — Cognito auth for Playwright
    AWS_REGION (default: us-east-1) — Bedrock region for scoring
    DEMO_JUDGE_MODEL (default: us.anthropic.claude-sonnet-4-6) — LLM scoring model
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any

import httpx

sys.stdout.reconfigure(encoding="utf-8")


# ---------------------------------------------------------------------------
# Constants (mirrored from generate_report.py for visual consistency)
# ---------------------------------------------------------------------------

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
    "manage_package": ("#283593", "#E8EAF6"),
    "query_package_state": ("#283593", "#E8EAF6"),
}

DOC_TYPE_COLORS = {
    "compliance-strategist": ("#1565C0", "#E3F2FD", "Compliance"),
    "legal-counselor": ("#AD1457", "#FCE4EC", "Legal"),
    "financial-advisor": ("#2E7D32", "#E8F5E9", "Financial"),
    "market-researcher": ("#E65100", "#FFF3E0", "Market"),
    "market-intelligence": ("#E65100", "#FFF3E0", "Market"),
    "document-drafter": ("#6A1B9A", "#F3E5F5", "Drafting"),
    "supervisor-core": ("#37474F", "#ECEFF1", "Core"),
    "agents": ("#795548", "#EFEBE9", "Agents"),
}


class BackendUnreachableError(Exception):
    """Raised when the EAGLE backend returns 5xx or refuses connections.

    Aborts the whole run once triggered — subsequent turns will fail identically.
    """


# ---------------------------------------------------------------------------
# 1. Docx parser
# ---------------------------------------------------------------------------

# EAGLE response block markers. Any paragraph matching one of these is treated
# as internal/output metadata, not user speech. Groups of consecutive markers
# form "marker blocks" that delimit turns.
_MARKER_WORDS = {"reasoning", "internal", "think", "no output"}
_KB_PATH_RE = re.compile(r"^[\w-]+/[\w-]+/[\w._-]+\.\w+$")
_CHARS_RE = re.compile(r"^\d+\s*chars?\.?$", re.IGNORECASE)

# STRONG user-turn start signals. Only unambiguous user-intent openers are
# listed here — this regex is used to split inter-block spans into "EAGLE
# response tail" vs "next user turn head". Keep it conservative: false
# positives (EAGLE lines matched as user) are worse than false negatives
# (user lines appended to EAGLE). Hand-edit demo_turns.json if a split
# is wrong, or override with --turns-json PATH.
_USER_START_RE = re.compile(
    r"^("
    # Explicit first-person intent verbs
    r"I\s+need\b|I\s+want\b|I\s+would\b|I\s+will\b|I\s+can\b|"
    r"I['\u2019]d\s+like\b|I['\u2019]d\s+want\b|I['\u2019]d\s+prefer\b|"
    r"I['\u2019]m\s+looking\b|I['\u2019]m\s+trying\b|I['\u2019]m\s+working\b|"
    r"I['\u2019]ve\s+got\b|I['\u2019]ve\s+been\b|"
    r"I\s+think\s+we\b|I\s+have\b|"
    # Requests / commands directed at EAGLE
    r"Can\s+you\b|Could\s+you\b|Would\s+you\b|Will\s+you\b|"
    r"Please\b|"
    r"Draft\b|Generate\b|Produce\b|Write\b|Create\b|Build\b|"
    r"Give\s+me\b|Show\s+me\b|Walk\s+me\b|Tell\s+me\b|"
    # Context framings
    r"Here['\u2019]s\s+(what|how|the|my|where)\b|"
    r"The\s+requirement\b|The\s+scenario\b|"
    r"For\s+this\s+(acquisition|procurement|contract|scenario)\b|"
    # First-person plural intent
    r"We\s+need\b|We\s+want\b|We['\u2019]re\s+looking\b|We\s+have\b|"
    # Explicit demo-script framings
    r"This\s+conversation\b|Use\s+the\s+RFO\b|"
    r"Make\s+sure\b|Also\s+make\b|Also[,.]"
    r")"
)


def _is_marker_paragraph(text: str) -> bool:
    """Return True if this paragraph is an EAGLE internal marker or metadata line."""
    if not text:
        return False
    stripped = text.strip()
    lowered = stripped.lower().rstrip("\u2026.").strip()
    if lowered in _MARKER_WORDS:
        return True
    if _KB_PATH_RE.match(stripped):
        return True
    if _CHARS_RE.match(stripped):
        return True
    if lowered.startswith("let me pull"):
        return True
    if lowered.startswith("let me check"):
        return True
    return False


def _extract_reference_docs(eagle_block_paragraphs: list[str]) -> list[dict]:
    """Pull KB doc paths out of an EAGLE reference response block.

    Looks for the pattern: `path/to/file.txt` followed by `NNNN chars`.
    Returns [{"path": ..., "chars": ...}, ...].
    """
    docs: list[dict] = []
    seen: set[str] = set()
    i = 0
    while i < len(eagle_block_paragraphs):
        line = eagle_block_paragraphs[i].strip()
        if _KB_PATH_RE.match(line) and line not in seen:
            chars = 0
            if i + 1 < len(eagle_block_paragraphs):
                m = _CHARS_RE.match(eagle_block_paragraphs[i + 1].strip())
                if m:
                    # Extract the number portion
                    mnum = re.match(r"^(\d+)", eagle_block_paragraphs[i + 1].strip())
                    if mnum:
                        chars = int(mnum.group(1))
                    i += 1
            docs.append({"path": line, "chars": chars})
            seen.add(line)
        i += 1
    return docs


def _is_marker_line(text: str) -> bool:
    """Narrow marker check used for turn-boundary detection.

    Only the pure word markers ('Reasoning', 'internal', 'think', 'no output')
    delimit turns. KB paths and char counts are metadata *inside* an EAGLE
    response, not turn boundaries.
    """
    if not text:
        return False
    lowered = text.strip().lower().rstrip("\u2026.").strip()
    return lowered in _MARKER_WORDS


def _find_marker_blocks(paras: list[str]) -> list[tuple[int, int]]:
    """Return list of (start, end) inclusive paragraph indices for each
    contiguous run of marker-word lines. Each block marks the boundary
    between a user turn and the following EAGLE response.
    """
    indices = [i for i, p in enumerate(paras) if _is_marker_line(p)]
    if not indices:
        return []
    blocks: list[tuple[int, int]] = []
    cur_start = indices[0]
    cur_end = indices[0]
    for i in indices[1:]:
        if i == cur_end + 1:
            cur_end = i
        else:
            blocks.append((cur_start, cur_end))
            cur_start = cur_end = i
    blocks.append((cur_start, cur_end))
    return blocks


def _find_user_start(paras: list[str], lo: int, hi: int) -> int:
    """Within paras[lo:hi], find the first index matching a strong user-turn
    opener. Returns `hi` if no match — meaning: assume the whole span is
    EAGLE response with no trailing user turn (only happens on the final
    trailing block).
    """
    for i in range(lo, hi):
        text = paras[i].strip()
        if not text:
            continue
        if _is_marker_paragraph(text):
            continue
        if _USER_START_RE.match(text):
            return i
    return hi


def parse_demo_docx(path: str) -> dict:
    """Parse a multi-turn demo-script docx into structured turns.

    Core insight: marker blocks ('Reasoning…', 'internal', 'think', 'no output')
    are NOT 1:1 with turns. A single EAGLE turn can emit several marker blocks
    (one per internal tool call / deliberation step). The real turn-boundary
    signal is finding a user-intent paragraph between marker blocks.

    Algorithm:
      1. Find marker blocks — contiguous runs of marker-word paragraphs.
      2. Turn 1 user = paragraphs before the first marker block.
      3. Walk the inter-block spans in order:
           - span = paras[block_i_end+1 : block_i+1_start]
           - If span contains a paragraph matching _USER_START_RE, split it:
                 EAGLE response for current turn = span[0 : user_start]
                 Finalize current turn; begin new turn whose user_message
                 = span[user_start : end_of_span]
           - If no user-start in span, the span is EAGLE continuation of the
             *current* turn — append to current turn's EAGLE parts and continue.
      4. Trailing span (after last marker block) → EAGLE content of the last turn.

    Imperfect by design — the user-start heuristic may misplace a boundary
    by one paragraph. Inspect demo_turns.json after parsing and hand-edit
    if a turn split is wrong, or pass --turns-json PATH to override.

    Returns:
        {
            "metadata": {...},
            "turns": [
                {
                    "turn": 1,
                    "user_message": str,
                    "reference_response": str,
                    "reference_docs": [{"path": ..., "chars": ...}, ...],
                },
                ...
            ],
        }
    """
    try:
        from docx import Document  # python-docx
    except ImportError as e:
        raise RuntimeError(
            "python-docx not installed. Run: pip install python-docx"
        ) from e

    doc = Document(path)
    paras = [p.text.strip() for p in doc.paragraphs]
    blocks = _find_marker_blocks(paras)

    if not blocks:
        # Fallback: no markers at all. Treat whole doc as one user turn.
        user_text = "\n\n".join(p for p in paras if p)
        return {
            "metadata": {
                "path": str(path),
                "total_paragraphs": len(paras),
                "total_turns": 1,
                "marker_blocks": 0,
            },
            "turns": [
                {
                    "turn": 1,
                    "user_message": user_text,
                    "reference_response": "",
                    "reference_docs": [],
                }
            ],
        }

    def _clean(span_lo: int, span_hi: int, drop_markers: bool = True) -> list[str]:
        out: list[str] = []
        for j in range(span_lo, span_hi):
            p = paras[j]
            if not p:
                continue
            if drop_markers and _is_marker_paragraph(p):
                continue
            out.append(p)
        return out

    turns: list[dict] = []

    # --- Seed turn 1 with paragraphs before the first marker block ---
    first_mstart = blocks[0][0]
    current_user_paras = _clean(0, first_mstart)
    current_eagle_paras: list[str] = []
    turn_counter = 1

    for i, (mstart, mend) in enumerate(blocks):
        # Span of EAGLE content following THIS marker block, up to the next
        # marker block (or end of document for the last block).
        span_lo = mend + 1
        is_last_block = i + 1 >= len(blocks)
        span_hi = len(paras) if is_last_block else blocks[i + 1][0]

        if is_last_block:
            # Trailing span after the final marker block — this is, by
            # definition, all EAGLE content of the final turn. DO NOT look
            # for a user-start here (words like "Draft" appear legitimately
            # in EAGLE output for document drafts).
            user_start_idx = span_hi
        else:
            user_start_idx = _find_user_start(paras, span_lo, span_hi)

        if user_start_idx < span_hi:
            # Boundary found: current turn's EAGLE content ends at user_start_idx.
            current_eagle_paras.extend(_clean(span_lo, user_start_idx, drop_markers=False))
            turns.append(
                {
                    "turn": turn_counter,
                    "user_message": "\n\n".join(current_user_paras).strip(),
                    "reference_response": "\n\n".join(current_eagle_paras).strip(),
                    "reference_docs": _extract_reference_docs(current_eagle_paras),
                }
            )
            turn_counter += 1
            # Next user turn spans [user_start_idx : span_hi). EAGLE resets.
            current_user_paras = _clean(user_start_idx, span_hi)
            current_eagle_paras = []
        else:
            # No user text in this span → all of it is EAGLE continuation of
            # the current turn. Keep accumulating.
            current_eagle_paras.extend(_clean(span_lo, span_hi, drop_markers=False))

    # --- Finalize the final turn ---
    turns.append(
        {
            "turn": turn_counter,
            "user_message": "\n\n".join(current_user_paras).strip(),
            "reference_response": "\n\n".join(current_eagle_paras).strip(),
            "reference_docs": _extract_reference_docs(current_eagle_paras),
        }
    )

    return {
        "metadata": {
            "path": str(path),
            "total_paragraphs": len(paras),
            "total_turns": len(turns),
            "marker_blocks": len(blocks),
        },
        "turns": turns,
    }


# ---------------------------------------------------------------------------
# 2. Multi-turn API runner
# ---------------------------------------------------------------------------


async def _preflight_health_check(client: httpx.AsyncClient, base_url: str) -> None:
    """Hit /api/health and raise if the server isn't reachable."""
    try:
        r = await client.get(f"{base_url}/api/health", timeout=30)
        health = r.json()
        print(f"Server: {health.get('service', '?')} {health.get('version', '?')} - OK")
    except Exception as e:
        print(f"\nERROR: Server not reachable at {base_url}")
        print(f"  {e}")
        print("\nStart the server first:")
        print("  cd server && uvicorn app.main:app --reload --port 8000")
        sys.exit(1)


async def _run_turn(
    client: httpx.AsyncClient,
    base_url: str,
    tenant: str,
    session_id: str,
    turn: dict,
) -> dict:
    """POST one user message to the chat endpoint, return structured result."""
    turn_num = turn["turn"]
    user_msg = turn["user_message"]

    print(f"\n{'='*80}")
    print(f"Turn {turn_num}: {user_msg[:100]}")
    print(f"Session: {session_id}")
    print(f"{'='*80}")

    start = time.time()
    try:
        resp = await client.post(
            f"{base_url}/api/chat",
            json={"message": user_msg, "session_id": session_id},
            headers={
                "X-User-Id": "demo-eval",
                "X-Tenant-Id": tenant,
                "X-User-Email": "demo@eval.test",
                "X-User-Tier": "advanced",
            },
            timeout=600.0,
        )
        elapsed = time.time() - start

        if resp.status_code >= 500:
            raise BackendUnreachableError(
                f"Backend returned HTTP {resp.status_code} on Turn {turn_num} "
                f"after {elapsed:.1f}s. Aborting demo run."
            )

        data = resp.json()
        response_text = data.get("response", "")
        tools = data.get("tools_called", [])
        usage = data.get("usage", {})
        model = data.get("model", "unknown")

        print(f"\nCompleted in {elapsed:.1f}s | Model: {model}")
        print(f"Tools: {tools}")
        print(
            f"Tokens: in={usage.get('input_tokens', 0):,} "
            f"out={usage.get('output_tokens', 0):,}"
        )
        print(f"Response length: {len(response_text):,} chars")

        return {
            "turn": turn_num,
            "user_message": user_msg,
            "response": response_text,
            "tools": tools,
            "usage": usage,
            "model": model,
            "elapsed_s": round(elapsed, 1),
            "reference_response": turn["reference_response"],
            "reference_docs": turn["reference_docs"],
            "status": "ok",
        }
    except BackendUnreachableError:
        raise
    except (httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError) as e:
        elapsed = time.time() - start
        raise BackendUnreachableError(
            f"Connection to backend failed on Turn {turn_num} after {elapsed:.1f}s: {e}."
        ) from e
    except Exception as e:
        elapsed = time.time() - start
        print(f"\nERROR after {elapsed:.1f}s: {e}")
        return {
            "turn": turn_num,
            "user_message": user_msg,
            "response": f"ERROR: {e}",
            "tools": [],
            "usage": {},
            "model": "error",
            "elapsed_s": round(elapsed, 1),
            "reference_response": turn["reference_response"],
            "reference_docs": turn["reference_docs"],
            "status": "error",
        }


async def run_demo_session(
    base_url: str,
    tenant: str,
    turns: list[dict],
    pause_seconds: float = 3.0,
) -> tuple[str, list[dict]]:
    """Run all turns sequentially in ONE session. Returns (session_id, results)."""
    session_id = str(uuid.uuid4())
    results: list[dict] = []

    async with httpx.AsyncClient() as client:
        await _preflight_health_check(client, base_url)
        for turn in turns:
            try:
                r = await _run_turn(client, base_url, tenant, session_id, turn)
            except BackendUnreachableError as e:
                print(f"\n{'='*80}")
                print("BACKEND UNREACHABLE — ABORTING DEMO RUN")
                print(f"{'='*80}")
                print(f"  {e}")
                raise
            results.append(r)
            if pause_seconds > 0:
                await asyncio.sleep(pause_seconds)

    return session_id, results


# ---------------------------------------------------------------------------
# 3. Playwright screenshots (optional)
# ---------------------------------------------------------------------------


async def capture_demo_screenshots(
    base_url: str,
    turns: list[dict],
    output_dir: Path,
    headless: bool,
    auth_email: str | None,
    auth_password: str | None,
) -> dict[int, list[dict]]:
    """Drive the chat UI through each turn and save screenshots.

    Runs as a SEPARATE Playwright session from the API run — they do not
    share a session_id. API gives reliable response text, Playwright gives
    visual evidence. Returns {turn_num: [{"path": ..., "step": ...}, ...]}.

    Follows the journey_chat pattern from server/tests/e2e_judge_journeys.py:
      - textarea.fill(user_message) → pre-send screenshot
      - click "➤" send button
      - wait_with_interval_screenshots (30s intervals)
      - post-response screenshot
      - scroll to bottom → full-view screenshot
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError as e:
        raise RuntimeError(
            "Playwright not installed. Run: pip install playwright && playwright install chromium"
        ) from e

    screenshots_root = output_dir / "screenshots"
    screenshots_root.mkdir(parents=True, exist_ok=True)
    per_turn: dict[int, list[dict]] = {}

    auth_email = auth_email or os.environ.get("EAGLE_TEST_EMAIL")
    auth_password = auth_password or os.environ.get("EAGLE_TEST_PASSWORD")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()
        print(f"\n[screenshots] Chromium launched (headless={headless})")

        # --- Auth ---
        await page.goto(base_url, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        if "/login" in page.url:
            if not auth_email or not auth_password:
                await browser.close()
                raise RuntimeError(
                    "Auth required but no credentials. Set EAGLE_TEST_EMAIL/"
                    "EAGLE_TEST_PASSWORD or pass --auth-email/--auth-password."
                )
            print(f"[screenshots] Logging in as {auth_email}...")
            await page.fill("#email", auth_email)
            await page.fill("#password", auth_password)
            await page.click("button[type='submit']")
            for _ in range(20):
                await page.wait_for_timeout(1000)
                if "/login" not in page.url:
                    break
            else:
                await browser.close()
                raise RuntimeError("Login timed out — still on login page")
            print("[screenshots] Authenticated")
        else:
            print("[screenshots] No auth required (dev mode)")

        # --- Navigate to chat ---
        await page.goto(f"{base_url}/chat/", wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)

        # Try clicking New Chat to start fresh
        try:
            new_chat = page.get_by_role("button", name="New Chat")
            await new_chat.click(timeout=5000)
            await page.wait_for_timeout(1000)
        except Exception:
            pass

        textarea = page.locator("textarea")
        await textarea.wait_for(state="visible", timeout=10000)
        send_btn = page.locator("button:has-text('➤')")

        async def _shot(turn_num: int, step: str, description: str) -> dict:
            turn_dir = screenshots_root / f"turn{turn_num}"
            turn_dir.mkdir(parents=True, exist_ok=True)
            path = turn_dir / f"{step}.png"
            data = await page.screenshot(full_page=True)
            path.write_bytes(data)
            print(f"[screenshots] turn{turn_num}/{step} → {path.name}")
            return {
                "turn": turn_num,
                "step": step,
                "description": description,
                "path": str(path),
                "bytes": len(data),
            }

        async def _wait_for_response(timeout_ms: int, interval_ms: int, turn_num: int) -> list[dict]:
            """Take a screenshot every interval_ms until textarea is re-enabled."""
            shots: list[dict] = []
            start = time.monotonic()
            interval_idx = 0
            suffixes = "abcdefghijklmnopqrstuvwxyz"
            while True:
                elapsed_ms = (time.monotonic() - start) * 1000
                if elapsed_ms >= timeout_ms:
                    return shots

                # Check condition (textarea re-enabled = response done)
                try:
                    if await textarea.is_enabled():
                        return shots
                except Exception:
                    pass

                # Wait in 2s chunks, check condition between chunks
                remaining = min(interval_ms, timeout_ms - elapsed_ms)
                waited = 0
                while waited < remaining:
                    step_wait = min(2000, remaining - waited)
                    await page.wait_for_timeout(step_wait)
                    waited += step_wait
                    try:
                        if await textarea.is_enabled():
                            return shots
                    except Exception:
                        pass

                # Take interval screenshot
                suffix = suffixes[interval_idx] if interval_idx < 26 else str(interval_idx)
                elapsed_sec = int(time.monotonic() - start)
                s = await _shot(
                    turn_num,
                    f"03_streaming_{suffix}_{elapsed_sec}s",
                    f"Streaming response — {elapsed_sec}s elapsed",
                )
                shots.append(s)
                interval_idx += 1

        # --- Per-turn flow ---
        for idx, turn in enumerate(turns):
            turn_num = turn["turn"]
            is_last = idx == len(turns) - 1
            timeout_ms = 300_000 if is_last else 120_000

            shots: list[dict] = []

            # Fill message and pre-send screenshot
            await textarea.wait_for(state="visible", timeout=10000)
            await textarea.fill(turn["user_message"])
            shots.append(
                await _shot(turn_num, "01_pre_send", "User message typed — about to send")
            )

            # Click send
            await send_btn.click()
            await page.wait_for_timeout(3000)
            shots.append(
                await _shot(turn_num, "02_streaming_start", "Agent streaming started")
            )

            # Wait with interval screenshots
            streaming_shots = await _wait_for_response(
                timeout_ms=timeout_ms, interval_ms=30_000, turn_num=turn_num
            )
            shots.extend(streaming_shots)

            # Post-response + full-scroll
            await page.wait_for_timeout(2000)
            shots.append(
                await _shot(turn_num, "04_response_complete", "Response complete")
            )
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(1000)
            shots.append(
                await _shot(turn_num, "05_response_scrolled", "Response scrolled to bottom")
            )

            per_turn[turn_num] = shots

        await browser.close()
        print(f"[screenshots] Done. {sum(len(v) for v in per_turn.values())} shots captured.")

    return per_turn


# ---------------------------------------------------------------------------
# 4. LLM scoring via Bedrock converse
# ---------------------------------------------------------------------------


def parse_eagle_docs(response: str) -> list[str]:
    """Extract KB doc paths from an EAGLE response (s3 key form)."""
    docs: list[str] = []
    seen = set()
    for m in re.finditer(
        r"eagle-knowledge-base/approved/([\w-]+/[\w-]+/[\w._-]+\.\w+)", response
    ):
        path = m.group(1).rstrip("`")
        if path not in seen:
            seen.add(path)
            docs.append(path)
    return docs


_SCORING_PROMPT = """You are scoring one turn of an EAGLE federal-acquisition chatbot against a reference produced by a senior contracting officer. EAGLE is a multi-turn system; by mid-conversation it may legitimately rely on context loaded earlier in the same session.

Turn {turn_num} of a multi-turn demo. {turn_context_hint}

USER MESSAGE:
{user_message}

REFERENCE RESPONSE (gold standard):
{reference}

EAGLE RESPONSE (candidate):
{candidate}

TOOLS EAGLE CALLED THIS TURN: {tools_called}
(Empty list is OK for greetings, acknowledgments, or when the question is answerable from prior-turn context.)

PRE-COMPUTED SOURCE OVERLAP HINT:
- EAGLE cited {eagle_doc_count} KB docs
- Reference cited {ref_doc_count} KB docs
- Overlap: {overlap_count} shared docs ({overlap_pct:.0%} of reference)

=================================================================
SCORING RULES (read carefully — the four dimensions are INDEPENDENT)
=================================================================

Score each dimension 0-5 as an INTEGER. EAGLE can match or exceed the
reference — if EAGLE is more thorough or more actionable than the
reference, give it 5/5 on that dimension. Do not artificially cap scores.

**accuracy** — factual correctness ONLY. Does every specific claim hold up?
  - 5: All FAR/RFO/AA/threshold/vehicle/case claims are correct and
       verifiable. No hallucinated section numbers or invented authorities.
  - 4: Content is correct; one minor or recoverable imprecision (e.g.,
       rounded dollar figure, slightly-off date).
  - 3: Content is correct but lacks specificity (vague FAR references
       like "under FAR Part 13" without the subsection).
  - 2: At least one material factual error that a CO would flag.
  - 1: Multiple factual errors or a fabricated primary citation
       (FAR section that doesn't exist, fake case number, wrong AA
       number, invented Class Deviation).
  - 0: Fundamental wrong answer or completely fabricated.
  NOTE: "Did not call a tool" is NOT an accuracy penalty. Only score
  accuracy on the CONTENT of the claims made.

**completeness** — topic coverage vs reference AND vs what a CO needs.
  - 5: Covers everything the reference covers AND adds value beyond it.
  - 4: Covers all main aspects the reference covered; minor edges missing.
  - 3: Covers the core question; misses 1-2 meaningful sub-topics.
  - 2: Addresses the question partially; major aspects missing.
  - 1: Tangential or shallow.
  - 0: Declines the question or answers the wrong question.

**sources** — grounding quality. Did EAGLE reference primary KB sources?
  - 5: Cites specific KB files or FAR sections that match or exceed the
       reference's citations. Overlap ≥60% OR EAGLE cites equivalent
       alternative primary sources.
  - 4: Solid citation coverage; overlap 30-60% with reference.
  - 3: Some citations present; overlap 10-30% OR cites general sources
       without specific file paths.
  - 2: Few citations, mostly general.
  - 1: No citations but claims are consistent with public knowledge.
  - 0: No citations AND response contains specific claims that should
       have been grounded (FAR/AA/threshold numbers with no source).
  NOTE: If the user asked a greeting or simple follow-up and the
  reference also had no KB cites, give EAGLE a neutral 3 — do not
  penalize on sources when there is nothing to cite.

**actionability** — can a CO use this today?
  - 5: Concrete next steps, decision tables, checklists, worked examples,
       or a complete drafted document section. Better or equal to reference.
  - 4: Clear guidance with a few specifics.
  - 3: General direction with some procedure but no concrete artifacts.
  - 2: Vague advice, mostly "consult your policy office".
  - 1: Philosophical or advisory with no forward motion.
  - 0: Asks clarifying questions when the user explicitly asked for output,
       or returns an error / no substantive content.

CROSS-DIMENSION GUARDRAILS:
  - If EAGLE's content is factually correct but uncited, accuracy can
    still be 4-5 while sources is 1-3. Do NOT drag accuracy down just
    because sources is low.
  - If EAGLE delivers BETTER actionability than the reference (e.g.,
    adds a decision table the reference lacks), actionability gets 5/5
    regardless of whether sources is weaker.
  - If a tool error caused EAGLE to return a graceful error message
    ("I hit an unexpected error"), score all four as 0 — but note it's
    a system failure, not a content failure.
  - The verdict is based on TOTAL score: >16 → "EAGLE > reference",
    12-16 → "EAGLE = reference", <12 → "EAGLE < reference".

Return ONLY a JSON object (no markdown fencing):

{{
  "accuracy": 0-5,
  "completeness": 0-5,
  "sources": 0-5,
  "actionability": 0-5,
  "verdict": "EAGLE > reference" or "EAGLE = reference" or "EAGLE < reference",
  "reasoning": "3-4 sentences. Name the single biggest win and single biggest gap. Separate content quality from grounding quality explicitly."
}}"""


def _build_bedrock_client():
    """Lazy-init a bedrock-runtime client configured for scoring calls.

    Routes through the backend's shared aws_session helper so scoring
    inherits the same credential path as the rest of EAGLE — typically
    ``AWS_PROFILE=eagle`` (SSO) locally, ECS task role on deployed envs.
    Falls back to a bare ``boto3.client`` call if the helper isn't
    importable (e.g. when the script is run outside the server/ dir).
    """
    import boto3
    from botocore.config import Config

    # Make sure the backend's .env is loaded so AWS_PROFILE propagates
    # even when this script is spawned from a shell that didn't source
    # it (e.g. run_in_background Bash tasks).
    try:
        from dotenv import load_dotenv
        _env_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "..", "..", "..", "server", ".env",
        )
        if os.path.exists(_env_path):
            load_dotenv(_env_path, override=False)
    except Exception:
        pass

    region = os.environ.get("AWS_REGION", "us-east-1")
    cfg = Config(
        connect_timeout=30,
        read_timeout=180,
        retries={"max_attempts": 2, "mode": "adaptive"},
    )

    # Prefer the shared backend session so the credential path is
    # explicit and logged (profile=eagle vs default chain).
    try:
        import sys
        server_app_path = os.path.abspath(
            os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "..", "..", "..", "..", "server",
            )
        )
        if server_app_path not in sys.path:
            sys.path.insert(0, server_app_path)
        from app.aws_session import get_shared_session  # type: ignore
        session = get_shared_session()
        return session.client("bedrock-runtime", region_name=region, config=cfg)
    except Exception:
        # Fallback: direct boto3 client, relying on whatever credential
        # path boto3 picks. At least AWS_PROFILE from the .env we just
        # loaded will be honored.
        return boto3.client("bedrock-runtime", region_name=region, config=cfg)


def score_turn(bedrock_client, turn_result: dict) -> dict:
    """Score one EAGLE response vs reference using Bedrock converse.

    Returns {"acc", "comp", "src", "act", "total", "verdict", "reasoning"}.
    On failure returns a zero-score entry with the error in reasoning.
    """
    model_id = os.environ.get(
        "DEMO_JUDGE_MODEL", "us.anthropic.claude-sonnet-4-6"
    )

    # Source overlap pre-computation
    eagle_docs = set(parse_eagle_docs(turn_result["response"]))
    ref_doc_paths = {d["path"] for d in turn_result.get("reference_docs", [])}
    overlap = eagle_docs & ref_doc_paths
    overlap_pct = len(overlap) / max(len(ref_doc_paths), 1)

    tools_list = turn_result.get("tools") or []
    tools_called_str = ", ".join(tools_list) if tools_list else "(none)"

    turn_num = turn_result["turn"]
    if turn_num == 1:
        turn_context_hint = (
            "This is the FIRST turn of the session — no prior context is "
            "loaded. If the user poses a factual question, EAGLE should "
            "fetch sources."
        )
    elif turn_num == 2:
        turn_context_hint = (
            "Turn 2 of a fresh session. Only the Turn 1 greeting/intro "
            "is in context — treat this as effectively a cold factual "
            "question. EAGLE should still call research for regulatory "
            "claims."
        )
    else:
        turn_context_hint = (
            f"Turn {turn_num} of a multi-turn session. Prior turns may "
            "have loaded research into context — it is acceptable for "
            "EAGLE to answer from prior-turn research IF the content is "
            "factually correct and cites the KB documents that were "
            "already fetched. But answering from memory without any "
            "grounding is still a failure."
        )

    prompt = _SCORING_PROMPT.format(
        turn_num=turn_num,
        turn_context_hint=turn_context_hint,
        user_message=turn_result["user_message"][:2000],
        reference=turn_result["reference_response"][:8000],
        candidate=turn_result["response"][:8000],
        tools_called=tools_called_str,
        eagle_doc_count=len(eagle_docs),
        ref_doc_count=len(ref_doc_paths),
        overlap_count=len(overlap),
        overlap_pct=overlap_pct,
    )

    try:
        response = bedrock_client.converse(
            modelId=model_id,
            messages=[
                {
                    "role": "user",
                    "content": [{"text": prompt}],
                }
            ],
            inferenceConfig={"maxTokens": 1400, "temperature": 0},
        )
        output_text = response["output"]["message"]["content"][0]["text"].strip()

        # Strip markdown fences if present
        if output_text.startswith("```"):
            output_text = re.sub(r"^```(?:json)?\s*", "", output_text)
            output_text = re.sub(r"\s*```$", "", output_text)

        try:
            data = json.loads(output_text)
        except json.JSONDecodeError:
            # Try to find the first {...} block
            m = re.search(r"\{.*\}", output_text, re.DOTALL)
            if not m:
                raise
            data = json.loads(m.group())

        acc = int(data.get("accuracy", 0))
        comp = int(data.get("completeness", 0))
        src = int(data.get("sources", 0))
        act = int(data.get("actionability", 0))

        return {
            "turn": turn_result["turn"],
            "acc": acc,
            "comp": comp,
            "src": src,
            "act": act,
            "total": acc + comp + src + act,
            "verdict": data.get("verdict", "EAGLE = reference"),
            "reasoning": data.get("reasoning", ""),
            "overlap_pct": round(overlap_pct, 2),
            "eagle_docs": sorted(eagle_docs),
            "ref_docs": sorted(ref_doc_paths),
            "model": model_id,
        }
    except Exception as e:
        print(f"[score] Turn {turn_result['turn']} scoring failed: {e}")
        return {
            "turn": turn_result["turn"],
            "acc": 0,
            "comp": 0,
            "src": 0,
            "act": 0,
            "total": 0,
            "verdict": "scoring-failed",
            "reasoning": f"Bedrock scoring error: {e}",
            "overlap_pct": round(overlap_pct, 2),
            "eagle_docs": sorted(eagle_docs),
            "ref_docs": sorted(ref_doc_paths),
            "model": model_id,
        }


def score_all_turns(results: list[dict]) -> dict[int, dict]:
    """Score every turn. Returns {turn_num: score_dict}."""
    client = _build_bedrock_client()
    scores: dict[int, dict] = {}
    for r in results:
        if r["status"] != "ok":
            print(f"[score] Skipping Turn {r['turn']} (status={r['status']})")
            continue
        print(f"\n[score] Scoring Turn {r['turn']}...")
        scores[r["turn"]] = score_turn(client, r)
        total = scores[r["turn"]]["total"]
        print(f"[score] Turn {r['turn']}: {total}/20 — {scores[r['turn']]['verdict']}")
    return scores


# ---------------------------------------------------------------------------
# 5. HTML report generation
# ---------------------------------------------------------------------------


def _doc_agent_label(path: str) -> tuple[str, str, str]:
    """(label, text_color, bg_color) for a doc path based on agent prefix."""
    for prefix, (text, bg, label) in DOC_TYPE_COLORS.items():
        if path.startswith(prefix):
            return label, text, bg
    return "KB", "#424242", "#F5F5F5"


def _doc_filename(path: str) -> str:
    return path.rsplit("/", 1)[-1] if "/" in path else path


def _img_to_data_uri(path: Path) -> str:
    """Base64-encode a PNG for inline embedding in the HTML report."""
    try:
        data = path.read_bytes()
        b64 = base64.b64encode(data).decode("ascii")
        return f"data:image/png;base64,{b64}"
    except Exception:
        return ""


def build_demo_report(
    run_id: str,
    demo_path: str,
    session_id: str,
    results: list[dict],
    scores: dict[int, dict],
    screenshots_by_turn: dict[int, list[dict]],
    server_url: str,
) -> str:
    """Build a self-contained HTML report for a demo run."""
    today = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Aggregate stats
    total_score = sum(s.get("total", 0) for s in scores.values())
    max_score = len(scores) * 20
    wins = sum(1 for s in scores.values() if "> " in s.get("verdict", ""))
    ties = sum(1 for s in scores.values() if "= " in s.get("verdict", ""))
    losses = sum(1 for s in scores.values() if "< " in s.get("verdict", ""))
    total_elapsed = sum(r.get("elapsed_s", 0) for r in results)
    total_in_tokens = sum(r.get("usage", {}).get("input_tokens", 0) for r in results)
    total_out_tokens = sum(r.get("usage", {}).get("output_tokens", 0) for r in results)

    # Aggregate doc overlap
    all_eagle_docs: set[str] = set()
    all_ref_docs: set[str] = set()
    for r in results:
        all_eagle_docs.update(parse_eagle_docs(r["response"]))
        all_ref_docs.update(d["path"] for d in r.get("reference_docs", []))
    shared = all_eagle_docs & all_ref_docs
    eagle_only = all_eagle_docs - all_ref_docs
    ref_only = all_ref_docs - all_eagle_docs

    # Per-turn score strip
    score_strip_items = ""
    for r in results:
        tn = r["turn"]
        sc = scores.get(tn, {})
        total = sc.get("total", 0)
        color = (
            "#2E7D32" if total >= 17
            else "#E65100" if total >= 12
            else "#C62828" if total > 0
            else "#9E9E9E"
        )
        score_strip_items += (
            f'<div class="summary-q"><div class="summary-q-num">Turn {tn}</div>'
            f'<div class="summary-q-score" style="color:{color}">{total}/20</div></div>'
        )

    # Per-turn cards
    turn_cards_html = []
    for r in results:
        tn = r["turn"]
        sc = scores.get(tn, {})
        user_msg = r["user_message"]
        eagle_resp = r["response"]
        ref_resp = r.get("reference_response", "")
        tools = r.get("tools", [])
        elapsed = r.get("elapsed_s", 0)
        eagle_doc_paths = parse_eagle_docs(eagle_resp)
        ref_doc_paths = [d["path"] for d in r.get("reference_docs", [])]
        shots = screenshots_by_turn.get(tn, [])

        # Score display
        score_html = ""
        if sc:
            total = sc.get("total", 0)
            total_color = (
                "#2E7D32" if total >= 17
                else "#E65100" if total >= 12
                else "#C62828"
            )
            score_html = f"""
            <div class="score-grid">
                <div class="score-item"><div class="score-val">{sc.get('acc', '—')}</div><div class="score-label">Accuracy</div></div>
                <div class="score-item"><div class="score-val">{sc.get('comp', '—')}</div><div class="score-label">Completeness</div></div>
                <div class="score-item"><div class="score-val">{sc.get('src', '—')}</div><div class="score-label">Sources</div></div>
                <div class="score-item"><div class="score-val">{sc.get('act', '—')}</div><div class="score-label">Actionability</div></div>
                <div class="score-total" style="color:{total_color}"><span class="score-big">{total}</span>/20</div>
            </div>
            """
            verdict = sc.get("verdict", "")
            if verdict:
                if "> " in verdict:
                    vclass = "verdict-win"
                elif "= " in verdict:
                    vclass = "verdict-tie"
                else:
                    vclass = "verdict-loss"
                score_html += f'<div class="verdict {vclass}">{escape(verdict)}</div>'
            reasoning = sc.get("reasoning", "")
            if reasoning:
                score_html += f'<div class="verdict-reasoning">{escape(reasoning)}</div>'

        # Tool pills
        tool_pills = ""
        for t in tools:
            tc, bg = TOOL_COLORS.get(t, ("#424242", "#F5F5F5"))
            tool_pills += (
                f'<span class="pill" style="background:{bg};color:{tc};'
                f'border:1px solid {tc}22">{escape(t)}</span>\n'
            )
        if not tools:
            tool_pills = (
                '<span class="pill" style="background:#F5F5F5;color:#9E9E9E;'
                'border:1px solid #E0E0E0">no tools</span>'
            )

        # Doc pills (EAGLE vs reference)
        def _doc_pills(doc_paths: list[str]) -> str:
            if not doc_paths:
                return '<div class="doc-empty">No KB documents referenced</div>'
            out = ""
            for p in doc_paths:
                label, tc, bg = _doc_agent_label(p)
                fname = _doc_filename(p)
                out += (
                    f'<div class="doc-row">'
                    f'<span class="doc-badge" style="background:{bg};color:{tc}">{escape(label)}</span>'
                    f'<span class="doc-name" title="{escape(p)}">{escape(fname)}</span>'
                    f"</div>\n"
                )
            return out

        eagle_doc_html = _doc_pills(eagle_doc_paths)
        ref_doc_html = _doc_pills(ref_doc_paths)

        # Screenshots
        shots_html = ""
        if shots:
            thumb_items = ""
            for s in shots:
                uri = _img_to_data_uri(Path(s["path"]))
                if not uri:
                    continue
                step_label = s.get("step", "").replace("_", " ")
                thumb_items += (
                    f'<a class="shot" href="{uri}" target="_blank">'
                    f'<img src="{uri}" alt="{escape(step_label)}">'
                    f'<div class="shot-label">{escape(step_label)}</div>'
                    f"</a>"
                )
            if thumb_items:
                shots_html = f"""
                <div class="section-label">Screenshots ({len(shots)})</div>
                <div class="shots-grid">{thumb_items}</div>
                """

        # Doc overlap numbers
        eagle_doc_count = len(eagle_doc_paths)
        ref_doc_count = len(ref_doc_paths)
        doc_delta = eagle_doc_count - ref_doc_count
        delta_class = (
            "delta-pos" if doc_delta > 0 else "delta-neg" if doc_delta < 0 else "delta-zero"
        )
        delta_str = f"+{doc_delta}" if doc_delta > 0 else str(doc_delta)

        eagle_len = len(eagle_resp)
        ref_len = len(ref_resp)

        turn_cards_html.append(f"""
        <div class="question-card">
            <div class="q-header">
                <div class="q-num">T{tn}</div>
                <div class="q-meta">
                    <span class="q-category">Turn {tn}</span>
                    <span class="q-title">{elapsed:.0f}s &bull; {r.get('model', 'unknown')}</span>
                </div>
                <div class="q-time">{len(tools)} tool{'s' if len(tools) != 1 else ''}</div>
            </div>

            <div class="q-text">{escape(user_msg)}</div>

            {score_html}

            <div class="section-label">Tools Called</div>
            <div class="pills-row">{tool_pills}</div>

            <div class="docs-compare">
                <div class="docs-col">
                    <div class="docs-header">
                        <span class="docs-system eagle-label">EAGLE</span>
                        <span class="docs-count">{eagle_doc_count} doc{'s' if eagle_doc_count != 1 else ''}</span>
                    </div>
                    <div class="docs-list">{eagle_doc_html}</div>
                </div>
                <div class="docs-col">
                    <div class="docs-header">
                        <span class="docs-system ro-label">Reference</span>
                        <span class="docs-count">{ref_doc_count} doc{'s' if ref_doc_count != 1 else ''}</span>
                    </div>
                    <div class="docs-list">{ref_doc_html}</div>
                </div>
            </div>

            <div class="docs-delta {delta_class}">
                Doc delta: {delta_str} &nbsp;|&nbsp; EAGLE {eagle_len:,} chars &nbsp;|&nbsp; Reference {ref_len:,} chars
            </div>

            {shots_html}

            <details class="response-toggle">
                <summary>View Responses</summary>
                <div class="responses-grid">
                    <div class="resp-col">
                        <div class="resp-label eagle-label">EAGLE</div>
                        <div class="resp-md" data-md="{escape(eagle_resp)}"></div>
                    </div>
                    <div class="resp-col">
                        <div class="resp-label ro-label">Reference</div>
                        <div class="resp-md" data-md="{escape(ref_resp)}"></div>
                    </div>
                </div>
            </details>
        </div>
        """)

    # KB coverage card
    coverage_html = ""

    def _coverage_pills(paths: set[str], cls: str) -> str:
        return "".join(
            f'<span class="pill {cls}" title="{escape(p)}">{escape(_doc_filename(p))}</span>'
            for p in sorted(paths)
        )

    if shared:
        coverage_html += (
            f'<div class="coverage-section">'
            f'<div class="coverage-label shared-label">Both Systems ({len(shared)})</div>'
            f'<div class="pills-wrap">{_coverage_pills(shared, "coverage-shared")}</div></div>'
        )
    if eagle_only:
        coverage_html += (
            f'<div class="coverage-section">'
            f'<div class="coverage-label eagle-only-label">EAGLE Only ({len(eagle_only)})</div>'
            f'<div class="pills-wrap">{_coverage_pills(eagle_only, "coverage-eagle")}</div></div>'
        )
    if ref_only:
        coverage_html += (
            f'<div class="coverage-section">'
            f'<div class="coverage-label ro-only-label">Reference Only ({len(ref_only)})</div>'
            f'<div class="pills-wrap">{_coverage_pills(ref_only, "coverage-ro")}</div></div>'
        )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>EAGLE Demo Report — {escape(run_id)}</title>
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

.meta-bar {{ background: white; border-radius: 12px; padding: 16px 20px; margin-bottom: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); display: flex; gap: 24px; flex-wrap: wrap; font-size: 12px; color: var(--gray-700); }}
.meta-bar b {{ color: var(--gray-900); }}

.summary-bar {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 16px; margin-bottom: 32px; }}
.summary-card {{ background: white; border-radius: 12px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); text-align: center; }}
.summary-card .big {{ font-size: 32px; font-weight: 700; }}
.summary-card .label {{ font-size: 12px; color: var(--gray-500); text-transform: uppercase; letter-spacing: 0.5px; margin-top: 4px; }}
.summary-card.wins .big {{ color: var(--green); }}
.summary-card.ties .big {{ color: var(--eagle-blue); }}
.summary-card.losses .big {{ color: var(--red); }}

.score-strip {{ display: flex; gap: 12px; justify-content: center; margin-bottom: 32px; flex-wrap: wrap; }}
.summary-q {{ background: white; border-radius: 10px; padding: 12px 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); text-align: center; min-width: 80px; }}
.summary-q-num {{ font-size: 11px; color: var(--gray-500); text-transform: uppercase; letter-spacing: 0.5px; }}
.summary-q-score {{ font-size: 20px; font-weight: 700; }}

.question-card {{ background: white; border-radius: 12px; padding: 24px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
.q-header {{ display: flex; align-items: center; gap: 16px; margin-bottom: 16px; }}
.q-num {{ font-size: 18px; font-weight: 700; color: var(--navy); background: #E8EAF6; border-radius: 8px; padding: 4px 12px; flex-shrink: 0; }}
.q-meta {{ flex: 1; }}
.q-category {{ display: inline-block; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; color: var(--eagle-blue); background: var(--eagle-bg); padding: 2px 8px; border-radius: 4px; margin-right: 8px; }}
.q-title {{ font-size: 14px; color: var(--gray-700); }}
.q-time {{ font-size: 13px; color: var(--gray-500); font-variant-numeric: tabular-nums; }}
.q-text {{ font-size: 13px; color: var(--gray-700); background: var(--gray-100); border-left: 3px solid var(--navy); padding: 10px 14px; border-radius: 0 6px 6px 0; margin-bottom: 16px; line-height: 1.5; white-space: pre-wrap; }}

.score-grid {{ display: flex; align-items: center; gap: 16px; margin-bottom: 12px; padding: 12px 16px; background: var(--gray-50); border-radius: 8px; flex-wrap: wrap; }}
.score-item {{ text-align: center; min-width: 60px; }}
.score-val {{ font-size: 20px; font-weight: 700; color: var(--navy); }}
.score-label {{ font-size: 10px; color: var(--gray-500); text-transform: uppercase; letter-spacing: 0.5px; }}
.score-total {{ margin-left: auto; text-align: center; }}
.score-big {{ font-size: 28px; font-weight: 800; }}
.verdict {{ font-size: 13px; font-weight: 600; padding: 6px 12px; border-radius: 6px; margin-bottom: 8px; display: inline-block; }}
.verdict-win {{ background: #E8F5E9; color: var(--green); }}
.verdict-tie {{ background: var(--eagle-bg); color: var(--eagle-blue); }}
.verdict-loss {{ background: #FFEBEE; color: var(--red); }}
.verdict-reasoning {{ font-size: 12px; color: var(--gray-700); padding: 8px 12px; background: var(--gray-50); border-radius: 6px; margin-bottom: 16px; line-height: 1.5; }}

.pill {{ display: inline-block; font-size: 12px; font-weight: 500; padding: 3px 10px; border-radius: 20px; margin: 2px 4px 2px 0; white-space: nowrap; }}
.pills-row {{ margin-bottom: 16px; }}
.pills-wrap {{ display: flex; flex-wrap: wrap; gap: 4px; }}
.section-label {{ font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; color: var(--gray-500); margin-bottom: 6px; margin-top: 12px; }}

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
.doc-empty {{ font-size: 12px; color: var(--gray-500); font-style: italic; padding: 4px 0; }}

.docs-delta {{ font-size: 11px; padding: 6px 12px; border-radius: 6px; margin-bottom: 12px; text-align: center; }}
.delta-pos {{ background: #E8F5E9; color: var(--green); }}
.delta-neg {{ background: #FFEBEE; color: var(--red); }}
.delta-zero {{ background: var(--gray-100); color: var(--gray-500); }}

.shots-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 10px; margin-bottom: 16px; }}
.shot {{ display: block; text-decoration: none; border: 1px solid var(--gray-300); border-radius: 6px; overflow: hidden; background: white; }}
.shot img {{ width: 100%; height: 120px; object-fit: cover; object-position: top; display: block; }}
.shot-label {{ font-size: 10px; color: var(--gray-700); padding: 4px 6px; text-align: center; background: var(--gray-50); font-family: 'SF Mono', 'Fira Code', monospace; border-top: 1px solid var(--gray-200); }}

.response-toggle {{ margin-top: 8px; }}
.response-toggle summary {{ font-size: 13px; color: var(--eagle-blue); cursor: pointer; font-weight: 500; padding: 6px 0; }}
.response-toggle summary:hover {{ text-decoration: underline; }}
.responses-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 12px; }}
@media (max-width: 768px) {{ .responses-grid {{ grid-template-columns: 1fr; }} }}
.resp-col {{ background: var(--gray-50); border-radius: 8px; padding: 12px; }}
.resp-label {{ font-size: 12px; font-weight: 700; padding: 3px 10px; border-radius: 6px; display: inline-block; margin-bottom: 8px; }}
.resp-md {{ font-size: 13px; color: var(--gray-700); max-height: 600px; overflow-y: auto; line-height: 1.6; }}
.resp-md h1,.resp-md h2,.resp-md h3,.resp-md h4 {{ color: var(--navy); margin: 14px 0 6px; }}
.resp-md h1 {{ font-size: 16px; }} .resp-md h2 {{ font-size: 15px; }} .resp-md h3 {{ font-size: 14px; }} .resp-md h4 {{ font-size: 13px; }}
.resp-md p {{ margin: 6px 0; }}
.resp-md ul,.resp-md ol {{ margin: 6px 0 6px 20px; }}
.resp-md li {{ margin: 3px 0; }}
.resp-md table {{ border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 12px; }}
.resp-md th,.resp-md td {{ border: 1px solid var(--gray-300); padding: 5px 8px; text-align: left; }}
.resp-md th {{ background: var(--gray-100); font-weight: 600; }}
.resp-md code {{ background: var(--gray-100); padding: 1px 4px; border-radius: 3px; font-size: 12px; font-family: 'SF Mono','Fira Code',monospace; }}
.resp-md pre {{ background: var(--gray-100); padding: 10px; border-radius: 6px; overflow-x: auto; margin: 8px 0; }}
.resp-md pre code {{ background: none; padding: 0; }}
.resp-md blockquote {{ border-left: 3px solid var(--gray-300); padding: 4px 12px; margin: 8px 0; color: var(--gray-700); background: var(--gray-50); }}
.resp-md hr {{ border: none; border-top: 1px solid var(--gray-300); margin: 12px 0; }}
.resp-md strong {{ font-weight: 600; }}

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

.footer {{ text-align: center; padding: 24px; font-size: 12px; color: var(--gray-500); }}
</style>
</head>
<body>

<div class="header">
    <h1>EAGLE Demo Scenario Report</h1>
    <div class="subtitle">{escape(run_id)} &mdash; {today}</div>
</div>

<div class="container">

    <div class="meta-bar">
        <div><b>Demo:</b> {escape(Path(demo_path).name)}</div>
        <div><b>Server:</b> {escape(server_url)}</div>
        <div><b>Session:</b> <code>{escape(session_id)}</code></div>
        <div><b>Total elapsed:</b> {total_elapsed:.0f}s</div>
        <div><b>Tokens:</b> {total_in_tokens:,} in / {total_out_tokens:,} out</div>
    </div>

    <div class="summary-bar">
        <div class="summary-card"><div class="big" style="color:var(--navy)">{total_score}/{max_score}</div><div class="label">Total Score</div></div>
        <div class="summary-card wins"><div class="big">{wins}</div><div class="label">EAGLE Wins</div></div>
        <div class="summary-card ties"><div class="big">{ties}</div><div class="label">Ties</div></div>
        <div class="summary-card losses"><div class="big">{losses}</div><div class="label">Reference Wins</div></div>
        <div class="summary-card"><div class="big" style="color:var(--navy)">{len(all_eagle_docs)}</div><div class="label">EAGLE Docs</div></div>
        <div class="summary-card"><div class="big" style="color:var(--ro-purple)">{len(all_ref_docs)}</div><div class="label">Reference Docs</div></div>
    </div>

    <div class="score-strip">{score_strip_items}</div>

    <div class="coverage-card">
        <h2>Knowledge Base Coverage</h2>
        <p style="font-size:13px;color:var(--gray-700);margin-bottom:16px">
            Unique KB documents across all {len(results)} turns.
            EAGLE: {len(all_eagle_docs)} unique &nbsp;|&nbsp;
            Reference: {len(all_ref_docs)} unique &nbsp;|&nbsp;
            Shared: {len(shared)}
        </p>
        {coverage_html}
    </div>

    {"".join(turn_cards_html)}

</div>

<div class="footer">
    EAGLE Demo Report &mdash; Generated {today} &mdash; {len(results)} turns evaluated
</div>

<script src="https://cdn.jsdelivr.net/npm/marked@15/marked.min.js"></script>
<script>
document.addEventListener('DOMContentLoaded', function() {{
    document.querySelectorAll('.resp-md[data-md]').forEach(function(el) {{
        var raw = el.getAttribute('data-md');
        var ta = document.createElement('textarea');
        ta.innerHTML = raw;
        var md = ta.value;
        el.innerHTML = marked.parse(md, {{ breaks: false, gfm: true }});
    }});
}});
</script>

</body>
</html>"""
    return html


# ---------------------------------------------------------------------------
# 6. CLI
# ---------------------------------------------------------------------------


async def _amain(args):
    demo_path = Path(args.demo_script)
    if not demo_path.exists():
        print(f"ERROR: Demo script not found: {demo_path}")
        sys.exit(1)

    # Resolve output dir
    if args.output:
        output_root = Path(args.output)
    else:
        repo_root = Path(__file__).resolve().parent.parent.parent.parent.parent
        output_root = repo_root / "scripts" / "demo_eval_results"

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_dir = output_root / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"EAGLE Demo Scenario Evaluator")
    print(f"  Demo:    {demo_path}")
    print(f"  Server:  {args.server}")
    print(f"  Tenant:  {args.tenant}")
    print(f"  Run ID:  {run_id}")
    print(f"  Output:  {output_dir}")

    # --- 1. Parse docx (or load hand-edited turns JSON) ---
    if args.turns_json:
        turns_json_path = Path(args.turns_json)
        if not turns_json_path.exists():
            print(f"ERROR: --turns-json file not found: {turns_json_path}")
            sys.exit(1)
        print(f"\n{'='*80}\nLoading turns from {turns_json_path}\n{'='*80}")
        with open(turns_json_path, encoding="utf-8") as f:
            parsed = json.load(f)
        if "turns" not in parsed:
            print(f"ERROR: {turns_json_path} missing 'turns' key")
            sys.exit(1)
        # Back-fill metadata if older hand-edited file is missing it
        parsed.setdefault(
            "metadata",
            {
                "path": str(demo_path),
                "total_paragraphs": 0,
                "total_turns": len(parsed["turns"]),
                "marker_blocks": 0,
            },
        )
    else:
        print(f"\n{'='*80}\nParsing demo script...\n{'='*80}")
        parsed = parse_demo_docx(str(demo_path))
    turns = parsed["turns"]
    print(f"Parsed {len(turns)} turns from {parsed['metadata'].get('total_paragraphs', 0)} paragraphs")
    for t in turns:
        preview = t["user_message"].replace("\n", " ")[:100]
        ref_preview = t["reference_response"].replace("\n", " ")[:80]
        print(
            f"  Turn {t['turn']}: user={len(t['user_message'])}ch "
            f"ref={len(t['reference_response'])}ch docs={len(t['reference_docs'])}"
        )
        print(f"    U: {preview}")
        print(f"    R: {ref_preview}")

    turns_path = output_dir / "demo_turns.json"
    with open(turns_path, "w", encoding="utf-8") as f:
        json.dump(parsed, f, indent=2, ensure_ascii=False)
    print(f"\nParsed turns saved to {turns_path}")

    if args.parse_only:
        print("\n--parse-only set, exiting.")
        return

    # --- 2. Run API turns ---
    print(f"\n{'='*80}\nRunning {len(turns)} turns against {args.server}...\n{'='*80}")
    try:
        session_id, results = await run_demo_session(
            base_url=args.server,
            tenant=args.tenant,
            turns=turns,
            pause_seconds=3.0,
        )
    except BackendUnreachableError as e:
        print(f"\nABORTED: {e}")
        sys.exit(2)

    results_path = output_dir / "results.json"
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(
            {"session_id": session_id, "server": args.server, "turns": results},
            f,
            indent=2,
            ensure_ascii=False,
        )
    print(f"\nResults saved to {results_path}")

    # --- 3. Screenshots (optional) ---
    screenshots_by_turn: dict[int, list[dict]] = {}
    if args.screenshots:
        print(f"\n{'='*80}\nCapturing Playwright screenshots...\n{'='*80}")
        try:
            screenshots_by_turn = await capture_demo_screenshots(
                base_url=args.server,
                turns=turns,
                output_dir=output_dir,
                headless=not args.headed,
                auth_email=args.auth_email,
                auth_password=args.auth_password,
            )
        except Exception as e:
            print(f"[screenshots] Capture failed: {e}")
            print("[screenshots] Continuing without screenshots.")

    # --- 4. Scoring ---
    scores: dict[int, dict] = {}
    if not args.skip_scoring:
        print(f"\n{'='*80}\nScoring turns via Bedrock...\n{'='*80}")
        try:
            scores = score_all_turns(results)
            scores_path = output_dir / "scores.json"
            with open(scores_path, "w", encoding="utf-8") as f:
                # JSON-serializable: convert int keys
                json.dump(
                    {str(k): v for k, v in scores.items()},
                    f,
                    indent=2,
                    ensure_ascii=False,
                )
            print(f"\nScores saved to {scores_path}")
        except Exception as e:
            print(f"[score] Scoring failed: {e}")
            print("[score] Continuing without scores.")

    # --- 5. HTML report ---
    print(f"\n{'='*80}\nBuilding HTML report...\n{'='*80}")
    html = build_demo_report(
        run_id=run_id,
        demo_path=str(demo_path),
        session_id=session_id,
        results=results,
        scores=scores,
        screenshots_by_turn=screenshots_by_turn,
        server_url=args.server,
    )
    report_path = output_dir / "demo_report.html"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Report: {report_path}")

    # --- Summary ---
    print(f"\n{'='*80}\nSUMMARY\n{'='*80}")
    total_score = sum(s.get("total", 0) for s in scores.values())
    max_score = len(scores) * 20 if scores else 0
    total_elapsed = sum(r.get("elapsed_s", 0) for r in results)
    print(f"Turns:       {len(results)}")
    print(f"Total time:  {total_elapsed:.0f}s")
    if scores:
        print(f"Score:       {total_score}/{max_score}")
    print(f"Output:      {output_dir}")


def main():
    parser = argparse.ArgumentParser(
        description="Run an EAGLE demo scenario from a .docx script against a live server"
    )
    parser.add_argument(
        "--demo-script",
        required=True,
        help="Path to the demo-script .docx file",
    )
    parser.add_argument(
        "--server",
        required=True,
        help="EAGLE server base URL (e.g., https://DEV-ALB-URL or http://localhost:8000)",
    )
    parser.add_argument("--tenant", default="dev-tenant", help="Tenant ID for API calls")
    parser.add_argument("--output", default=None, help="Override output directory root")
    parser.add_argument(
        "--screenshots",
        action="store_true",
        help="Capture Playwright screenshots of the chat UI",
    )
    parser.add_argument(
        "--auth-email",
        default=None,
        help="Cognito email (or set EAGLE_TEST_EMAIL)",
    )
    parser.add_argument(
        "--auth-password",
        default=None,
        help="Cognito password (or set EAGLE_TEST_PASSWORD)",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Show the browser window during screenshot capture",
    )
    parser.add_argument(
        "--skip-scoring",
        action="store_true",
        help="Skip Bedrock LLM scoring (report will omit score cards)",
    )
    parser.add_argument(
        "--parse-only",
        action="store_true",
        help="Only parse the docx and save demo_turns.json, no API calls",
    )
    parser.add_argument(
        "--turns-json",
        default=None,
        help="Skip docx parsing and load hand-edited turns from this JSON "
             "(use after --parse-only to fix turn boundaries manually)",
    )
    args = parser.parse_args()

    asyncio.run(_amain(args))


if __name__ == "__main__":
    main()
