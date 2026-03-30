"""
Vision Judge — evaluates EAGLE UI screenshots using Bedrock Converse.

Sends each screenshot to Claude Sonnet via the Bedrock converse API with
image content blocks. Returns structured JudgmentResult with pass/fail verdict,
confidence, quality score, and detailed reasoning.

The EAGLE application itself uses Haiku 4.5 during test runs (set via
STRANDS_MODEL_ID) to keep app-response costs low. This judge module uses
Sonnet for the best vision evaluation quality.

Usage:
    judge = VisionJudge()
    result = judge.evaluate(screenshot_bytes, "chat", "Page with agent response", "03_response_complete")
"""

import json
import logging
import os
import re

import boto3
from botocore.config import Config

from .e2e_judge_cache import JudgmentResult, JudgeCache, compute_sha256
from .e2e_judge_prompts import get_prompt

logger = logging.getLogger(__name__)

# Default: Claude Sonnet for vision quality.
DEFAULT_JUDGE_MODEL = "us.anthropic.claude-sonnet-4-6"


class VisionJudge:
    """Evaluates screenshots via Bedrock converse with image content blocks."""

    def __init__(
        self,
        model_id: str = None,
        region: str = None,
        cache: JudgeCache = None,
    ):
        self.model_id = model_id or os.getenv("E2E_JUDGE_MODEL", DEFAULT_JUDGE_MODEL)
        self.region = region or os.getenv("AWS_REGION", "us-east-1")
        self.cache = cache or JudgeCache()

        # Bedrock client — same config pattern as strands_agentic_service.py
        self._client = boto3.client(
            "bedrock-runtime",
            region_name=self.region,
            config=Config(
                connect_timeout=30,
                read_timeout=120,
                retries={"max_attempts": 2, "mode": "adaptive"},
            ),
        )

        self._total_calls = 0
        self._cache_hits = 0
        self._input_tokens = 0
        self._output_tokens = 0

    def evaluate(
        self,
        screenshot_bytes: bytes,
        journey: str,
        page_description: str,
        step_description: str,
        page_context: str = "",
    ) -> JudgmentResult:
        """Judge a single screenshot. Checks cache first.

        Args:
            screenshot_bytes: Raw PNG image bytes.
            journey: Journey name (e.g., "chat", "admin", "login").
            page_description: What the page should look like.
            step_description: What this specific step captures.
            page_context: Frontend events captured since the last screenshot
                (console errors, network failures, SSE events). Appended to
                the judge prompt so the model can reason about frontend state.

        Returns:
            JudgmentResult with verdict, score, reasoning, and cache status.
        """
        sha256 = compute_sha256(screenshot_bytes)
        self._total_calls += 1

        # Check cache
        cached = self.cache.get(sha256)
        if cached is not None:
            self._cache_hits += 1
            logger.info(f"Cache hit for {step_description} ({sha256[:12]}...)")
            return cached

        # Cache miss — call Bedrock
        logger.info(f"Judging {step_description} ({sha256[:12]}...) via {self.model_id}")
        prompt = get_prompt(journey, page_description, step_description)

        # Append frontend event context if present
        if page_context:
            prompt += (
                "\n\n--- Frontend Event Context (captured by Playwright) ---\n"
                "The following events were recorded in the browser between the "
                "previous screenshot and this one. Use them to understand errors, "
                "network failures, or SSE streaming state that may explain what "
                "you see in the screenshot.\n\n"
                f"{page_context}"
            )

        try:
            response = self._client.converse(
                modelId=self.model_id,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "image": {
                                    "format": "png",
                                    "source": {"bytes": screenshot_bytes},
                                }
                            },
                            {"text": prompt},
                        ],
                    }
                ],
                inferenceConfig={"maxTokens": 1000, "temperature": 0},
            )

            # Track token usage from Bedrock response
            usage = response.get("usage", {})
            self._input_tokens += usage.get("inputTokens", 0)
            self._output_tokens += usage.get("outputTokens", 0)

            # Parse response
            output_text = response["output"]["message"]["content"][0]["text"]
            judgment = self._parse_judgment(output_text, journey, step_description)

        except Exception as e:
            logger.error(f"Bedrock converse failed for {step_description}: {e}")
            judgment = JudgmentResult(
                verdict="fail",
                confidence=0.0,
                reasoning=f"Vision judge error: {e}",
                ui_quality_score=0,
                issues=[f"Judge call failed: {type(e).__name__}"],
                model_id=self.model_id,
                journey=journey,
                step_name=step_description,
            )

        # Store in cache
        self.cache.put(sha256, judgment)
        return judgment

    def _parse_judgment(self, text: str, journey: str, step_name: str) -> JudgmentResult:
        """Parse the LLM's JSON response into a JudgmentResult."""
        # Strip markdown code fences if present
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Try to extract JSON from surrounding text
            match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
            if match:
                data = json.loads(match.group())
            else:
                return JudgmentResult(
                    verdict="warning",
                    confidence=0.5,
                    reasoning=f"Could not parse judge response as JSON: {text[:200]}",
                    ui_quality_score=5,
                    issues=["Judge response was not valid JSON"],
                    model_id=self.model_id,
                    journey=journey,
                    step_name=step_name,
                )

        return JudgmentResult(
            verdict=data.get("verdict", "warning"),
            confidence=float(data.get("confidence", 0.5)),
            reasoning=data.get("reasoning", ""),
            ui_quality_score=int(data.get("ui_quality_score", 5)),
            issues=data.get("issues", []),
            model_id=self.model_id,
            journey=journey,
            step_name=step_name,
        )

    @property
    def stats(self) -> dict:
        """Return judge call statistics including cost estimate."""
        # Sonnet pricing (Bedrock, us-east-1, as of 2025-05):
        # Input: $3.00/MTok, Output: $15.00/MTok
        # Image tokens: ~1600 tokens per 1440x900 screenshot
        input_cost = (self._input_tokens / 1_000_000) * 3.00
        output_cost = (self._output_tokens / 1_000_000) * 15.00
        total_cost = input_cost + output_cost

        return {
            "total_calls": self._total_calls,
            "cache_hits": self._cache_hits,
            "cache_misses": self._total_calls - self._cache_hits,
            "cache_hit_rate": (
                self._cache_hits / self._total_calls if self._total_calls > 0 else 0
            ),
            "input_tokens": self._input_tokens,
            "output_tokens": self._output_tokens,
            "cost_usd": round(total_cost, 4),
        }
