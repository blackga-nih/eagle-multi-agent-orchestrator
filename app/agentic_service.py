"""
Agentic Framework Service using Bedrock Agents with multi-tenant support
"""
import boto3
import json
from typing import Dict, Any, List
from .models import TenantContext
from .runtime_context import RuntimeContextManager

class AgenticService:
    def __init__(self, agent_id: str, agent_alias_id: str = "TSTALIASID"):
        self.bedrock_agent_runtime = boto3.client('bedrock-agent-runtime')
        self.agent_id = agent_id
        self.agent_alias_id = agent_alias_id
    
    def invoke_agent_with_planning(self, message: str, tenant_context: TenantContext) -> Dict[str, Any]:
        """Invoke Bedrock Agent with full agentic capabilities"""
        
        session_id = f"{tenant_context.tenant_id}-{tenant_context.user_id}-{tenant_context.session_id}"
        
        # Build runtime context following AWS patterns
        session_attributes = RuntimeContextManager.build_session_attributes(
            tenant_context.tenant_id,
            tenant_context.user_id, 
            tenant_context.session_id,
            additional_context={
                "organization_type": "enterprise",
                "access_level": "standard"
            }
        )
        
        prompt_attributes = RuntimeContextManager.build_prompt_session_attributes(
            tenant_context.tenant_id,
            tenant_context.user_id,
            message_context={
                "request_type": "agentic_query",
                "enable_planning": "true",
                "enable_actions": "true"
            }
        )
        
        try:
            response = self.bedrock_agent_runtime.invoke_agent(
                agentId=self.agent_id,
                agentAliasId=self.agent_alias_id,
                sessionId=session_id,
                inputText=message,
                sessionAttributes=session_attributes,
                promptSessionAttributes=prompt_attributes,
                enableTrace=True
            )
            
            return self._process_agentic_response(response, session_id, tenant_context.tenant_id)
            
        except Exception as e:
            return {
                "response": f"Agent Error: {str(e)}",
                "session_id": session_id,
                "agentic_trace": {"error": True},
                "tenant_id": tenant_context.tenant_id
            }
    
    def _process_agentic_response(self, response, session_id: str, tenant_id: str) -> Dict[str, Any]:
        """Process agentic response with detailed trace analysis"""
        
        agent_response = ""
        agentic_trace = {
            "planning_steps": [],
            "action_calls": [],
            "knowledge_queries": [],
            "reasoning_chain": []
        }
        
        for event in response['completion']:
            if 'chunk' in event:
                chunk = event['chunk']
                if 'bytes' in chunk:
                    agent_response += chunk['bytes'].decode('utf-8')
                    
            elif 'trace' in event:
                trace = event['trace']
                
                # Planning trace
                if 'orchestrationTrace' in trace:
                    orchestration = trace['orchestrationTrace']
                    
                    if 'rationale' in orchestration:
                        agentic_trace["reasoning_chain"].append({
                            "step": "reasoning",
                            "content": orchestration['rationale'].get('text', '')
                        })
                    
                    if 'invocationInput' in orchestration:
                        agentic_trace["planning_steps"].append({
                            "step": "planning",
                            "action": orchestration['invocationInput'].get('actionGroupInvocationInput', {}).get('actionGroupName', 'unknown')
                        })
                
                # Action group traces
                if 'actionGroupInvocationInput' in trace:
                    action_input = trace['actionGroupInvocationInput']
                    agentic_trace["action_calls"].append({
                        "action_group": action_input.get('actionGroupName'),
                        "function": action_input.get('function'),
                        "parameters": action_input.get('parameters', {})
                    })
                
                # Knowledge base traces
                if 'knowledgeBaseLookupInput' in trace:
                    kb_input = trace['knowledgeBaseLookupInput']
                    agentic_trace["knowledge_queries"].append({
                        "knowledge_base_id": kb_input.get('knowledgeBaseId'),
                        "query": kb_input.get('text', '')
                    })
        
        return {
            "response": agent_response,
            "session_id": session_id,
            "tenant_id": tenant_id,
            "agentic_trace": agentic_trace,
            "capabilities_used": self._analyze_capabilities(agentic_trace)
        }
    
    def _analyze_capabilities(self, trace: Dict) -> Dict[str, bool]:
        """Analyze which agentic capabilities were used"""
        return {
            "planning": len(trace.get("planning_steps", [])) > 0,
            "reasoning": len(trace.get("reasoning_chain", [])) > 0,
            "tool_calling": len(trace.get("action_calls", [])) > 0,
            "knowledge_retrieval": len(trace.get("knowledge_queries", [])) > 0,
            "multi_step": len(trace.get("planning_steps", [])) > 1
        }