"""
Heuristic conversation quality scorer for EAGLE.

Scores conversations 0-100 based on:
- Completion without error (+30)
- Tool success rate (+20)
- Document generated if requested (+15)
- Response length reasonableness (+10)
- Low follow-up/retry count (+15)
- Error deductions (-10 each)
"""

import logging
from typing import Any

logger = logging.getLogger("eagle.telemetry.scorer")


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
    doc_keywords = ["generate", "create", "draft", "write", "produce", "sow", "igce", "document"]
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
    score = max(0, min(100, score))

    return {
        "score": score,
        "breakdown": breakdown,
        "flags": flags,
    }
