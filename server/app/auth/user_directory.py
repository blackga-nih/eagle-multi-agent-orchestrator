"""DynamoDB-backed user directory: USER#<email> → profile lookup.

Replaces Cognito as the source of truth for tenant assignment, subscription
tier, and admin role. After the Entra OIDC callback we resolve the email
claim to a ``USER#<email>`` row; if missing or disabled the user is "Not
Authorized" and the frontend redirects to ``/not-authorized``.

The single-table layout matches existing EAGLE conventions
(`SESSION#`, `MSG#`, `USAGE#`, `COST#`, `SUB#`).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from botocore.exceptions import BotoCoreError, ClientError

from ..db_client import get_table, item_to_dict, now_iso

logger = logging.getLogger("eagle.auth.directory")


def _user_pk(email: str) -> str:
    return f"USER#{email.strip().lower()}"


@dataclass
class UserProfile:
    email: str
    tenant_id: str
    tier: str
    is_admin: bool
    enabled: bool
    display_name: Optional[str] = None

    @property
    def authorized(self) -> bool:
        return self.enabled


def get_user_profile(email: str) -> Optional[UserProfile]:
    """Fetch a user profile by email. Returns ``None`` if no row exists."""
    if not email:
        return None
    try:
        resp = get_table().get_item(Key={"PK": _user_pk(email), "SK": "PROFILE"})
    except (ClientError, BotoCoreError) as exc:
        logger.error("DynamoDB get_user_profile failed for %s: %s", email, exc)
        return None

    item = resp.get("Item")
    if not item:
        return None

    data = item_to_dict(item)
    return UserProfile(
        email=data.get("email", email),
        tenant_id=data.get("tenant_id", "default"),
        tier=data.get("subscription_tier", data.get("tier", "basic")),
        is_admin=bool(data.get("is_admin", False)),
        enabled=bool(data.get("enabled", True)),
        display_name=data.get("display_name"),
    )


def upsert_user_profile(profile: UserProfile) -> UserProfile:
    """Create or replace a user profile. Used by seed scripts and admin tools."""
    item = {
        "PK": _user_pk(profile.email),
        "SK": "PROFILE",
        "email": profile.email.strip().lower(),
        "tenant_id": profile.tenant_id,
        "subscription_tier": profile.tier,
        "is_admin": profile.is_admin,
        "enabled": profile.enabled,
        "updated_at": now_iso(),
    }
    if profile.display_name:
        item["display_name"] = profile.display_name

    # Preserve created_at if the row already exists.
    existing = get_user_profile(profile.email)
    if existing is None:
        item["created_at"] = item["updated_at"]

    get_table().put_item(Item=item)
    return profile
