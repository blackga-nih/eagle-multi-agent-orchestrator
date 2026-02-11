"""
Browser Video Recorder for EAGLE Eval Suite

Records Playwright videos of real chat conversations on the EAGLE chat page.
Each UC test sends its scenario prompt through the browser UI and records
the agent's live response.

Usage (standalone):
    python browser_recorder.py --test 21 --base-url http://localhost:3000 \
        --auth-email user@nih.gov --auth-password "pass"

Usage (integrated — called from test_eagle_sdk_eval.py --record-video):
    recorder = BrowserRecorder()  # defaults to data/eval/videos/
    await recorder.start()
    ctx = await recorder.begin_test(21)   # opens chat, sends UC prompt
    await recorder.wait_for_response(ctx) # waits for agent to finish
    path = await recorder.end_test(ctx)   # closes context, finalizes video
    await recorder.stop()

Requires: pip install playwright && playwright install chromium
"""

import asyncio
import os
import subprocess
import sys
from datetime import datetime, timezone
from typing import Optional

# ---------------------------------------------------------------------------
# Test-to-prompt mapping: the chat message to send for each test
# Mirrors the exact prompts from test_eagle_sdk_eval.py UC tests.
# ---------------------------------------------------------------------------
TEST_PROMPTS: dict[int, str] = {
    9: (
        "Hi, I need to buy a new microscope. Not sure about the price. "
        "Need it in 2 months."
    ),
    15: (
        "New acquisition request: We need IT modernization services for $500K "
        "over 3 years. Includes cloud migration and agile development. "
        "Run the full skill chain to assess this acquisition."
    ),
    21: (
        "I have a quote for $13,800 from Fisher Scientific for lab supplies — "
        "centrifuge tubes, pipette tips, and reagents. Grant-funded, deliver to "
        "Building 37 Room 204. I want to use the purchase card. "
        "What's the fastest way to process this?"
    ),
    22: (
        "I need to exercise Option Year 3 on contract HHSN261201500003I. "
        "The base value was $1.2M, same scope continuing, new COR replacing "
        "Dr. Smith, 3% cost escalation per the contract terms, no performance "
        "issues. Option period would be 10/1/2028 through 9/30/2029. "
        "What documents do I need to prepare?"
    ),
    23: (
        "I need to modify contract HHSN261201500003I. Adding $150K in FY2026 "
        "funding and extending the period of performance by 6 months to September 30, 2027. "
        "Same scope of work, just continuing the existing effort. "
        "Is this within scope? What type of modification is this? What documents do I need?"
    ),
    24: (
        "Review this acquisition package for a $487,500 IT services contract: "
        "The AP says competitive full and open, but the IGCE total is $495,000 — "
        "cost mismatch. The SOW mentions a 3-year PoP but the AP says 2 years. "
        "Market research is 14 months old. No FAR 52.219 small business clause. "
        "Task 3 deliverable in the SOW has no acceptance criteria. "
        "Identify all findings and categorize by severity (critical/moderate/minor)."
    ),
    25: (
        "I need to close out contract HHSN261200900045C. It's a firm-fixed-price "
        "contract, all options were exercised, final invoice has been paid, "
        "and all deliverables have been accepted. What's the FAR 4.804 close-out "
        "checklist? What documents do I still need — release of claims letter, "
        "patent report, property report? Draft a COR final assessment outline."
    ),
    26: (
        "Government shutdown is imminent — 4 hours away. I have 200+ active contracts. "
        "How should I classify them? I know some are fully funded FFP (should continue), "
        "some are incrementally funded (stop at limit), some are cost-reimbursement "
        "(stop work immediately), and some support excepted life/safety activities. "
        "What notification categories do I need? What should each email say? "
        "Draft the four notification templates."
    ),
    27: (
        "I have 180 score sheets from 9 technical reviewers evaluating 20 proposals. "
        "Each reviewer scored 5 evaluation factors: Technical Approach, Management Plan, "
        "Past Performance, Key Personnel, and Cost Realism. "
        "Three proposals have significant reviewer divergence. "
        "The reviewers also submitted 847 total questions — many are duplicates. "
        "How should I consolidate the scores? What analysis should I run for "
        "reviewer variance? How do I deduplicate and categorize the questions?"
    ),
}

# Human-readable names (for video filenames)
TEST_NAMES: dict[int, str] = {
    9:  "uc01_intake_workflow",
    15: "uc01_full_chain",
    21: "uc02_micro_purchase",
    22: "uc03_option_exercise",
    23: "uc04_contract_modification",
    24: "uc05_co_package_review",
    25: "uc07_contract_closeout",
    26: "uc08_shutdown_notification",
    27: "uc09_score_consolidation",
}

