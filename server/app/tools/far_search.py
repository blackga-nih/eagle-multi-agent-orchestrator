"""Active FAR search tool handler."""

from __future__ import annotations


def exec_search_far(params: dict, tenant_id: str) -> dict:
    """Search Federal Acquisition Regulation using shared far-database.json."""
    from ..compliance_matrix import search_far as compliance_search_far

    query = params.get("query", "")
    parts_filter = params.get("parts", None)

    results = compliance_search_far(query, parts_filter)

    if not results:
        results = [
            {
                "part": "1",
                "section": "1.102",
                "title": "Statement of Guiding Principles",
                "summary": "Deliver best value to the Government, satisfy the customer, minimize administrative costs, conduct business with integrity.",
                "applicability": "All federal acquisitions",
                "s3_keys": [],
            }
        ]

    return {
        "query": query,
        "parts_searched": parts_filter or ["all"],
        "results_count": len(results),
        "clauses": results[:15],
        "source": "FAR/DFARS/HHSAR reference database (eagle-plugin/data/far-database.json)",
        "note": "Call knowledge_fetch on s3_keys to read the full FAR document before answering.",
    }
