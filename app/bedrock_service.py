import boto3
import json
import uuid
from datetime import datetime
from typing import Dict, Any, Optional
from .models import TenantContext, UsageMetric

class BedrockAgentService:
    def __init__(self, agent_id: str, agent_alias_id: str = "TSTALIASID"):
        self.bedrock_agent_runtime = boto3.client('bedrock-agent-runtime')
        self.bedrock_runtime = boto3.client('bedrock-runtime')
        self.agent_id = agent_id
        self.agent_alias_id = agent_alias_id
        # Use the latest Claude 3.5 Sonnet model
        self.model_id = "anthropic.claude-3-5-sonnet-20241022-v2:0"  # Latest available
        
    def invoke_agent(self, message: str, tenant_context: TenantContext) -> Dict[str, Any]:
        """Invoke Bedrock Agent with proper runtime context following AWS patterns"""
        
        # Create tenant-aware session ID following AWS best practices
        session_id = f"{tenant_context.tenant_id}-{tenant_context.user_id}-{tenant_context.session_id}"
        
        # Runtime context with tenant information (following AWS Agent Core patterns)
        session_attributes = {
            "tenant_id": tenant_context.tenant_id,
            "user_id": tenant_context.user_id,
            "session_context": tenant_context.session_id,
            "organization": tenant_context.tenant_id  # For knowledge base filtering
        }
        
        # Prompt attributes for dynamic behavior per tenant
        prompt_session_attributes = {
            "current_tenant": tenant_context.tenant_id,
            "user_context": f"User {tenant_context.user_id} from tenant {tenant_context.tenant_id}"
        }
        
        try:
            if self.agent_id and self.agent_id != "your-agent-id":
                # Use Bedrock Agent Core Runtime with proper context
                response = self.bedrock_agent_runtime.invoke_agent(
                    agentId=self.agent_id,
                    agentAliasId=self.agent_alias_id,
                    sessionId=session_id,
                    inputText=message,
                    sessionAttributes=session_attributes,
                    promptSessionAttributes=prompt_session_attributes,
                    enableTrace=True  # Enable for usage tracking
                )
                return self._process_agent_response(response, session_id, tenant_context.tenant_id)
            else:
                return self._invoke_claude_direct(message, session_id, tenant_context.tenant_id)
            
        except Exception as e:
            return {
                "response": f"Error: {str(e)}",
                "session_id": session_id,
                "usage_metrics": {"error": True},
                "tenant_id": tenant_context.tenant_id
            }
    
    def _process_agent_response(self, response, session_id: str, tenant_id: str) -> Dict[str, Any]:
        """Process Bedrock Agent response with enhanced trace analysis"""
        agent_response = ""
        usage_data = {
            "tenant_id": tenant_id,
            "session_id": session_id,
            "invocation_time": datetime.utcnow().isoformat()
        }
        trace_data = []
        
        for event in response['completion']:
            if 'chunk' in event:
                chunk = event['chunk']
                if 'bytes' in chunk:
                    agent_response += chunk['bytes'].decode('utf-8')
            elif 'trace' in event:
                trace = event['trace']
                trace_data.append(trace)
                
                # Extract detailed usage metrics from trace
                if 'orchestrationTrace' in trace:
                    orchestration = trace['orchestrationTrace']
                    usage_data.update(self._extract_orchestration_metrics(orchestration))
                
                # Extract knowledge base usage
                if 'knowledgeBaseLookupOutput' in trace:
                    kb_output = trace['knowledgeBaseLookupOutput']
                    usage_data['knowledge_base_queries'] = usage_data.get('knowledge_base_queries', 0) + 1
                    usage_data['retrieved_references'] = len(kb_output.get('retrievedReferences', []))
                
                # Extract action group usage
                if 'actionGroupInvocationOutput' in trace:
                    usage_data['action_group_calls'] = usage_data.get('action_group_calls', 0) + 1
        
        return {
            "response": agent_response,
            "session_id": session_id,
            "usage_metrics": usage_data,
            "tenant_id": tenant_id,
            "trace_summary": self._summarize_traces(trace_data)
        }
    
    def _invoke_claude_direct(self, message: str, session_id: str, tenant_id: str) -> Dict[str, Any]:
        """Direct Claude 3.5 Sonnet invocation with tenant context"""
        try:
            # Enhanced prompt with tenant context following Agent Core patterns
            system_prompt = f"""You are an AI assistant for tenant {tenant_id}. 
Provide responses that are contextually appropriate for this organization.
Session ID: {session_id}"""
            
            body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1000,
                "system": system_prompt,
                "messages": [
                    {
                        "role": "user",
                        "content": message
                    }
                ]
            }
            
            response = self.bedrock_runtime.invoke_model(
                modelId=self.model_id,
                body=json.dumps(body)
            )
            
            response_body = json.loads(response['body'].read())
            
            return {
                "response": response_body['content'][0]['text'],
                "session_id": session_id,
                "usage_metrics": {
                    "tenant_id": tenant_id,
                    "model_id": self.model_id,
                    "input_tokens": response_body.get('usage', {}).get('input_tokens', 0),
                    "output_tokens": response_body.get('usage', {}).get('output_tokens', 0),
                    "invocation_time": datetime.utcnow().isoformat(),
                    "direct_invocation": True
                },
                "tenant_id": tenant_id,
                "trace_summary": {"direct_model_call": True}
            }
            
        except Exception as e:
            return {
                "response": f"Claude Error: {str(e)}",
                "session_id": session_id,
                "usage_metrics": {"error": True, "tenant_id": tenant_id},
                "tenant_id": tenant_id
            }
    
    def _extract_orchestration_metrics(self, orchestration_trace: Dict) -> Dict[str, Any]:
        """Extract detailed metrics from orchestration trace following AWS patterns"""
        metrics = {}
        
        # Model invocation metrics
        if 'modelInvocationInput' in orchestration_trace:
            model_input = orchestration_trace['modelInvocationInput']
            metrics['model_invocations'] = metrics.get('model_invocations', 0) + 1
            metrics['model_id'] = model_input.get('foundationModel', 'unknown')
            
        if 'modelInvocationOutput' in orchestration_trace:
            model_output = orchestration_trace['modelInvocationOutput']
            if 'metadata' in model_output:
                metadata = model_output['metadata']
                metrics['input_tokens'] = metadata.get('usage', {}).get('inputTokens', 0)
                metrics['output_tokens'] = metadata.get('usage', {}).get('outputTokens', 0)
        
        # Reasoning and planning metrics
        if 'rationale' in orchestration_trace:
            metrics['reasoning_steps'] = 1
            
        if 'invocationInput' in orchestration_trace:
            metrics['planning_steps'] = 1
            
        return metrics
    
    def _summarize_traces(self, trace_data: list) -> Dict[str, Any]:
        """Summarize trace data for tenant analytics"""
        summary = {
            "total_traces": len(trace_data),
            "trace_types": {},
            "processing_steps": 0
        }
        
        for trace in trace_data:
            for trace_type in trace.keys():
                summary['trace_types'][trace_type] = summary['trace_types'].get(trace_type, 0) + 1
                summary['processing_steps'] += 1
                
        return summary