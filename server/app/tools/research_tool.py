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


def exec_research(
    params: dict, tenant_id: str, session_id: str | None = None
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
    search_result = exec_knowledge_search(search_params, tenant_id, session_id)

    # 2. Auto-fetch top 4
    fetched_docs = []
    fetched_keys: set[str] = set()
    for r in search_result.get("results", [])[:4]:
        s3_key = r.get("s3_key")
        if s3_key and s3_key not in fetched_keys:
            content = exec_knowledge_fetch({"s3_key": s3_key}, tenant_id, session_id)
            if "error" not in content:
                fetched_keys.add(s3_key)
                fetched_docs.append({
                    "title": r.get("title", ""),
                    "s3_key": s3_key,
                    "content": content.get("content", "")[:15000],
                })

    # 3. Dynamic checklist search (isolated query — separate from general KB search)
    checklist_content: dict[str, str] = {}
    method = _detect_method(acquisition_method, query, contract_value)

    if include_checklist and method != "micro":
        cl_query = _CHECKLIST_QUERIES.get(method, "PMR common requirements checklist")
        cl_query += " file reviewer FRC"

        cl_result = exec_knowledge_search(
            {"document_type": "checklist", "query": cl_query, "limit": 5},
            tenant_id, session_id,
        )

        for r in cl_result.get("results", [])[:4]:
            s3_key = r.get("s3_key")
            if s3_key and s3_key not in fetched_keys:
                result = exec_knowledge_fetch({"s3_key": s3_key}, tenant_id, session_id)
                if "content" in result:
                    fetched_keys.add(s3_key)
                    checklist_content[r.get("title", s3_key)] = result["content"][:20000]

    return {
        "kb_results": search_result.get("results", []),
        "fetched_documents": fetched_docs,
        "checklists": checklist_content,
        "detected_method": method,
        "_guidance": (
            "Use checklists to cross-reference document requirements. "
            "The PMR checklist is HHS/NIH-specific — items there supplement FAR requirements. "
            "The FRC (File Reviewer's Checklist) is NIH's internal review standard. "
            "Cite KB documents and checklist references in your response."
        ),
    }
