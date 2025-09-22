from pydantic import BaseModel
from typing import Dict, Any, Optional, List
from datetime import datetime
from enum import Enum

class TenantContext(BaseModel):
    tenant_id: str
    user_id: str
    session_id: str

class ChatMessage(BaseModel):
    message: str
    tenant_context: TenantContext

class ChatResponse(BaseModel):
    response: str
    session_id: str
    tenant_id: str
    usage_metrics: Dict[str, Any]

class UsageMetric(BaseModel):
    tenant_id: str
    timestamp: datetime
    metric_type: str
    value: float
    session_id: str
    agent_id: Optional[str] = None

class TenantSession(BaseModel):
    tenant_id: str
    user_id: str
    session_id: str
    created_at: datetime
    last_activity: datetime
    message_count: int = 0