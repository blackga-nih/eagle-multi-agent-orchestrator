"""
Commands API Router

Serves the slash command registry from eagle-plugin/command-registry.json.
Commands are tier-gated: each command declares a minimum subscription tier,
and only commands the user's tier can access are returned.
"""

from fastapi import APIRouter, Depends

from ..cognito_auth import UserContext
from .dependencies import get_user_from_header

router = APIRouter(prefix="/api/commands", tags=["commands"])

_TIER_RANK = {"basic": 0, "advanced": 1, "premium": 2}


@router.get("")
async def list_commands(
    user: UserContext = Depends(get_user_from_header),
):
    """Return all slash commands available for the user's subscription tier."""
    from eagle_skill_constants import COMMANDS

    user_rank = _TIER_RANK.get(user.tier, 0)
    return [
        cmd
        for cmd in COMMANDS
        if _TIER_RANK.get(cmd.get("tier", "basic"), 0) <= user_rank
    ]
