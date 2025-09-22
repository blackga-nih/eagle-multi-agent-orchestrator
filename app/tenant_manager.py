import uuid
from datetime import datetime
from typing import Dict, Optional
from .models import TenantSession, UsageMetric

class TenantManager:
    def __init__(self):
        # In-memory storage for demo (use DynamoDB in production)
        self.tenant_sessions: Dict[str, TenantSession] = {}
        self.usage_metrics: Dict[str, list] = {}
    
    def create_session(self, tenant_id: str, user_id: str) -> str:
        """Create a new session for a tenant user"""
        session_id = str(uuid.uuid4())
        session_key = f"{tenant_id}-{user_id}-{session_id}"
        
        session = TenantSession(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            created_at=datetime.utcnow(),
            last_activity=datetime.utcnow()
        )
        
        self.tenant_sessions[session_key] = session
        return session_id
    
    def get_session(self, tenant_id: str, user_id: str, session_id: str) -> Optional[TenantSession]:
        """Retrieve a tenant session"""
        session_key = f"{tenant_id}-{user_id}-{session_id}"
        return self.tenant_sessions.get(session_key)
    
    def update_session_activity(self, tenant_id: str, user_id: str, session_id: str):
        """Update session last activity and message count"""
        session_key = f"{tenant_id}-{user_id}-{session_id}"
        if session_key in self.tenant_sessions:
            self.tenant_sessions[session_key].last_activity = datetime.utcnow()
            self.tenant_sessions[session_key].message_count += 1
    
    def record_usage_metric(self, metric: UsageMetric):
        """Record usage metric for a tenant"""
        if metric.tenant_id not in self.usage_metrics:
            self.usage_metrics[metric.tenant_id] = []
        
        self.usage_metrics[metric.tenant_id].append(metric)
    
    def get_tenant_usage(self, tenant_id: str) -> Dict:
        """Get usage summary for a tenant"""
        metrics = self.usage_metrics.get(tenant_id, [])
        
        return {
            "tenant_id": tenant_id,
            "total_messages": len(metrics),
            "sessions": len([s for s in self.tenant_sessions.values() if s.tenant_id == tenant_id]),
            "metrics": [m.dict() for m in metrics[-10:]]  # Last 10 metrics
        }
    
    def get_all_tenant_sessions(self, tenant_id: str) -> list:
        """Get all sessions for a tenant"""
        return [s.dict() for s in self.tenant_sessions.values() if s.tenant_id == tenant_id]