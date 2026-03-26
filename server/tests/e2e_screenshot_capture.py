"""
Screenshot capture utility for E2E judge pipeline.

Extends the BrowserRecorder authentication pattern to capture full-page PNG
screenshots at each test step. Each screenshot is hashed (SHA-256) for cache
lookup by the vision judge.

Usage:
    capture = ScreenshotCapture(base_url="http://ALB-URL", run_id="20260326-140000")
    await capture.start()
    screenshots = await capture.run_journey("chat", journey_chat)
    await capture.stop()
"""

import asyncio
import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from .e2e_judge_cache import compute_sha256


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
        """Create a new browser context + page with cached auth state."""
        context = await self._browser.new_context(
            viewport=self.viewport,
            storage_state=self._storage_state,
        )
        page = await context.new_page()
        return page

    async def take(
        self,
        page,
        journey: str,
        step_name: str,
        description: str,
        full_page: bool = True,
    ) -> dict:
        """Take a screenshot and compute its SHA-256 hash.

        Args:
            page: Playwright Page object.
            journey: Journey name (e.g., "chat", "admin").
            step_name: Step identifier (e.g., "01_page_load").
            description: Human-readable description of what should be on screen.
            full_page: Whether to capture the full scrollable page.

        Returns:
            Dict with path, sha256, journey, step_name, description.
        """
        journey_dir = os.path.join(self.output_dir, journey)
        os.makedirs(journey_dir, exist_ok=True)

        filepath = os.path.join(journey_dir, f"{step_name}.png")
        screenshot_bytes = await page.screenshot(full_page=full_page)

        with open(filepath, "wb") as f:
            f.write(screenshot_bytes)

        sha256 = compute_sha256(screenshot_bytes)

        entry = {
            "path": filepath,
            "sha256": sha256,
            "journey": journey,
            "step_name": step_name,
            "description": description,
        }
        self._screenshots.append(entry)
        print(f"  [capture] {journey}/{step_name} ({sha256[:12]}...)")
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
