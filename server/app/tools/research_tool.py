"""Composite research tool — KB search + auto-fetch + dynamic checklist selection.

Used by the legacy dispatch path. The Strands @tool version lives in
strands_agentic_service.py and shares the same logic inline.
"""

from __future__ import annotations

import logging

from .knowledge_tools import exec_knowledge_fetch, exec_knowledge_search

logger = logging.getLogger("eagle.tools.research")

_CHECKLIST_QUERIES: dict[str, str] = {
    "sap": "simplified acquisition SAP PMR checklist",
    "negotiated": "negotiated procurement PMR common requirements checklist",
    "fss": "federal supply schedule FSS PMR checklist",
    "bpa-est": "blanket purchase agreement BPA PMR checklist",
    "bpa-call": "blanket purchase agreement BPA call order PMR checklist",
    "idiq": "IDIQ indefinite delivery PMR checklist",
    "idiq-order": "IDIQ task order PMR checklist",
    "sole": "sole source PMR common requirements checklist",
}


def _detect_method(acquisition_method: str, query: str, contract_value: float) -> str:
    """Infer acquisition method from explicit param, query text signals, or value."""
    if acquisition_method:
        am = acquisition_method.lower().strip()
        aliases = {
            "sole source": "sole", "sole-source": "sole", "j&a": "sole",
            "gsa": "fss", "schedule": "fss", "fss": "fss",
            "bpa": "bpa-est", "blanket purchase": "bpa-est",
            "idiq": "idiq-order", "task order": "idiq-order",
            "micro": "micro", "purchase card": "micro", "gpc": "micro",
            "sap": "sap", "simplified": "sap",
            "negotiated": "negotiated", "full and open": "negotiated",
        }
        for alias, method in aliases.items():
            if alias in am:
                return method
        if am in _CHECKLIST_QUERIES:
            return am

    q = query.lower()
    if any(s in q for s in ("sole source", "sole-source", "only one source", "j&a")):
        return "sole"
    if any(s in q for s in ("gsa", "schedule", "fss")):
        return "fss"
    if any(s in q for s in ("bpa", "blanket purchase")):
        return "bpa-est"
    if any(s in q for s in ("idiq", "task order")):
        return "idiq-order"
    if any(s in q for s in ("micro", "purchase card", "gpc")):
        return "micro"

    if contract_value > 0:
        if contract_value < 15000:
            return "micro"
        if contract_value <= 350000:
            return "sap"
        return "negotiated"

    return "sap"


_MICRO_PURCHASE_DROP_PREFIXES: tuple[str, ...] = (
    # Protest guidance is irrelevant for FAR 13.2 micro-purchases — there's no
    # competitive selection to protest. UC2.1 review (2026-04-29) flagged that
    # EAGLE was pulling these into a microscope purchase request.
    "eagle-knowledge-base/approved/legal-counselor/protest-guidance/",
    # J&A justifications are FAR Part 6 / FAR 8.4 territory; no J&A is required
    # for micro-purchases per FAR 13.106-2(a) (single quote acceptable).
    "eagle-knowledge-base/approved/compliance-strategist/justifications/",
    "eagle-knowledge-base/approved/legal-counselor/appropriations-law/",
)

# Topic patterns that re-enable the dropped folders even under micro-purchase.
# If the user explicitly asks about protest, J&A, or appropriations,
# the filter is bypassed — we only drop when the topic is unrelated.
_MICRO_PURCHASE_DROP_BYPASS: tuple[str, ...] = (
    "protest", "j&a", "jofoc", "jefo", "appropriation", "bona fide",
    "limited source", "sole source", "justification",
)


