# AWS Bedrock Agent Core Runtime Context Implementation

Based on: [AWS Bedrock Agent Core Samples - Understanding Runtime Context](https://github.com/awslabs/amazon-bedrock-agentcore-samples/blob/main/01-tutorials/01-AgentCore-runtime/03-advanced-concepts/02-understanding-runtime-context/understanding_runtime_context.ipynb)

## 🔧 **Runtime Context Patterns**

### **1. Session Attributes (Persistent Context)**
```python
session_attributes = {
    "tenant_id": "acme-corp",           # Core tenant isolation
    "user_id": "john-doe",              # User context
    "session_context": "sess-001",      # Session tracking
    "organization": "acme-corp",         # For knowledge base filtering
    "department": "customer_support",   # Additional context
    "session_start_time": "2024-01-01T10:00:00Z"
}
```

**Purpose:** Persist across entire conversation session, used for:
- Tenant isolation and data filtering
- Knowledge base scoping per organization
- Session-level context and preferences

### **2. Prompt Session Attributes (Dynamic Context)**
```python
prompt_session_attributes = {
    "current_tenant": "acme-corp",      # Current request context
    "current_user": "john-doe",         # Current user
    "request_timestamp": "2024-01-01T10:05:00Z",
    "user_context": "User john-doe from organization acme-corp",
    "interaction_type": "chat_message"  # Message-specific context
}
```

**Purpose:** Change with each message, used for:
- Dynamic behavior per request
- Message-specific context
- Real-time user state

### **3. Bedrock Agent Invocation with Context**
```python
response = bedrock_agent_runtime.invoke_agent(
    agentId="AGENT123",
    agentAliasId="TSTALIASID",
    sessionId="acme-corp-john-doe-sess-001",  # Tenant-scoped session
    inputText="How can you help me?",
    sessionAttributes=session_attributes,      # Persistent context
    promptSessionAttributes=prompt_attributes, # Dynamic context
    enableTrace=True                          # For usage analytics
)
```

## 🏢 **Multi-Tenant Implementation**

### **Session ID Format**
```
{tenant_id}-{user_id}-{session_id}
Examples:
- acme-corp-john-doe-sess-001
- beta-inc-jane-smith-sess-002
- gamma-llc-bob-wilson-sess-003
```

### **Tenant Context Flow**
```
1. JWT Authentication → Extract tenant_id, user_id
2. Session Creation → Build tenant-scoped session_id
3. Runtime Context → Inject tenant context into session attributes
4. Bedrock Agent → Process with tenant-aware context
5. Trace Analysis → Extract tenant-specific usage metrics
6. Response → Return with tenant context maintained
```

### **Knowledge Base Filtering**
```python
# Session attributes enable tenant-specific knowledge base queries
session_attributes = {
    "organization": "acme-corp",     # Filters knowledge base results
    "department": "support",         # Further scoping
    "access_level": "standard"       # Permission-based filtering
}
```

## 📊 **Trace Analysis for Multi-Tenancy**

### **Orchestration Trace Extraction**
```python
def extract_tenant_metrics(trace_data):
    metrics = {
        "tenant_id": "acme-corp",
        "processing_steps": [],
        "resource_usage": {}
    }
    
    if 'orchestrationTrace' in trace_data:
        orchestration = trace_data['orchestrationTrace']
        
        # Model invocation tracking
        if 'modelInvocationInput' in orchestration:
            metrics["processing_steps"].append("model_invocation")
            metrics["resource_usage"]["model_id"] = orchestration['modelInvocationInput'].get('foundationModel')
        
        # Knowledge base usage tracking
        if 'knowledgeBaseLookupInput' in orchestration:
            metrics["processing_steps"].append("knowledge_base_lookup")
            metrics["resource_usage"]["kb_id"] = orchestration['knowledgeBaseLookupInput'].get('knowledgeBaseId')
        
        # Action group usage tracking
        if 'actionGroupInvocationInput' in orchestration:
            metrics["processing_steps"].append("action_group_invocation")
            metrics["resource_usage"]["action_group"] = orchestration['actionGroupInvocationInput'].get('actionGroupName')
    
    return metrics
```

### **Usage Pattern Analysis**
```python
# Track processing patterns per tenant
tenant_patterns = {
    "acme-corp": {
        "model_invocation -> knowledge_base_lookup": 15,
        "model_invocation": 8,
        "model_invocation -> action_group_invocation": 3
    },
    "beta-inc": {
        "model_invocation": 12,
        "model_invocation -> knowledge_base_lookup": 5
    }
}
```

## 🔍 **Key Differences from Basic Implementation**

### **Before (Basic):**
```python
# Simple session attributes
session_attributes = {
    "tenantId": tenant_id,
    "userId": user_id
}
```

### **After (AWS Agent Core Patterns):**
```python
# Rich runtime context following AWS patterns
session_attributes = RuntimeContextManager.build_session_attributes(
    tenant_id=tenant_id,
    user_id=user_id,
    session_id=session_id,
    additional_context={
        "organization": tenant_id,      # For KB filtering
        "department": "support",        # Scoping
        "session_start_time": timestamp # Tracking
    }
)

prompt_session_attributes = RuntimeContextManager.build_prompt_session_attributes(
    tenant_id=tenant_id,
    user_id=user_id,
    message_context={
        "interaction_type": "chat",     # Dynamic behavior
        "urgency": "normal"            # Message-specific
    }
)
```

## 🚀 **Benefits for Multi-Tenant Applications**

### **1. Enhanced Tenant Isolation**
- Session attributes ensure tenant context flows through all operations
- Knowledge base queries automatically scoped to tenant organization
- Action groups can access tenant-specific resources

### **2. Detailed Usage Analytics**
- Trace data provides granular usage metrics per tenant
- Processing patterns help optimize tenant-specific workflows
- Resource usage tracking enables accurate billing

### **3. Dynamic Behavior**
- Prompt session attributes allow per-message customization
- Tenant-specific AI behavior based on organization context
- Real-time adaptation to user needs

### **4. Production Readiness**
- Follows AWS best practices for Agent Core runtime
- Comprehensive trace analysis for monitoring
- Scalable context management across tenants

## 🧪 **Testing Runtime Context**

Run the demo to see runtime context patterns:
```bash
python examples/runtime_context_demo.py
```

This shows:
- Session vs prompt attribute differences
- Trace context extraction
- Multi-tenant usage summaries
- Proper Bedrock Agent invocation patterns

The implementation now follows AWS Bedrock Agent Core best practices for runtime context management in multi-tenant scenarios.