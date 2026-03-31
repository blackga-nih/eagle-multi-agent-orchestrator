"""
Knowledge Base API Router

Provides endpoints for browsing and searching the EAGLE knowledge base:
- List/search documents
- Aggregate stats
- Fetch document content
- Plugin reference data files
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from ..cognito_auth import UserContext
from .dependencies import get_user_from_header

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/knowledge-base", tags=["knowledge-base"])

_PLUGIN_DATA_FILES = {
    "far-database.json": "FAR/DFARS/HHSAR clause database (~900+ clauses)",
    "matrix.json": "Acquisition decision matrix — thresholds and contract types",
    "thresholds.json": "Fiscal year regulatory thresholds (SAT, MPT, JOFOC)",
    "contract-vehicles.json": "Pre-approved contract vehicles (GSA, NITAAC, etc.)",
}


def _get_dynamo():
    import boto3

    return boto3.resource("dynamodb", region_name=os.getenv("AWS_REGION", "us-east-1"))


@router.get("")
async def api_list_knowledge_base(
    topic: Optional[str] = None,
    document_type: Optional[str] = None,
    agent: Optional[str] = None,
    query: Optional[str] = None,
    limit: int = 50,
    user: UserContext = Depends(get_user_from_header),
):
    """List/search knowledge base documents from the metadata table."""
    from boto3.dynamodb.conditions import Attr

    # If free-text query provided, delegate to the existing search tool
    if query:
        from ..tools.knowledge_tools import exec_knowledge_search

        result = exec_knowledge_search(
            {
                "query": query,
                "topic": topic,
                "document_type": document_type,
                "agent": agent,
                "limit": limit,
            },
            tenant_id=user.tenant_id,
        )
        return {"documents": result.get("results", []), "count": result.get("count", 0)}

    table_name = os.getenv("METADATA_TABLE", "eagle-document-metadata-dev")
    try:
        ddb = _get_dynamo()
        table = ddb.Table(table_name)

        scan_kwargs: dict = {}
        filter_expr = Attr("PK").not_exists()

        if topic:
            filter_expr = filter_expr & Attr("primary_topic").eq(topic)
        if document_type:
            filter_expr = filter_expr & Attr("document_type").eq(document_type)
        if agent:
            filter_expr = filter_expr & Attr("primary_agent").eq(agent)

        scan_kwargs["FilterExpression"] = filter_expr

        items: list = []
        resp = table.scan(**scan_kwargs)
        items.extend(resp.get("Items", []))
        while "LastEvaluatedKey" in resp:
            scan_kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
            resp = table.scan(**scan_kwargs)
            items.extend(resp.get("Items", []))

        items.sort(key=lambda x: x.get("last_updated", ""), reverse=True)
        items = items[:limit]

        documents = []
        for item in items:
            documents.append(
                {
                    "document_id": item.get("document_id", ""),
                    "title": item.get("title", ""),
                    "summary": item.get("summary", ""),
                    "document_type": item.get("document_type", ""),
                    "primary_topic": item.get("primary_topic", ""),
                    "primary_agent": item.get("primary_agent", ""),
                    "authority_level": item.get("authority_level", ""),
                    "keywords": item.get("keywords", [])[:10],
                    "s3_key": item.get("s3_key", ""),
                    "confidence_score": float(item.get("confidence_score", 0)),
                    "word_count": int(item.get("word_count", 0)),
                    "page_count": int(item.get("page_count", 0)),
                    "file_type": item.get("file_type", ""),
                    "last_updated": item.get("last_updated", ""),
                }
            )

        return {"documents": documents, "count": len(documents)}
    except Exception as e:
        logger.error("Knowledge base list error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to list knowledge base")


@router.get("/stats")
async def api_knowledge_base_stats(
    user: UserContext = Depends(get_user_from_header),
):
    """Aggregate knowledge base stats by topic, type, and agent."""
    from boto3.dynamodb.conditions import Attr

    table_name = os.getenv("METADATA_TABLE", "eagle-document-metadata-dev")
    try:
        ddb = _get_dynamo()
        table = ddb.Table(table_name)

        items: list = []
        resp = table.scan(FilterExpression=Attr("PK").not_exists())
        items.extend(resp.get("Items", []))
        while "LastEvaluatedKey" in resp:
            resp = table.scan(
                FilterExpression=Attr("PK").not_exists(),
                ExclusiveStartKey=resp["LastEvaluatedKey"],
            )
            items.extend(resp.get("Items", []))

        by_topic: dict[str, int] = {}
        by_type: dict[str, int] = {}
        by_agent: dict[str, int] = {}
        for item in items:
            t = item.get("primary_topic", "unknown")
            by_topic[t] = by_topic.get(t, 0) + 1
            dt = item.get("document_type", "unknown")
            by_type[dt] = by_type.get(dt, 0) + 1
            a = item.get("primary_agent", "unknown")
            by_agent[a] = by_agent.get(a, 0) + 1

        return {
            "total": len(items),
            "by_topic": dict(
                sorted(by_topic.items(), key=lambda x: x[1], reverse=True)
            ),
            "by_type": dict(sorted(by_type.items(), key=lambda x: x[1], reverse=True)),
            "by_agent": dict(
                sorted(by_agent.items(), key=lambda x: x[1], reverse=True)
            ),
        }
    except Exception as e:
        logger.error("Knowledge base stats error: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500, detail="Failed to get knowledge base stats"
        )


@router.get("/document/{s3_key:path}")
async def api_kb_document(
    s3_key: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Fetch full document content from S3."""
    from ..tools.knowledge_tools import exec_knowledge_fetch

    result = exec_knowledge_fetch({"s3_key": s3_key}, tenant_id=user.tenant_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/plugin-data")
async def api_kb_plugin_data(
    file: Optional[str] = None,
    user: UserContext = Depends(get_user_from_header),
):
    """List or fetch static plugin reference data files."""
    data_dir = (
        Path(__file__).resolve().parent.parent.parent.parent
        / "eagle-plugin"
        / "data"
    )

    if file is None:
        files = []
        for name, description in _PLUGIN_DATA_FILES.items():
            fpath = data_dir / name
            if fpath.exists():
                content = json.loads(fpath.read_text(encoding="utf-8"))
                item_count = (
                    len(content) if isinstance(content, list) else len(content.keys())
                )
                files.append(
                    {
                        "name": name,
                        "description": description,
                        "size_bytes": fpath.stat().st_size,
                        "item_count": item_count,
                    }
                )
        return {"files": files}

    if file not in _PLUGIN_DATA_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file. Allowed: {list(_PLUGIN_DATA_FILES.keys())}",
        )

    fpath = data_dir / file
    if not fpath.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {file}")

    content = json.loads(fpath.read_text(encoding="utf-8"))
    item_count = len(content) if isinstance(content, list) else len(content.keys())
    return {"name": file, "content": content, "item_count": item_count}
