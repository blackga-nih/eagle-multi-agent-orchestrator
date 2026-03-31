"""
Heuristic conversation quality scorer for EAGLE.

Scores conversations 0-100 based on:
- Completion without error (+30)
- Tool success rate (+20)
- Document generated if requested (+15)
- Response length reasonableness (+10)
- Low follow-up/retry count (+15)
- Error deductions (-10 each)

Also exposes reusable helpers for eval reports: clamping, tool-call subscores,
rollup aggregates, confidence from evidence depth, and score bands.
"""

from __future__ import annotations

import logging
import math
from typing import Any

logger = logging.getLogger("eagle.telemetry.scorer")

# ── Normalized score helpers ─────────────────────────────────────────────


def clamp_score_0_100(value: float | int) -> int:
    """Clamp a numeric value to an integer in [0, 100]."""
    return int(round(max(0.0, min(100.0, float(value)))))


def normalize_to_score_100(value: float, src_min: float, src_max: float) -> int:
    """Linearly map ``value`` from ``[src_min, src_max]`` to [0, 100].

    If the source range is degenerate, returns 50.
    """
    if src_max <= src_min:
        return 50
    t = (float(value) - src_min) / (src_max - src_min)
    return clamp_score_0_100(t * 100.0)


# ── Score bands (interpretation) ───────────────────────────────────────────


def score_band_label(score: int) -> str:
    """Human-readable quality band for a 0-100 score."""
    s = clamp_score_0_100(score)
    if s >= 90:
        return "Excellent"
    if s >= 75:
        return "Strong"
    if s >= 60:
        return "Adequate"
    if s >= 40:
        return "Weak"
    return "Critical"


def score_band_description(score: int) -> str:
    """One-line interpretation for reports."""
    band = score_band_label(score)
    hints = {
        "Excellent": "Meets or exceeds typical production expectations.",
        "Strong": "Solid run; minor gaps only.",
        "Adequate": "Acceptable but with visible gaps or risk areas.",
        "Weak": "Significant issues; investigate before relying on results.",
        "Critical": "Severe failures or missing evidence; not reliable.",
    }
    return hints[band]


# ── Tool-call scoring ─────────────────────────────────────────────────────

# Pairs that often reflect a sensible retrieval / reasoning chain in EAGLE evals.
_GOOD_TOOL_PAIRS: frozenset[tuple[str, str]] = frozenset(
    {
        ("knowledge_search", "knowledge_fetch"),
        ("search_far", "knowledge_fetch"),
        ("search_far", "knowledge_search"),
        ("search_far", "legal_counsel"),
        ("query_compliance_matrix", "knowledge_search"),
        ("knowledge_search", "legal_counsel"),
    }
)


