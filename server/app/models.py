from pydantic import BaseModel
from typing import Dict, Any, Optional, List
from datetime import datetime
from enum import Enum
from decimal import Decimal

class SubscriptionTier(str, Enum):
    BASIC = "basic"
    ADVANCED = "advanced"
    PREMIUM = "premium"

class TierLimits(BaseModel):
    daily_messages: int
    monthly_messages: int
    max_session_duration: int  # minutes
    concurrent_sessions: int
    mcp_server_access: bool

class TenantContext(BaseModel):
    tenant_id: str
    user_id: str
    session_id: str
    subscription_tier: SubscriptionTier = SubscriptionTier.BASIC

class ChatMessage(BaseModel):
    message: str
    session_id: Optional[str] = None
    tenant_context: Optional[TenantContext] = None

class ChatResponse(BaseModel):
    response: str
    session_id: str
    tenant_id: str
    usage_metrics: Dict[str, Any]

class UsageMetric(BaseModel):
    tenant_id: str
    timestamp: datetime
    metric_type: str
    value: Decimal
    session_id: str
    agent_id: Optional[str] = None

class TenantSession(BaseModel):
    tenant_id: str
    user_id: str
    session_id: str
    subscription_tier: SubscriptionTier
    created_at: datetime
    last_activity: datetime
    message_count: int = 0
    tier_usage_count: int = 0

class SubscriptionUsage(BaseModel):
    tenant_id: str
    subscription_tier: SubscriptionTier
    daily_usage: int = 0
    monthly_usage: int = 0
    active_sessions: int = 0
    last_reset_date: datetime


class UploadResponse(BaseModel):
    key: str
    filename: str
    size_bytes: int
    content_type: str


class KBReviewRecord(BaseModel):
    review_id: str
    filename: str
    s3_key: str
    status: str  # "pending" | "approved" | "rejected"
    analysis_summary: str
    proposed_diff: List[Dict[str, Any]]
    created_at: str
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None