# Max wait for agent response (seconds) — some UCs produce long responses
RESPONSE_TIMEOUT: dict[int, int] = {
    9: 60, 15: 120, 21: 60, 22: 60, 23: 60,
    24: 90, 25: 90, 26: 120, 27: 120,
}


class RecordingContext:
    """Holds Playwright context + page for a single test recording."""

    def __init__(self, context, page, test_id: int, video_dir: str):
        self.context = context
        self.page = page
        self.test_id = test_id
        self.video_dir = video_dir
        self._video_path: Optional[str] = None

    async def finalize(self) -> Optional[str]:
        """Close context (finalizes video) and return the video path."""
        try:
            self._video_path = await self.page.video.path()
        except Exception:
            pass
        await self.context.close()
        return self._video_path


class BrowserRecorder:
    """Playwright-based video recorder for EAGLE eval tests.

    Opens Chromium, navigates to the chat page, sends the UC scenario prompt,
    records the full agent response, and saves the video as WebM.
    """

    def __init__(
        self,
        video_dir: str = None,
        base_url: str = "http://localhost:3000",
        headless: bool = True,
        viewport_width: int = 1280,
        viewport_height: int = 720,
        auth_email: Optional[str] = None,
        auth_password: Optional[str] = None,
    ):
        if video_dir is None:
            repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            video_dir = os.path.join(repo_root, "data", "eval", "videos")
        self.video_dir = os.path.abspath(video_dir)
        self.base_url = base_url.rstrip("/")
        self.headless = headless
        self.viewport = {"width": viewport_width, "height": viewport_height}
        self.auth_email = auth_email or os.environ.get("EAGLE_TEST_EMAIL")
        self.auth_password = auth_password or os.environ.get("EAGLE_TEST_PASSWORD")
        self._pw = None
        self._browser = None
        self._storage_state = None  # cached auth state after first login
        os.makedirs(self.video_dir, exist_ok=True)

    async def start(self):
        """Launch Playwright and Chromium."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            print("  [recorder] playwright not installed. Run: pip install playwright && playwright install chromium")
            raise

        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=self.headless)
        print(f"  [recorder] Chromium launched (headless={self.headless})")

        # Pre-authenticate once and cache the storage state for all contexts
        await self._authenticate()

    async def _authenticate(self):
        """Log in once via the UI and cache the browser storage state."""
        context = await self._browser.new_context(viewport=self.viewport)
        page = await context.new_page()

        await page.goto(self.base_url, wait_until="networkidle")

        # Wait for potential client-side redirect (AuthGuard uses useEffect)
        await page.wait_for_timeout(3000)

        # Check if we landed on the login page
        if "/login" in page.url:
            if not self.auth_email or not self.auth_password:
                print("  [recorder] Auth required but no credentials provided.")
                print("             Set --auth-email/--auth-password or EAGLE_TEST_EMAIL/EAGLE_TEST_PASSWORD env vars.")
                await context.close()
                raise RuntimeError("Recorder needs credentials to log in")

            print(f"  [recorder] Logging in as {self.auth_email}...")
            await page.fill("#login-email", self.auth_email)
            await page.fill("#login-password", self.auth_password)
            await page.click("button[type='submit']")

            # Wait for redirect away from /login (Cognito redirects to /)
            for _ in range(20):
                await page.wait_for_timeout(1000)
                if "/login" not in page.url:
                    break
            else:
                error_el = page.locator("div[role='alert']")
                if await error_el.count() > 0:
                    err_text = await error_el.text_content()
                    print(f"  [recorder] Login error: {err_text}")
                else:
                    print("  [recorder] Login timed out — still on login page")
                await context.close()
                raise RuntimeError("Recorder login failed")

            print(f"  [recorder] Authenticated successfully")
        else:
            print(f"  [recorder] No auth required (dev mode)")

        # Save storage state (cookies + localStorage) for reuse
        self._storage_state = await context.storage_state()
        await context.close()

    async def stop(self):
        """Tear down browser and Playwright."""
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()
        print(f"  [recorder] Browser closed. Videos in: {self.video_dir}")

    def has_recording(self, test_id: int) -> bool:
        """Check if a test has a chat prompt to record."""
        return test_id in TEST_PROMPTS

    async def begin_test(self, test_id: int) -> Optional[RecordingContext]:
        """Open browser, navigate to chat, send the UC prompt, start recording.

        Returns a RecordingContext, or None if the test has no prompt mapping.
        """
        if test_id not in TEST_PROMPTS:
            return None

        prompt = TEST_PROMPTS[test_id]
        test_name = TEST_NAMES.get(test_id, f"test_{test_id}")
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        test_video_dir = os.path.join(self.video_dir, f"{test_name}_{timestamp}")
        os.makedirs(test_video_dir, exist_ok=True)

        context = await self._browser.new_context(
            record_video_dir=test_video_dir,
            record_video_size=self.viewport,
            viewport=self.viewport,
            storage_state=self._storage_state,
        )
        page = await context.new_page()

        print(f"  [recorder] Recording test {test_id} → {self.base_url} (chat)")

        await page.goto(self.base_url, wait_until="networkidle")

        # Wait for the chat textarea to appear
        try:
            await page.wait_for_selector("textarea", state="visible", timeout=15000)
        except Exception:
            await page.wait_for_timeout(3000)
            if "/login" in page.url:
                print(f"  [recorder] Auth redirect — skipping test {test_id}")
                await context.close()
                return None

        # Brief pause so the page is visually settled for the video
        await page.wait_for_timeout(1000)

        # Type the prompt into the chat textarea
        textarea = page.locator("textarea")
        await textarea.fill(prompt)
        await page.wait_for_timeout(500)

        # Send the message
        send_btn = page.locator("button:has-text('➤')")
        await send_btn.click()
        print(f"  [recorder] Prompt sent ({len(prompt)} chars)")

        return RecordingContext(context, page, test_id, test_video_dir)

    async def wait_for_response(self, ctx: Optional[RecordingContext]):
        """Wait for the EAGLE agent to finish responding.

        Watches for the typing indicator (.typing-dot) to appear then disappear,
        plus waits for the textarea to become enabled again.
        """
        if ctx is None:
            return

        page = ctx.page
        timeout_s = RESPONSE_TIMEOUT.get(ctx.test_id, 90)

        # Wait for typing indicator to appear (agent started responding)
        try:
            await page.wait_for_selector(".typing-dot", state="visible", timeout=15000)
        except Exception:
            # Agent may have already finished before we could detect the dots
            pass

        # Wait for typing indicator to disappear (agent finished)
        try:
            await page.wait_for_selector(
                ".typing-dot", state="hidden", timeout=timeout_s * 1000
            )
        except Exception:
            print(f"  [recorder] Response timeout ({timeout_s}s) — recording what we have")

        # Extra pause so the full response is visible in the video
        await page.wait_for_timeout(3000)

        # Scroll to the bottom of the message list to capture everything
        try:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(1000)
        except Exception:
            pass

    async def end_test(self, ctx: Optional[RecordingContext]) -> Optional[str]:
        """Finalize recording and return the video file path."""
        if ctx is None:
            return None

        video_path = await ctx.finalize()
        if video_path:
            print(f"  [recorder] Video saved: {video_path}")
        return video_path


def convert_webm_to_mp4(webm_path: str, mp4_path: Optional[str] = None) -> Optional[str]:
    """Convert a WebM video to MP4 using ffmpeg (if available).

    Returns the MP4 path, or None if ffmpeg is not installed.
    """
    if mp4_path is None:
        mp4_path = webm_path.rsplit(".", 1)[0] + ".mp4"

    try:
        subprocess.run(
            [
                "ffmpeg", "-i", webm_path,
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "23",
                "-y",
                mp4_path,
            ],
            check=True,
            capture_output=True,
        )
        return mp4_path
    except FileNotFoundError:
        return None  # ffmpeg not installed
    except subprocess.CalledProcessError:
        return None


# ---------------------------------------------------------------------------
# Standalone mode: record a single UC chat interaction
# ---------------------------------------------------------------------------
async def _standalone(test_id: int, base_url: str, headless: bool,
                      auth_email: Optional[str] = None, auth_password: Optional[str] = None):
    recorder = BrowserRecorder(
        base_url=base_url, headless=headless,
        auth_email=auth_email, auth_password=auth_password,
    )
    await recorder.start()

    ctx = await recorder.begin_test(test_id)
    if ctx is None:
        print(f"Test {test_id} has no prompt mapping. Available: {list(TEST_PROMPTS.keys())}")
        await recorder.stop()
        return

    await recorder.wait_for_response(ctx)
    video_path = await recorder.end_test(ctx)
    await recorder.stop()

    if video_path:
        print(f"\nVideo: {video_path}")
        mp4 = convert_webm_to_mp4(video_path)
        if mp4:
            print(f"MP4:   {mp4}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Record EAGLE eval chat interactions")
    parser.add_argument("--test", type=int, required=True, help="Test ID to record")
    parser.add_argument("--base-url", default="http://localhost:3000", help="Frontend base URL")
    parser.add_argument("--headed", action="store_true", help="Run with visible browser")
    parser.add_argument("--auth-email", default=None, help="Login email (or set EAGLE_TEST_EMAIL)")
    parser.add_argument("--auth-password", default=None, help="Login password (or set EAGLE_TEST_PASSWORD)")
    args = parser.parse_args()

    asyncio.run(_standalone(
        args.test, args.base_url, headless=not args.headed,
        auth_email=args.auth_email, auth_password=args.auth_password,
    ))
