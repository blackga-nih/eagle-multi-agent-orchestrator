"""Shared S3 document key parsing, validation, and tenant-scoping utilities.

Extracted from spreadsheet_edit_service, document_ai_edit_service, and main
to eliminate duplication and provide a single source of truth for S3 key logic.
"""

from __future__ import annotations

import re
from typing import Optional


def extract_package_document_ref(doc_key: str) -> Optional[dict[str, object]]:
    """Parse a canonical package document S3 key into its components.

    Supports both the canonical layout
    ``eagle/{tenant}/packages/{pkg_id}/{doc_type}/v{version}/{filename}``
    and the legacy layout
    ``eagle/{tenant}/{user}/packages/{pkg_id}/{filename}``.
    """
    canonical = re.match(
        r"^eagle/(?P<tenant>[^/]+)/packages/(?P<package_id>[^/]+)"
        r"/(?P<doc_type>[^/]+)/v(?P<version>\d+)/(?P<filename>[^/]+)$",
        doc_key,
    )
    if canonical:
        info = canonical.groupdict()
        return {
            "tenant_id": info["tenant"],
            "package_id": info["package_id"],
            "doc_type": info["doc_type"],
            "version": int(info["version"]),
            "filename": info["filename"],
        }

    legacy = re.match(
        r"^eagle/(?P<tenant>[^/]+)/(?P<user>[^/]+)/packages"
        r"/(?P<package_id>[^/]+)/(?P<filename>[^/]+)$",
        doc_key,
    )
    if not legacy:
        return None

    info = legacy.groupdict()
    filename = info["filename"]
    stem = filename.rsplit(".", 1)[0]
    doc_type = stem.split("_v", 1)[0] if "_v" in stem else stem
    version = None
    version_match = re.search(r"_v(\d+)", stem)
    if version_match:
        version = int(version_match.group(1))

    return {
        "tenant_id": info["tenant"],
        "package_id": info["package_id"],
        "doc_type": doc_type,
        "version": version,
        "filename": filename,
    }


def extract_workspace_document_ref(doc_key: str) -> Optional[dict[str, str]]:
    """Parse a workspace document S3 key into tenant, user, and filename."""
    match = re.match(
        r"^eagle/(?P<tenant>[^/]+)/(?P<user>[^/]+)/documents/(?P<filename>[^/]+)$",
        doc_key,
    )
    if not match:
        return None
    return match.groupdict()


def is_allowed_document_key(
    doc_key: str, tenant_id: str, user_id: Optional[str] = None
) -> bool:
    """Check if the S3 key is an allowed document within the tenant scope.

    Permits package documents (``eagle/{tenant}/packages/...``) and
    user workspace documents (``eagle/{tenant}/{user}/...``).
    """
    if doc_key.startswith(f"eagle/{tenant_id}/packages/"):
        return True
    if user_id and doc_key.startswith(f"eagle/{tenant_id}/{user_id}/"):
        return True
    return False


def is_tenant_scoped_key(key: str, tenant_id: str) -> bool:
    """Check if the key is already scoped within this tenant's S3 namespace.

    Returns True for any key starting with ``eagle/{tenant_id}/``, meaning
    it should NOT have a user prefix prepended.
    """
    return key.startswith(f"eagle/{tenant_id}/")
