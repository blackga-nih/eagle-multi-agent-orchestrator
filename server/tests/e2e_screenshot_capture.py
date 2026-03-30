"""
Screenshot capture utility for E2E judge pipeline.

Extends the BrowserRecorder authentication pattern to capture full-page PNG
screenshots at each test step. Each screenshot is hashed (SHA-256) for cache
lookup by the vision judge.

Includes PageEventCollector — attaches to Playwright page events (console,
network, errors) and drains them into a text context string at each screenshot.
This context is passed alongside the image to the vision judge so it can reason
about frontend state, not just pixels.

Usage:
    capture = ScreenshotCapture(base_url="http://ALB-URL", run_id="20260326-140000")
    await capture.start()
    screenshots = await capture.run_journey("chat", journey_chat)
    await capture.stop()
"""

import asyncio
import hashlib
import json as _json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from .e2e_judge_cache import compute_sha256


# ---------------------------------------------------------------------------
# PageEventCollector — captures frontend events between screenshots
# ---------------------------------------------------------------------------

class PageEventCollector:
    """Collects Playwright page events (console, errors, network) for judge context.

    Attach to a page via ``attach(page)``. Between screenshots, call ``drain()``
    to get a text summary of everything that happened, then reset for the next
    interval. The drained text is passed to the vision judge alongside the
    screenshot so it can reason about *why* the UI looks a certain way.

    Collected events:
        - console.log / console.error / console.warn messages
        - page errors (uncaught exceptions)
        - failed network requests (status >= 400 or request errors)
        - SSE event stream chunks (tool_use, tool_result, error, complete)

    The collector caps stored events at MAX_EVENTS to avoid unbounded memory.
    """

    MAX_EVENTS = 200
    MAX_CONTEXT_CHARS = 3000  # Truncate context text sent to judge

    def __init__(self):
        self._events: list[dict] = []
        self._page = None

    def attach(self, page) -> "PageEventCollector":
        """Hook into Playwright page events. Call once per page."""
        self._page = page

        page.on("console", self._on_console)
        page.on("pageerror", self._on_page_error)
        page.on("response", self._on_response)
        page.on("requestfailed", self._on_request_failed)

        return self

    def _on_console(self, msg):
        """Capture console.log/warn/error messages."""
        level = msg.type  # "log", "error", "warning", "info", "debug"
        if level in ("debug", "info"):
            return  # Skip noise — only collect warn/error/log
        text = msg.text[:300]
        if len(self._events) < self.MAX_EVENTS:
            self._events.append({"type": "console", "level": level, "text": text})

    def _on_page_error(self, error):
        """Capture uncaught page exceptions."""
        if len(self._events) < self.MAX_EVENTS:
            self._events.append({
                "type": "page_error",
                "text": str(error)[:300],
            })

    def _on_response(self, response):
        """Capture failed HTTP responses and SSE event data."""
        url = response.url
        status = response.status

        # Failed requests (4xx, 5xx)
        if status >= 400 and len(self._events) < self.MAX_EVENTS:
            self._events.append({
                "type": "http_error",
                "status": status,
                "url": _truncate_url(url),
            })

        # SSE stream events — capture key event types from /api/chat
        if "/api/chat" in url or "/api/invoke" in url:
            if len(self._events) < self.MAX_EVENTS:
                self._events.append({
                    "type": "sse_response",
                    "status": status,
                    "url": _truncate_url(url),
                })

    def _on_request_failed(self, request):
        """Capture network failures (DNS, connection refused, etc.)."""
        if len(self._events) < self.MAX_EVENTS:
            self._events.append({
                "type": "request_failed",
                "url": _truncate_url(request.url),
                "failure": request.failure or "unknown",
            })

    def drain(self) -> str:
        """Return a text summary of collected events and reset the buffer.

        Returns empty string if no interesting events were collected.
        """
        if not self._events:
            return ""

        lines = []
        console_errors = [e for e in self._events if e["type"] == "console" and e.get("level") == "error"]
        console_warnings = [e for e in self._events if e["type"] == "console" and e.get("level") == "warning"]
        page_errors = [e for e in self._events if e["type"] == "page_error"]
        http_errors = [e for e in self._events if e["type"] == "http_error"]
        request_failures = [e for e in self._events if e["type"] == "request_failed"]
        sse_responses = [e for e in self._events if e["type"] == "sse_response"]

        if page_errors:
            lines.append(f"PAGE ERRORS ({len(page_errors)}):")
            for e in page_errors[:5]:
                lines.append(f"  - {e['text']}")

        if console_errors:
            lines.append(f"CONSOLE ERRORS ({len(console_errors)}):")
            for e in console_errors[:5]:
                lines.append(f"  - {e['text']}")

        if http_errors:
            lines.append(f"FAILED HTTP REQUESTS ({len(http_errors)}):")
            for e in http_errors[:5]:
                lines.append(f"  - {e['status']} {e['url']}")

        if request_failures:
            lines.append(f"NETWORK FAILURES ({len(request_failures)}):")
            for e in request_failures[:3]:
                lines.append(f"  - {e['url']}: {e['failure']}")

        if sse_responses:
            lines.append(f"SSE CHAT RESPONSES ({len(sse_responses)}):")
            for e in sse_responses[:3]:
                lines.append(f"  - {e['status']} {e['url']}")

        if console_warnings:
            lines.append(f"CONSOLE WARNINGS ({len(console_warnings)}):")
            for e in console_warnings[:3]:
                lines.append(f"  - {e['text']}")

        self._events.clear()

        context = "\n".join(lines)
        if len(context) > self.MAX_CONTEXT_CHARS:
            context = context[: self.MAX_CONTEXT_CHARS - 20] + "\n... (truncated)"
        return context


