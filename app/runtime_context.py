"""
Runtime Context Management following AWS Bedrock Agent Core patterns
Based on: https://github.com/awslabs/amazon-bedrock-agentcore-samples
"""
from typing import Dict, Any, Optional
from datetime import datetime

class RuntimeContextManager:
    """Manages runtime context for multi-tenant Bedrock Agent invocations"""
    
    @staticmethod
    def build_session_attributes(tenant_id: str, user_id: str, session_id: str, 
                                additional_context: Optional[Dict] = None) -> Dict[str, str]:
        """
        Build session attributes following AWS Agent Core patterns
        These persist across the entire conversation session
        """
        base_attributes = {
            # Core tenant context
            "tenant_id": tenant_id,
            "user_id": user_id,
            "session_context": session_id,
            
            # Organization context for knowledge base filtering
            "organization": tenant_id,
            "department": "general",
            
            # Session metadata
            "session_start_time": datetime.utcnow().isoformat(),
            "client_type": "multi_tenant_chat"
        }
        
        if additional_context:
            base_attributes.update(additional_context)
            
        return base_attributes
    
    @staticmethod
    def build_prompt_session_attributes(tenant_id: str, user_id: str, 
                                      message_context: Optional[Dict] = None) -> Dict[str, str]:
        """
        Build prompt session attributes for dynamic behavior per request
        These can change with each message
        """
        prompt_attributes = {
            # Current request context
            "current_tenant": tenant_id,
            "current_user": user_id,
            "request_timestamp": datetime.utcnow().isoformat(),
            
            # Dynamic context for this specific message
            "user_context": f"User {user_id} from organization {tenant_id}",
            "interaction_type": "chat_message"
        }
        
        if message_context:
            prompt_attributes.update(message_context)
            
        return prompt_attributes
    
    @staticmethod
    def extract_tenant_context_from_trace(trace_data: Dict) -> Dict[str, Any]:
        """
        Extract tenant-specific context from Bedrock Agent trace data
        Following AWS patterns for trace analysis
        """
        context = {
            "tenant_metrics": {},
            "processing_steps": [],
            "resource_usage": {}
        }
        
        # Extract orchestration trace information
        if 'orchestrationTrace' in trace_data:
            orchestration = trace_data['orchestrationTrace']
            
            # Model invocation context
            if 'modelInvocationInput' in orchestration:
                model_input = orchestration['modelInvocationInput']
                context["processing_steps"].append("model_invocation")
                context["resource_usage"]["model_id"] = model_input.get('foundationModel')
                
            # Knowledge base context
            if 'knowledgeBaseLookupInput' in orchestration:
                kb_input = orchestration['knowledgeBaseLookupInput']
                context["processing_steps"].append("knowledge_base_lookup")
                context["resource_usage"]["knowledge_base_id"] = kb_input.get('knowledgeBaseId')
                
            # Action group context
            if 'actionGroupInvocationInput' in orchestration:
                ag_input = orchestration['actionGroupInvocationInput']
                context["processing_steps"].append("action_group_invocation")
                context["resource_usage"]["action_group"] = ag_input.get('actionGroupName')
        
        return context
    
    @staticmethod
    def build_tenant_usage_summary(trace_contexts: list, tenant_id: str) -> Dict[str, Any]:
        """
        Build comprehensive usage summary for a tenant from multiple trace contexts
        """
        summary = {
            "tenant_id": tenant_id,
            "total_interactions": len(trace_contexts),
            "resource_breakdown": {
                "model_invocations": 0,
                "knowledge_base_queries": 0,
                "action_group_calls": 0
            },
            "processing_patterns": {},
            "timestamp": datetime.utcnow().isoformat()
        }
        
        for trace_context in trace_contexts:
            # Count resource usage
            for step in trace_context.get("processing_steps", []):
                if step == "model_invocation":
                    summary["resource_breakdown"]["model_invocations"] += 1
                elif step == "knowledge_base_lookup":
                    summary["resource_breakdown"]["knowledge_base_queries"] += 1
                elif step == "action_group_invocation":
                    summary["resource_breakdown"]["action_group_calls"] += 1
            
            # Track processing patterns
            pattern = " -> ".join(trace_context.get("processing_steps", []))
            if pattern:
                summary["processing_patterns"][pattern] = summary["processing_patterns"].get(pattern, 0) + 1
        
        return summary