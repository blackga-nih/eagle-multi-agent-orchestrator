from typing import Dict, Optional
from datetime import datetime, timedelta
from app.models import SubscriptionTier, TierLimits, SubscriptionUsage
from app.dynamodb_store import DynamoDBStore
from decimal import Decimal

class SubscriptionService:
    def __init__(self, dynamodb_store: DynamoDBStore):
        self.store = dynamodb_store
        self.tier_limits = {
            SubscriptionTier.BASIC: TierLimits(
                daily_messages=50,
                monthly_messages=1000,
                max_session_duration=30,
                concurrent_sessions=1,
                mcp_server_access=False
            ),
            SubscriptionTier.ADVANCED: TierLimits(
                daily_messages=200,
                monthly_messages=5000,
                max_session_duration=120,
                concurrent_sessions=3,
                mcp_server_access=True
            ),
            SubscriptionTier.PREMIUM: TierLimits(
                daily_messages=1000,
                monthly_messages=25000,
                max_session_duration=480,
                concurrent_sessions=10,
                mcp_server_access=True
            )
        }

    def get_tier_limits(self, tier: SubscriptionTier) -> TierLimits:
        return self.tier_limits[tier]

    async def check_usage_limits(self, tenant_id: str, tier: SubscriptionTier) -> Dict[str, bool]:
        """Check if tenant has exceeded usage limits"""
        usage = await self.get_usage(tenant_id, tier)
        limits = self.get_tier_limits(tier)
        
        return {
            "daily_limit_exceeded": usage.daily_usage >= limits.daily_messages,
            "monthly_limit_exceeded": usage.monthly_usage >= limits.monthly_messages,
            "concurrent_sessions_exceeded": usage.active_sessions >= limits.concurrent_sessions,
            "can_use_mcp": limits.mcp_server_access
        }

    async def get_usage(self, tenant_id: str, tier: SubscriptionTier) -> SubscriptionUsage:
        """Get current usage for tenant"""
        try:
            response = self.store.usage_table.get_item(
                Key={
                    "tenant_id": f"{tenant_id}#{tier.value}",
                    "timestamp": "current"
                }
            )
            if "Item" in response:
                item = response["Item"]
                return SubscriptionUsage(
                    tenant_id=tenant_id,
                    subscription_tier=tier,
                    daily_usage=int(item.get("daily_usage", 0)),
                    monthly_usage=int(item.get("monthly_usage", 0)),
                    active_sessions=int(item.get("active_sessions", 0)),
                    last_reset_date=datetime.fromisoformat(item.get("last_reset_date", datetime.now().isoformat()))
                )
        except Exception:
            pass
        
        return SubscriptionUsage(
            tenant_id=tenant_id,
            subscription_tier=tier,
            last_reset_date=datetime.now()
        )

    async def increment_usage(self, tenant_id: str, tier: SubscriptionTier):
        """Increment usage counters"""
        now = datetime.now()
        usage = await self.get_usage(tenant_id, tier)
        
        # Reset daily counter if new day
        if usage.last_reset_date.date() < now.date():
            usage.daily_usage = 0
            usage.last_reset_date = now
        
        # Reset monthly counter if new month
        if usage.last_reset_date.month != now.month:
            usage.monthly_usage = 0
        
        usage.daily_usage += 1
        usage.monthly_usage += 1
        
        # Store updated usage
        self.store.usage_table.put_item(
            Item={
                "tenant_id": f"{tenant_id}#{tier.value}",
                "timestamp": "current",
                "daily_usage": usage.daily_usage,
                "monthly_usage": usage.monthly_usage,
                "active_sessions": usage.active_sessions,
                "last_reset_date": usage.last_reset_date.isoformat(),
                "tier": tier.value
            }
        )