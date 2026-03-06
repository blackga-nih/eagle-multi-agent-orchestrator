"""
Package Context Service -- Resolves active package for chat sessions.

Determines whether a chat session is operating in "package mode" (documents
route to a specific acquisition package) or "workspace mode" (standalone docs).

Context resolution order:
1. Explicit package_id in request body (highest priority)
2. active_package_id in session metadata
3. No package context (workspace mode)
"""
import logging
from dataclasses import dataclass
from typing import Optional

from .session_store import get_session, update_session
from .package_store import get_package

logger = logging.getLogger("eagle.package_context")


@dataclass
class PackageContext:
    """Resolved package context for a chat session."""

    mode: str  # "package" or "workspace"
    package_id: Optional[str] = None
    package_title: Optional[str] = None
    acquisition_pathway: Optional[str] = None
    required_documents: Optional[list] = None
    completed_documents: Optional[list] = None

    @property
    def is_package_mode(self) -> bool:
        return self.mode == "package" and self.package_id is not None


def resolve_context(
    tenant_id: str,
    user_id: str,
    session_id: str,
    explicit_package_id: Optional[str] = None,
) -> PackageContext:
    """Resolve the package context for a chat session.

    Args:
        tenant_id: Tenant identifier
        user_id: User identifier
        session_id: Chat session identifier
        explicit_package_id: Package ID explicitly provided in request (overrides session)

    Returns:
        PackageContext with resolved mode and package details
    """
    # Priority 1: Explicit package_id in request
    if explicit_package_id:
        pkg = get_package(tenant_id, explicit_package_id)
        if pkg:
            logger.debug(
                "Package context resolved from explicit ID: %s", explicit_package_id
            )
            return _build_package_context(pkg)
        else:
            logger.warning(
                "Explicit package_id %s not found for tenant %s",
                explicit_package_id, tenant_id
            )
            # Fall through to session metadata

    # Priority 2: Session metadata
    session = get_session(session_id, tenant_id, user_id)
    if session:
        metadata = session.get("metadata", {})
        session_package_id = metadata.get("active_package_id")

        if session_package_id:
            pkg = get_package(tenant_id, session_package_id)
            if pkg:
                logger.debug(
                    "Package context resolved from session metadata: %s",
                    session_package_id
                )
                return _build_package_context(pkg)
            else:
                logger.warning(
                    "Session active_package_id %s not found, clearing from session",
                    session_package_id
                )
                # Clear stale package reference
                clear_active_package(tenant_id, user_id, session_id)

    # Priority 3: No package context (workspace mode)
    logger.debug("No package context found, using workspace mode")
    return PackageContext(mode="workspace")


def set_active_package(
    tenant_id: str,
    user_id: str,
    session_id: str,
    package_id: str,
) -> Optional[PackageContext]:
    """Set the active package for a session.

    Args:
        tenant_id: Tenant identifier
        user_id: User identifier
        session_id: Chat session identifier
        package_id: Package ID to set as active

    Returns:
        PackageContext if package exists and was set, None otherwise
    """
    # Verify package exists
    pkg = get_package(tenant_id, package_id)
    if not pkg:
        logger.warning(
            "Cannot set active package: %s not found for tenant %s",
            package_id, tenant_id
        )
        return None

    # Get current session metadata
    session = get_session(session_id, tenant_id, user_id)
    if not session:
        logger.warning(
            "Cannot set active package: session %s not found", session_id
        )
        return None

    # Update session metadata
    metadata = session.get("metadata", {})
    metadata["active_package_id"] = package_id

    update_session(
        session_id=session_id,
        tenant_id=tenant_id,
        user_id=user_id,
        updates={"metadata": metadata}
    )

    logger.info(
        "Set active package %s for session %s", package_id, session_id
    )
    return _build_package_context(pkg)


def clear_active_package(
    tenant_id: str,
    user_id: str,
    session_id: str,
) -> bool:
    """Clear the active package from a session (switch to workspace mode).

    Args:
        tenant_id: Tenant identifier
        user_id: User identifier
        session_id: Chat session identifier

    Returns:
        True if cleared successfully, False otherwise
    """
    session = get_session(session_id, tenant_id, user_id)
    if not session:
        logger.warning(
            "Cannot clear active package: session %s not found", session_id
        )
        return False

    metadata = session.get("metadata", {})
    if "active_package_id" in metadata:
        del metadata["active_package_id"]
        update_session(
            session_id=session_id,
            tenant_id=tenant_id,
            user_id=user_id,
            updates={"metadata": metadata}
        )
        logger.info("Cleared active package for session %s", session_id)

    return True


def get_active_package_id(
    tenant_id: str,
    user_id: str,
    session_id: str,
) -> Optional[str]:
    """Get the active package ID for a session without full resolution.

    Args:
        tenant_id: Tenant identifier
        user_id: User identifier
        session_id: Chat session identifier

    Returns:
        Package ID if set, None otherwise
    """
    session = get_session(session_id, tenant_id, user_id)
    if not session:
        return None

    metadata = session.get("metadata", {})
    return metadata.get("active_package_id")


def _build_package_context(pkg: dict) -> PackageContext:
    """Build a PackageContext from a package record."""
    return PackageContext(
        mode="package",
        package_id=pkg.get("package_id"),
        package_title=pkg.get("title"),
        acquisition_pathway=pkg.get("acquisition_pathway"),
        required_documents=pkg.get("required_documents", []),
        completed_documents=pkg.get("completed_documents", []),
    )