def _truncate_url(url: str, max_len: int = 120) -> str:
    """Shorten URLs for context text."""
    if len(url) <= max_len:
        return url
    return url[:max_len - 3] + "..."


class ScreenshotCapture:
    """Captures and hashes screenshots during Playwright browser journeys.

    Reuses the BrowserRecorder authentication pattern from browser_recorder.py:
    logs in once via Cognito (or skips in dev mode), caches the storage state,
    and reuses it across all journeys.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:3000",
        run_id: str = None,
        output_dir: str = None,
        headless: bool = True,
        viewport_width: int = 1440,
        viewport_height: int = 900,
        auth_email: Optional[str] = None,
        auth_password: Optional[str] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        self.headless = headless
        self.viewport = {"width": viewport_width, "height": viewport_height}
        self.auth_email = auth_email or os.environ.get("EAGLE_TEST_EMAIL")
        self.auth_password = auth_password or os.environ.get("EAGLE_TEST_PASSWORD")

        if output_dir is None:
            repo_root = Path(__file__).resolve().parent.parent.parent
            output_dir = str(repo_root / "data" / "e2e-judge" / "screenshots")
        self.output_dir = os.path.join(output_dir, self.run_id)
        os.makedirs(self.output_dir, exist_ok=True)

        self._pw = None
        self._browser = None
        self._storage_state = None
        self._screenshots: list[dict] = []  # collected (path, sha256, journey, step)
        self._event_collector: Optional[PageEventCollector] = None

    async def start(self):
        """Launch Playwright + Chromium and authenticate."""
        from playwright.async_api import async_playwright

        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=self.headless)
        print(f"  [capture] Chromium launched (headless={self.headless})")

        await self._authenticate()
        print(f"  [capture] Screenshots will be saved to: {self.output_dir}")

    async def _authenticate(self):
        """Log in once and cache storage state. Mirrors browser_recorder.py."""
        context = await self._browser.new_context(viewport=self.viewport)
        page = await context.new_page()

        await page.goto(self.base_url, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        if "/login" in page.url:
            if not self.auth_email or not self.auth_password:
                await context.close()
                raise RuntimeError(
                    "Auth required but no credentials. "
                    "Set EAGLE_TEST_EMAIL/EAGLE_TEST_PASSWORD or --auth-email/--auth-password."
                )

            print(f"  [capture] Logging in as {self.auth_email}...")
            await page.fill("#email", self.auth_email)
            await page.fill("#password", self.auth_password)
            await page.click("button[type='submit']")

            for _ in range(20):
                await page.wait_for_timeout(1000)
                if "/login" not in page.url:
                    break
            else:
                await context.close()
                raise RuntimeError("Login timed out — still on login page")

            print("  [capture] Authenticated successfully")
        else:
            print("  [capture] No auth required (dev mode)")

        self._storage_state = await context.storage_state()
        await context.close()

    async def stop(self):
        """Tear down browser and Playwright."""
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()
        print(f"  [capture] Done. {len(self._screenshots)} screenshots captured.")

    async def new_page(self) -> "Page":
        """Create a new browser context + page with cached auth state.

        Automatically attaches a PageEventCollector to capture console logs,
        network errors, and SSE events for judge context.
        """
        context = await self._browser.new_context(
            viewport=self.viewport,
            storage_state=self._storage_state,
        )
        page = await context.new_page()
        self._event_collector = PageEventCollector().attach(page)
        return page

    async def take(
        self,
        page,
        journey: str,
        step_name: str,
        description: str,
        full_page: bool = True,
    ) -> dict:
        """Take a screenshot, compute SHA-256, and drain frontend event context.

        Args:
            page: Playwright Page object.
            journey: Journey name (e.g., "chat", "admin").
            step_name: Step identifier (e.g., "01_page_load").
            description: Human-readable description of what should be on screen.
            full_page: Whether to capture the full scrollable page.

        Returns:
            Dict with path, sha256, journey, step_name, description,
            and page_context (frontend events captured since last screenshot).
        """
        journey_dir = os.path.join(self.output_dir, journey)
        os.makedirs(journey_dir, exist_ok=True)

        filepath = os.path.join(journey_dir, f"{step_name}.png")
        screenshot_bytes = await page.screenshot(full_page=full_page)

        with open(filepath, "wb") as f:
            f.write(screenshot_bytes)

        sha256 = compute_sha256(screenshot_bytes)

        # Drain frontend events collected since the last screenshot
        page_context = ""
        if self._event_collector:
            page_context = self._event_collector.drain()

        entry = {
            "path": filepath,
            "sha256": sha256,
            "journey": journey,
            "step_name": step_name,
            "description": description,
            "page_context": page_context,
        }
        self._screenshots.append(entry)

        ctx_tag = f" +{len(page_context)}ch context" if page_context else ""
        print(f"  [capture] {journey}/{step_name} ({sha256[:12]}...){ctx_tag}")
        return entry

    @property
    def screenshots(self) -> list[dict]:
        """All screenshots captured so far."""
        return list(self._screenshots)

    @property
    def manifest(self) -> dict:
        """Full manifest of the capture run."""
        return {
            "run_id": self.run_id,
            "base_url": self.base_url,
            "total_screenshots": len(self._screenshots),
            "screenshots": self._screenshots,
        }