def extract_tool_calls_from_strands_trace(trace: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Normalize eval ``trace`` JSON to the structure expected by ``score_tool_calls``.

    Each item: ``{"name": str, "input": dict, "success": bool, "order": int}``.
    """
    out: list[dict[str, Any]] = []
    if not trace:
        return out
    order = 0
    for msg in trace:
        if msg.get("type") != "AssistantMessage":
            continue
        for block in msg.get("content") or []:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "tool_use":
                continue
            name = (block.get("tool") or block.get("name") or "").strip()
            raw_in = block.get("input")
            inp: dict[str, Any] = raw_in if isinstance(raw_in, dict) else {}
            out.append({"name": name, "input": inp, "success": True, "order": order})
            order += 1
    return out


def _legacy_calls_from_timings(
    tool_timings: list[dict] | None,
    tool_failures: list[dict] | None,
    tools_called: list[str] | None,
) -> list[dict[str, Any]]:
    """Build call records from streaming/telemetry-style inputs."""
    fail_names = {str(f.get("tool_name", "")) for f in (tool_failures or [])}
    calls: list[dict[str, Any]] = []
    for i, t in enumerate(tool_timings or []):
        name = str(t.get("tool_name", "") or "")
        raw_in = t.get("input")
        inp = raw_in if isinstance(raw_in, dict) else {}
        calls.append(
            {
                "name": name,
                "input": inp,
                "success": name not in fail_names,
                "order": i,
            }
        )
    if not calls and tools_called:
        for i, name in enumerate(tools_called):
            calls.append({"name": name, "input": {}, "success": True, "order": i})
    return calls


def score_tool_calls(
    calls: list[dict[str, Any]],
    *,
    log_text: str = "",
    status_pass: bool = True,
) -> dict[str, Any]:
    """Score tool usage on four dimensions (each 0-25, sum 0-100).

    - **selection**: diversity and presence of tools when work was expected
    - **parameters**: non-empty argument payloads (weak signal in many eval fixtures)
    - **execution**: pass/fail heuristics from ``status_pass`` and log keywords
    - **sequence**: common sensible orderings; light penalty for noisy repeats

    This is heuristic; traces with empty ``input`` {} still score neutrally on parameters.
    """
    breakdown: dict[str, int] = {}
    lower = log_text.lower()
    log_suggests_failure = any(
        kw in lower
        for kw in (
            "tool error",
            "tool failed",
            "traceback",
            "exception:",
            "invoke failed",
            "error calling tool",
        )
    )
    names = [str(c.get("name") or "") for c in calls]
    n = len(names)
    uniq = len({x for x in names if x})

    # Selection (0-25)
    if n == 0:
        breakdown["selection"] = 12
    else:
        diversity = uniq / max(n, 1)
        breadth = min(n, 5) / 5.0
        breakdown["selection"] = clamp_score_0_100(25.0 * (0.55 * diversity + 0.45 * breadth))

    # Parameters (0-25): fraction of calls with non-empty JSON input
    if n == 0:
        breakdown["parameters"] = 12
    else:
        nonempty = sum(1 for c in calls if isinstance(c.get("input"), dict) and len(c["input"]) > 0)
        frac = nonempty / max(n, 1)
        # Baseline 0.5 so empty-input traces are not punished harshly
        breakdown["parameters"] = clamp_score_0_100(25.0 * (0.5 + 0.5 * frac))

    # Execution (0-25)
    any_failed = any(c.get("success") is False for c in calls)
    if status_pass and not any_failed and not log_suggests_failure:
        breakdown["execution"] = 25
    elif status_pass and not any_failed:
        breakdown["execution"] = 18
    elif status_pass:
        breakdown["execution"] = 10
    else:
        breakdown["execution"] = 4

    # Sequence (0-25)
    if n < 2:
        breakdown["sequence"] = 18 if n == 1 else 15
    else:
        seq_pts = 10
        for i in range(n - 1):
            pair = (names[i], names[i + 1])
            if pair in _GOOD_TOOL_PAIRS:
                seq_pts += 5
        for i in range(n - 1):
            if names[i] and names[i] == names[i + 1]:
                seq_pts -= 3
        breakdown["sequence"] = clamp_score_0_100(float(min(25, max(0, seq_pts))))

    total = clamp_score_0_100(sum(breakdown.values()))
    return {
        "score": total,
        "breakdown": breakdown,
        "band": score_band_label(total),
        "call_count": n,
        "unique_tools": uniq,
    }


# ── Confidence from evidence depth ─────────────────────────────────────────


def confidence_from_evidence(
    *,
    response_chars: int = 0,
    num_tool_calls: int = 0,
    trace_steps: int = 0,
    indicator_hit_ratio: float | None = None,
    lf_pass_ratio: float | None = None,
) -> dict[str, Any]:
    """0-100 confidence based on how much observable evidence supports the run.

    Higher when responses are substantive, tools/steps exist, indicators match,
    and Langfuse checks (if provided) pass. Missing optional signals are treated
    as neutral rather than penalizing.
    """
    parts: dict[str, float] = {}

    # Response depth (0-30): saturates past a few thousand chars
    char_score = 30.0 * (1.0 - math.exp(-max(0, response_chars) / 2500.0))
    parts["response_depth"] = char_score

    # Tool / trace activity (0-25)
    activity = min(25.0, 6.0 * num_tool_calls + 2.0 * max(0, trace_steps - num_tool_calls))
    parts["tool_trace"] = activity

    # Indicators (0-25) — optional
    if indicator_hit_ratio is not None:
        r = max(0.0, min(1.0, float(indicator_hit_ratio)))
        parts["indicators"] = 25.0 * r
    else:
        parts["indicators"] = 12.5

    # Langfuse validation (0-20) — optional
    if lf_pass_ratio is not None:
        r = max(0.0, min(1.0, float(lf_pass_ratio)))
        parts["langfuse"] = 20.0 * r
    else:
        parts["langfuse"] = 10.0

    raw = sum(parts.values())
    # Normalize weights to 100 (fixed max sum = 30+25+25+20 = 100)
    score = clamp_score_0_100(raw)
    return {
        "score": score,
        "breakdown": {k: round(v, 2) for k, v in parts.items()},
        "band": score_band_label(score),
    }


# ── Rollup eval scoring ─────────────────────────────────────────────────────


def rollup_eval_backend_only(
    *,
    tier_scores_0_100: list[float],
    overall_pass_rate: float,
    tier_weight: float = 0.55,
) -> dict[str, Any]:
    """Combine per-tier quality scores with binary pass rate (backend / Strands only).

    ``tier_scores_0_100`` should contain one entry per executed backend tier
    (e.g. unit mean, integration mean). ``overall_pass_rate`` is passed_tests/total_tests.
    """
    pr = max(0.0, min(1.0, float(overall_pass_rate)))
    mean_tier = sum(tier_scores_0_100) / len(tier_scores_0_100) if tier_scores_0_100 else 0.0
    w = max(0.0, min(1.0, tier_weight))
    combined = w * mean_tier + (1.0 - w) * (pr * 100.0)
    score = clamp_score_0_100(combined)
    return {
        "score": score,
        "band": score_band_label(score),
        "mean_tier_score": round(mean_tier, 2),
        "pass_rate": pr,
        "mode": "backend_only",
    }


def rollup_eval_full_stack(
    backend_rollup: dict[str, Any],
    *,
    e2e_pass_rate: float | None,
    e2e_weight: float = 0.28,
) -> dict[str, Any]:
    """Blend backend rollup with E2E pass rate when E2E ran."""
    if e2e_pass_rate is None:
        return {**backend_rollup, "stack": "backend"}
    ew = max(0.0, min(1.0, e2e_weight))
    pr = max(0.0, min(1.0, float(e2e_pass_rate)))
    base = float(backend_rollup.get("score", 0))
    combined = (1.0 - ew) * base + ew * (pr * 100.0)
    score = clamp_score_0_100(combined)
    out = {**backend_rollup, "score": score, "band": score_band_label(score)}
    out["stack"] = "full"
    out["e2e_pass_rate"] = pr
    return out


def eval_run_confidence_from_tiers(
    *,
    tier1: dict[str, Any] | None,
    tier2: dict[str, Any] | None,
    e2e: dict[str, Any] | None,
) -> dict[str, Any]:
    """Confidence for pytest/Playwright aggregate reports (fewer signals than MT JSON)."""
    ran = [t for t in (tier1, tier2, e2e) if t is not None]
    depth = len(ran)
    base = 25 + 18 * depth

    def _n_tests(d: dict[str, Any]) -> int:
        return int(d.get("passed", 0) + d.get("failed", 0) + d.get("errors", 0))

    volume = sum(_n_tests(t) for t in ran)
    vol_pts = min(30.0, volume * 1.5)

    err_pts = 25.0
    for t in ran:
        if t.get("errors", 0) > 0 or t.get("failed", 0) > 0:
            err_pts -= 4
    err_pts = max(0.0, err_pts)

    raw = base + vol_pts + err_pts
    score = clamp_score_0_100(raw)
    return {
        "score": score,
        "breakdown": {
            "tier_coverage": float(base),
            "test_volume": float(vol_pts),
            "stability": float(err_pts),
        },
        "band": score_band_label(score),
        "tiers_executed": depth,
    }


# ── Conversation score (legacy + enriched) ────────────────────────────────


def score_conversation(
    *,
    completed: bool = True,
    error_count: int = 0,
    tool_timings: list[dict] | None = None,
    tool_failures: list[dict] | None = None,
    response_text: str = "",
    tools_called: list[str] | None = None,
    user_message: str = "",
    duration_ms: int = 0,
) -> dict[str, Any]:
    """Score a conversation on a 0-100 scale with breakdown.

    Returns:
        {
            "score": int,
            "breakdown": {component: points},
            "flags": [str],
            "band": str,
            "band_description": str,
            "tool_call_score": {...},
            "confidence": {...},
        }
    """
    score = 0
    breakdown: dict[str, int] = {}
    flags: list[str] = []

    # 1. Completion without error (+30)
    if completed and error_count == 0:
        breakdown["completion"] = 30
        score += 30
    elif completed:
        breakdown["completion"] = 15
        score += 15
        flags.append(f"completed_with_{error_count}_errors")
    else:
        breakdown["completion"] = 0
        flags.append("incomplete")

    # 2. Tool success rate (+20)
    total_tools = len(tool_timings or [])
    failed_tools = len(tool_failures or [])
    if total_tools > 0:
        success_rate = (total_tools - failed_tools) / total_tools
        tool_points = int(20 * success_rate)
        breakdown["tool_success"] = tool_points
        score += tool_points
        if failed_tools > 0:
            flags.append(f"{failed_tools}_tool_failures")
    else:
        # No tools used — neutral
        breakdown["tool_success"] = 15
        score += 15

    # 3. Document generated if requested (+15)
    doc_keywords = [
        "generate",
        "create",
        "draft",
        "write",
        "produce",
        "sow",
        "igce",
        "document",
    ]
    user_wants_doc = any(kw in user_message.lower() for kw in doc_keywords)
    doc_tools = ["generate_document", "create_document", "export_document"]
    doc_generated = any(t in (tools_called or []) for t in doc_tools)

    if user_wants_doc and doc_generated:
        breakdown["document_delivery"] = 15
        score += 15
    elif user_wants_doc and not doc_generated:
        breakdown["document_delivery"] = 0
        flags.append("document_requested_not_generated")
    else:
        # Not relevant — give partial credit
        breakdown["document_delivery"] = 10
        score += 10

    # 4. Response length reasonableness (+10)
    resp_len = len(response_text)
    if 50 <= resp_len <= 10000:
        breakdown["response_quality"] = 10
        score += 10
    elif resp_len > 10000:
        breakdown["response_quality"] = 7
        score += 7
        flags.append("very_long_response")
    elif resp_len > 0:
        breakdown["response_quality"] = 5
        score += 5
        flags.append("short_response")
    else:
        breakdown["response_quality"] = 0
        flags.append("empty_response")

    # 5. Reasonable duration (+15)
    if 500 <= duration_ms <= 120000:
        breakdown["duration"] = 15
        score += 15
    elif duration_ms < 500:
        breakdown["duration"] = 5
        score += 5
        flags.append("suspiciously_fast")
    elif duration_ms <= 300000:
        breakdown["duration"] = 10
        score += 10
        flags.append("slow_response")
    else:
        breakdown["duration"] = 0
        flags.append("timeout_duration")

    # 6. Error deductions
    error_deduction = min(error_count * 10, 30)
    if error_deduction > 0:
        breakdown["error_penalty"] = -error_deduction
        score -= error_deduction

    # Clamp
    score = clamp_score_0_100(score)

    calls = _legacy_calls_from_timings(tool_timings, tool_failures, tools_called)
    tool_call_score = score_tool_calls(
        calls,
        log_text="",
        status_pass=completed and error_count == 0,
    )
    ind_ratio: float | None = None
    confidence = confidence_from_evidence(
        response_chars=resp_len,
        num_tool_calls=len(calls),
        trace_steps=len(tool_timings or []) or len(calls),
        indicator_hit_ratio=ind_ratio,
        lf_pass_ratio=None,
    )

    return {
        "score": score,
        "breakdown": breakdown,
        "flags": flags,
        "band": score_band_label(score),
        "band_description": score_band_description(score),
        "tool_call_score": tool_call_score,
        "confidence": confidence,
    }
