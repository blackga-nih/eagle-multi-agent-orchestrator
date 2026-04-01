"""User Document Tools for conversational attachment injection.

These tools allow the AI agent to:
1. List documents uploaded by the user
2. Get the text content of a specific document

This enables the user to say "Create an SOW from my requirements doc" and have
the model find and use the uploaded document automatically.
"""

import logging
from typing import Optional

logger = logging.getLogger("eagle.user_document_tools")


# -- Tool Schemas (Anthropic tool_use format) ----------------------------------


LIST_USER_DOCUMENTS_TOOL = {
    "name": "list_user_documents",
    "description": (
        "List documents uploaded by the current user. Use this to find documents "
        "the user has uploaded that can be used as source material for generation. "
        "Returns document metadata including title, type, and whether it's assigned "
        "to a package."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "scope": {
                "type": "string",
                "enum": ["all", "workspace", "assigned"],
                "description": (
                    "Filter documents: 'all' for all documents, 'workspace' for "
                    "unassigned documents, 'assigned' for documents in a package"
                ),
                "default": "all",
            },
            "package_id": {
                "type": "string",
                "description": "Optional package ID to filter by",
            },
        },
        "required": [],
    },
}


GET_DOCUMENT_CONTENT_TOOL = {
    "name": "get_document_content",
    "description": (
        "Get the text content of an uploaded document. Use this after list_user_documents "
        "to retrieve the actual content of a document for use in generation. "
        "Returns the markdown/text content that can be included in prompts."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "document_id": {
                "type": "string",
                "description": "The document_id from list_user_documents",
            },
        },
        "required": ["document_id"],
    },
}


# -- Tool Implementations ------------------------------------------------------


def list_user_documents(
    tenant_id: str,
    user_id: str,
    scope: str = "all",
    package_id: Optional[str] = None,
) -> dict:
    """List documents uploaded by a user.

    Args:
        tenant_id: Tenant identifier
        user_id: User identifier
        scope: "all", "workspace", or "assigned"
        package_id: Optional package filter

    Returns:
        Dict with documents list and count
    """
    from ..unified_document_store import list_user_documents as store_list_user_docs
    from ..unified_document_store import list_package_documents

    try:
        if package_id:
            docs = list_package_documents(tenant_id, package_id, limit=50)
        else:
            docs = store_list_user_docs(tenant_id, user_id, scope=scope, limit=50)

        # Simplify for agent consumption
        simplified = []
        for doc in docs:
            simplified.append({
                "document_id": doc.get("document_id"),
                "title": doc.get("title"),
                "doc_type": doc.get("doc_type"),
                "filename": doc.get("original_filename") or doc.get("filename"),
                "package_id": doc.get("package_id"),
                "is_deliverable": doc.get("is_deliverable", False),
                "created_at": doc.get("created_at"),
            })

        return {
            "success": True,
            "documents": simplified,
            "count": len(simplified),
        }
    except Exception as e:
        logger.error("Failed to list user documents: %s", e)
        return {
            "success": False,
            "error": str(e),
            "documents": [],
            "count": 0,
        }


def get_document_content(
    tenant_id: str,
    user_id: str,
    document_id: str,
    max_chars: int = 50000,
) -> dict:
    """Get the text content of a document.

    Args:
        tenant_id: Tenant identifier
        user_id: User identifier
        document_id: Document UUID
        max_chars: Maximum characters to return

    Returns:
        Dict with document content
    """
    from botocore.exceptions import ClientError

    from ..db_client import get_s3
    from ..document_markdown_service import convert_to_markdown
    from ..unified_document_store import get_document

    try:
        doc = get_document(tenant_id, document_id)
        if not doc:
            return {
                "success": False,
                "error": "Document not found",
            }

        if doc.get("owner_user_id") != user_id:
            return {
                "success": False,
                "error": "Access denied",
            }

        s3 = get_s3()
        content = None
        truncated = False

        # Try markdown sidecar first
        markdown_key = doc.get("markdown_s3_key")
        if markdown_key:
            try:
                response = s3.get_object(Bucket=doc["s3_bucket"], Key=markdown_key)
                content = response["Body"].read().decode("utf-8", errors="replace")
            except ClientError:
                logger.debug("Could not fetch markdown for document %s", document_id)

        # Fall back to extracting from original
        if not content:
            try:
                response = s3.get_object(Bucket=doc["s3_bucket"], Key=doc["s3_key"])
                raw = response["Body"].read()
                content = convert_to_markdown(
                    raw, doc.get("content_type", ""), doc.get("filename", "")
                )
            except ClientError as e:
                logger.error("Failed to fetch document %s: %s", document_id, e)
                return {
                    "success": False,
                    "error": "Failed to retrieve document content",
                }

        if not content:
            content = "[Could not extract text content]"

        # Truncate if too long
        if len(content) > max_chars:
            content = content[:max_chars] + "\n\n[Content truncated...]"
            truncated = True

        return {
            "success": True,
            "document_id": document_id,
            "title": doc.get("title"),
            "doc_type": doc.get("doc_type"),
            "content": content,
            "truncated": truncated,
            "char_count": len(content),
        }
    except Exception as e:
        logger.error("Failed to get document content: %s", e)
        return {
            "success": False,
            "error": str(e),
        }


# -- Tool Registry -------------------------------------------------------------


USER_DOCUMENT_TOOLS = [
    LIST_USER_DOCUMENTS_TOOL,
    GET_DOCUMENT_CONTENT_TOOL,
]


def make_user_document_tools(tenant_id: str, user_id: str) -> list:
    """Create Strands-compatible tool functions for user documents.

    Args:
        tenant_id: Tenant identifier
        user_id: User identifier

    Returns:
        List of tool functions
    """
    from strands import tool

    @tool
    def list_user_documents_tool(
        scope: str = "all",
        package_id: str = "",
    ) -> str:
        """List documents uploaded by the current user.

        Args:
            scope: Filter - 'all', 'workspace' (unassigned), or 'assigned'
            package_id: Optional package ID to filter by
        """
        result = list_user_documents(
            tenant_id=tenant_id,
            user_id=user_id,
            scope=scope,
            package_id=package_id if package_id else None,
        )
        import json
        return json.dumps(result, indent=2, default=str)

    @tool
    def get_document_content_tool(document_id: str) -> str:
        """Get the text content of an uploaded document.

        Args:
            document_id: The document_id from list_user_documents
        """
        result = get_document_content(
            tenant_id=tenant_id,
            user_id=user_id,
            document_id=document_id,
        )
        import json
        return json.dumps(result, indent=2, default=str)

    return [list_user_documents_tool, get_document_content_tool]