def _filter_results_by_method(
    results: list[dict], method: str, query: str
) -> tuple[list[dict], list[dict]]:
    """Drop method-irrelevant docs from search results.

    Returns (kept, dropped) so callers can log what was filtered. Dropped
    entries are NOT returned to the model — keeping them out of the auto-fetch
    pool prevents the agent from over-fetching irrelevant content (UC2.1 root
    cause).
    """
    if method != "micro":
        return list(results or []), []

    # Bypass: if the user explicitly asked about protest/J&A/appropriations,
    # those docs ARE relevant even on a micro-purchase.
    q_lower = (query or "").lower()
    if any(b in q_lower for b in _MICRO_PURCHASE_DROP_BYPASS):
        return list(results or []), []

    kept: list[dict] = []
    dropped: list[dict] = []
    for r in results or []:
        key = (r.get("s3_key") or "").lower()
        if any(key.startswith(p) for p in _MICRO_PURCHASE_DROP_PREFIXES):
            dropped.append(r)
        else:
            kept.append(r)
    return kept, dropped


def exec_research(
    params: dict, tenant_id: str, session_id: str | None = None,
    user_id: str | None = None,
) -> dict:
    """Execute the composite research tool for the legacy dispatch path."""
    query = params.get("query", "")
    contract_value = float(params.get("contract_value", 0))
    acquisition_method = params.get("acquisition_method", "")
    include_checklist = params.get("include_checklist", True)
    topic = params.get("topic", "")
    document_type = params.get("document_type", "")

    # 1. Knowledge search
    search_params = {
        k: v for k, v in {
            "query": query, "topic": topic,
            "document_type": document_type, "limit": 10,
        }.items() if v
    }
    search_result = exec_knowledge_search(search_params, tenant_id, session_id, user_id=user_id)

    # 1b. Method-aware filtering — drop docs whose prefix is irrelevant to the
    # detected acquisition method (PR2 from the 2026-04-29 triage spec). Done
    # BEFORE auto-fetch so we don't waste Bedrock calls on docs we'll drop.
    method = _detect_method(acquisition_method, query, contract_value)
    raw_results = search_result.get("results", [])
    kept_results, dropped_results = _filter_results_by_method(
        raw_results, method, query
    )

    # 2. Auto-fetch top 4 (from filtered results)
    fetched_docs = []
    fetched_keys: set[str] = set()
    for r in kept_results[:4]:
        s3_key = r.get("s3_key")
        if s3_key and s3_key not in fetched_keys:
            content = exec_knowledge_fetch({"s3_key": s3_key}, tenant_id, session_id, user_id=user_id)
            if "error" not in content:
                fetched_keys.add(s3_key)
                fetched_docs.append({
                    "title": r.get("title", ""),
                    "s3_key": s3_key,
                    "content": content.get("content", "")[:15000],
                })

    # 3. Dynamic checklist search (isolated query — separate from general KB search)
    checklist_content: dict[str, str] = {}

    if include_checklist and method != "micro":
        cl_query = _CHECKLIST_QUERIES.get(method, "PMR common requirements checklist")
        cl_query += " file reviewer FRC"

        cl_result = exec_knowledge_search(
            {"document_type": "checklist", "query": cl_query, "limit": 5},
            tenant_id, session_id, user_id=user_id,
        )

        for r in cl_result.get("results", [])[:4]:
            s3_key = r.get("s3_key")
            if s3_key and s3_key not in fetched_keys:
                result = exec_knowledge_fetch({"s3_key": s3_key}, tenant_id, session_id, user_id=user_id)
                if "content" in result:
                    fetched_keys.add(s3_key)
                    checklist_content[r.get("title", s3_key)] = result["content"][:20000]

    return {
        # kb_results is the filtered list — irrelevant docs (e.g. protest
        # guidance for micro-purchases) are dropped before reaching the model.
        "kb_results": kept_results,
        "fetched_documents": fetched_docs,
        "checklists": checklist_content,
        "detected_method": method,
        "_filtered_out": [
            {"s3_key": r.get("s3_key"), "title": r.get("title")}
            for r in dropped_results
        ],
        "_guidance": (
            "Use checklists to cross-reference document requirements. "
            "The PMR checklist is HHS/NIH-specific — items there supplement FAR requirements. "
            "The FRC (File Reviewer's Checklist) is NIH's internal review standard. "
            "Cite KB documents and checklist references in your response."
        ),
    }
