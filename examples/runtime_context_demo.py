#!/usr/bin/env python3
"""
Demo showing AWS Bedrock Agent Core Runtime Context patterns
Based on: https://github.com/awslabs/amazon-bedrock-agentcore-samples
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.runtime_context import RuntimeContextManager
from app.models import TenantContext
import json

def demo_runtime_context():
    """Demonstrate runtime context patterns for multi-tenant scenarios"""
    
    print("🔧 AWS Bedrock Agent Core Runtime Context Demo")
    print("=" * 50)
    
    # Example tenant contexts
    tenants = [
        {"tenant_id": "acme-corp", "user_id": "john-doe", "session_id": "sess-001"},
        {"tenant_id": "beta-inc", "user_id": "jane-smith", "session_id": "sess-002"}
    ]
    
    for tenant in tenants:
        print(f"\n🏢 Tenant: {tenant['tenant_id']}")
        print("-" * 30)
        
        # 1. Build Session Attributes (persistent across conversation)
        session_attrs = RuntimeContextManager.build_session_attributes(
            tenant_id=tenant["tenant_id"],
            user_id=tenant["user_id"],
            session_id=tenant["session_id"],
            additional_context={
                "department": "customer_support",
                "priority_level": "standard"
            }
        )
        
        print("📋 Session Attributes (persistent):")
        print(json.dumps(session_attrs, indent=2))
        
        # 2. Build Prompt Session Attributes (dynamic per message)
        prompt_attrs = RuntimeContextManager.build_prompt_session_attributes(
            tenant_id=tenant["tenant_id"],
            user_id=tenant["user_id"],
            message_context={
                "message_type": "question",
                "urgency": "normal"
            }
        )
        
        print("\n🎯 Prompt Session Attributes (per message):")
        print(json.dumps(prompt_attrs, indent=2))
        
        # 3. Simulate trace context extraction
        mock_trace = {
            "orchestrationTrace": {
                "modelInvocationInput": {
                    "foundationModel": "anthropic.claude-3-5-sonnet-20241022-v2:0"
                },
                "knowledgeBaseLookupInput": {
                    "knowledgeBaseId": f"kb-{tenant['tenant_id']}"
                }
            }
        }
        
        trace_context = RuntimeContextManager.extract_tenant_context_from_trace(mock_trace)
        
        print("\n📊 Extracted Trace Context:")
        print(json.dumps(trace_context, indent=2))
    
    # 4. Build usage summary across tenants
    print(f"\n📈 Multi-Tenant Usage Summary")
    print("-" * 30)
    
    mock_trace_contexts = [
        {"processing_steps": ["model_invocation", "knowledge_base_lookup"], "tenant_id": "acme-corp"},
        {"processing_steps": ["model_invocation"], "tenant_id": "acme-corp"},
        {"processing_steps": ["model_invocation", "action_group_invocation"], "tenant_id": "beta-inc"}
    ]
    
    for tenant_id in ["acme-corp", "beta-inc"]:
        tenant_traces = [tc for tc in mock_trace_contexts if tc["tenant_id"] == tenant_id]
        summary = RuntimeContextManager.build_tenant_usage_summary(tenant_traces, tenant_id)
        
        print(f"\n🏢 {tenant_id} Usage Summary:")
        print(json.dumps(summary, indent=2))

def demo_bedrock_agent_invocation():
    """Show how runtime context is used in actual Bedrock Agent calls"""
    
    print(f"\n🤖 Bedrock Agent Invocation Pattern")
    print("=" * 40)
    
    tenant_context = TenantContext(
        tenant_id="demo-tenant",
        user_id="demo-user", 
        session_id="demo-session"
    )
    
    # Session attributes (persistent)
    session_attributes = RuntimeContextManager.build_session_attributes(
        tenant_context.tenant_id,
        tenant_context.user_id,
        tenant_context.session_id
    )
    
    # Prompt attributes (per message)
    prompt_attributes = RuntimeContextManager.build_prompt_session_attributes(
        tenant_context.tenant_id,
        tenant_context.user_id
    )
    
    # Simulated Bedrock Agent call structure
    agent_call = {
        "agentId": "AGENT123",
        "agentAliasId": "TSTALIASID",
        "sessionId": f"{tenant_context.tenant_id}-{tenant_context.user_id}-{tenant_context.session_id}",
        "inputText": "How can you help me with my business questions?",
        "sessionAttributes": session_attributes,
        "promptSessionAttributes": prompt_attributes,
        "enableTrace": True
    }
    
    print("📞 Bedrock Agent Runtime Call:")
    print(json.dumps(agent_call, indent=2))
    
    print(f"\n✅ Key Benefits:")
    print("   • Tenant context flows through entire conversation")
    print("   • Session attributes persist across messages")
    print("   • Prompt attributes allow dynamic behavior")
    print("   • Trace data enables detailed usage analytics")
    print("   • Complete tenant isolation and tracking")

if __name__ == "__main__":
    demo_runtime_context()
    demo_bedrock_agent_invocation()