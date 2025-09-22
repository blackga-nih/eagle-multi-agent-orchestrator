from fastapi import FastAPI, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from datetime import datetime
import os
from .models import ChatMessage, ChatResponse, TenantContext, UsageMetric
from .bedrock_service import BedrockAgentService
from .agentic_service import AgenticService
from .dynamodb_store import DynamoDBStore
from .auth import get_current_user
from .runtime_context import RuntimeContextManager

app = FastAPI(title="Multi-Tenant Bedrock Chat", version="1.0.0")

# Initialize services
store = DynamoDBStore()

# Bedrock Agent configuration
AGENT_ID = os.getenv("BEDROCK_AGENT_ID", "your-agent-id")
AGENT_ALIAS_ID = os.getenv("BEDROCK_AGENT_ALIAS_ID", "TSTALIASID")

# Initialize both basic and agentic services
bedrock_service = BedrockAgentService(AGENT_ID, AGENT_ALIAS_ID)
agentic_service = AgenticService(AGENT_ID, AGENT_ALIAS_ID)

@app.post("/api/chat", response_model=ChatResponse)
async def chat(message: ChatMessage, current_user: dict = Depends(get_current_user)):
    """Send message to Bedrock Agent with tenant context and JWT auth"""
    
    # Verify tenant context matches authenticated user
    if message.tenant_context.tenant_id != current_user["tenant_id"]:
        raise HTTPException(status_code=403, detail="Tenant mismatch")
    
    if message.tenant_context.user_id != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="User mismatch")
    
    # Validate tenant session
    session = store.get_session(
        message.tenant_context.tenant_id,
        message.tenant_context.user_id,
        message.tenant_context.session_id
    )
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Use agentic service if agent is configured, otherwise fallback
    if AGENT_ID and AGENT_ID != "your-agent-id":
        result = agentic_service.invoke_agent_with_planning(message.message, message.tenant_context)
    else:
        result = bedrock_service.invoke_agent(message.message, message.tenant_context)
    
    # Update session activity
    store.update_session_activity(
        message.tenant_context.tenant_id,
        message.tenant_context.user_id,
        message.tenant_context.session_id
    )
    
    # Record enhanced usage metrics with trace data
    usage_metric = UsageMetric(
        tenant_id=message.tenant_context.tenant_id,
        timestamp=datetime.utcnow(),
        metric_type="agent_invocation",
        value=1.0,
        session_id=message.tenant_context.session_id,
        agent_id=AGENT_ID
    )
    store.record_usage_metric(usage_metric)
    
    # Store enhanced trace data for tenant analytics
    if "trace_summary" in result:
        trace_metric = UsageMetric(
            tenant_id=message.tenant_context.tenant_id,
            timestamp=datetime.utcnow(),
            metric_type="trace_analysis",
            value=result["trace_summary"].get("total_traces", 0),
            session_id=message.tenant_context.session_id,
            agent_id=AGENT_ID
        )
        store.record_usage_metric(trace_metric)
    
    return ChatResponse(
        response=result["response"],
        session_id=result["session_id"],
        tenant_id=result["tenant_id"],
        usage_metrics=result["usage_metrics"]
    )

@app.post("/api/sessions")
async def create_session(current_user: dict = Depends(get_current_user)):
    """Create a new chat session for authenticated tenant user"""
    session_id = store.create_session(current_user["tenant_id"], current_user["user_id"])
    
    return {
        "tenant_id": current_user["tenant_id"],
        "user_id": current_user["user_id"],
        "session_id": session_id,
        "created_at": datetime.utcnow().isoformat()
    }

@app.get("/api/tenants/{tenant_id}/usage")
async def get_tenant_usage(tenant_id: str, current_user: dict = Depends(get_current_user)):
    """Get usage metrics for authenticated tenant"""
    if tenant_id != current_user["tenant_id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return store.get_tenant_usage(tenant_id)

@app.get("/api/tenants/{tenant_id}/sessions")
async def get_tenant_sessions(tenant_id: str, current_user: dict = Depends(get_current_user)):
    """Get all sessions for authenticated tenant"""
    if tenant_id != current_user["tenant_id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return {
        "tenant_id": tenant_id,
        "sessions": store.get_tenant_sessions(tenant_id)
    }

@app.get("/api/tenants/{tenant_id}/analytics")
async def get_tenant_analytics(tenant_id: str, current_user: dict = Depends(get_current_user)):
    """Get enhanced analytics with trace data for authenticated tenant"""
    if tenant_id != current_user["tenant_id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get usage data and build analytics
    usage_data = store.get_tenant_usage(tenant_id)
    
    # Enhanced analytics following Agent Core patterns
    analytics = {
        "tenant_id": tenant_id,
        "total_interactions": usage_data.get("total_messages", 0),
        "active_sessions": usage_data.get("sessions", 0),
        "processing_patterns": {
            "agent_invocations": len([m for m in usage_data.get("metrics", []) if m.get("metric_type") == "agent_invocation"]),
            "trace_analyses": len([m for m in usage_data.get("metrics", []) if m.get("metric_type") == "trace_analysis"])
        },
        "resource_breakdown": {
            "model_invocations": usage_data.get("total_messages", 0),
            "knowledge_base_queries": 0,  # Would be extracted from traces
            "action_group_calls": 0       # Would be extracted from traces
        },
        "runtime_context_usage": {
            "session_attributes_used": True,
            "prompt_attributes_used": True,
            "trace_analysis_enabled": True
        }
    }
    
    return analytics

@app.get("/", response_class=HTMLResponse)
async def get_chat_interface():
    """Serve the chat interface"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Multi-Tenant Bedrock Chat</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            .container { max-width: 800px; margin: 0 auto; }
            .chat-box { border: 1px solid #ccc; height: 400px; overflow-y: scroll; padding: 10px; margin: 10px 0; }
            .message { margin: 5px 0; padding: 5px; }
            .user { background-color: #e3f2fd; text-align: right; }
            .agent { background-color: #f3e5f5; }
            .input-group { display: flex; gap: 10px; margin: 10px 0; }
            input, button { padding: 8px; }
            .tenant-info { background-color: #fff3e0; padding: 10px; margin: 10px 0; border-radius: 4px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Multi-Tenant Bedrock Chat</h1>
            
            <div class="tenant-info">
                <h3>Tenant Context</h3>
                <div class="input-group">
                    <input type="text" id="jwtToken" placeholder="JWT Token" style="flex: 1;">
                    <button onclick="setAuth()">Set Auth</button>
                    <button onclick="createSession()">Create Session</button>
                </div>
                <div class="input-group">
                    <button onclick="getTraceAnalytics()">View Trace Analytics</button>
                    <button onclick="getRuntimeContext()">View Runtime Context</button>
                    <button onclick="getAgenticCapabilities()">View Agentic Capabilities</button>
                </div>
                <div id="sessionInfo"></div>
            </div>
            
            <div id="chatBox" class="chat-box"></div>
            
            <div class="input-group">
                <input type="text" id="messageInput" placeholder="Type your message..." style="flex: 1;">
                <button onclick="sendMessage()">Send</button>
            </div>
            
            <div class="input-group">
                <button onclick="getUsage()">View Usage</button>
                <button onclick="getSessions()">View Sessions</button>
            </div>
            
            <div id="usageInfo"></div>
        </div>

        <script>
            let currentSession = null;
            let authToken = null;

            function setAuth() {
                authToken = document.getElementById('jwtToken').value;
                if (authToken) {
                    document.getElementById('sessionInfo').innerHTML = '<strong>Auth:</strong> Token set';
                }
            }

            async function createSession() {
                if (!authToken) {
                    alert('Please set JWT token first');
                    return;
                }
                
                const response = await fetch('/api/sessions', {
                    method: 'POST',
                    headers: { 
                        'Authorization': `Bearer ${authToken}`,
                        'Content-Type': 'application/json'
                    }
                });
                
                if (response.ok) {
                    currentSession = await response.json();
                    document.getElementById('sessionInfo').innerHTML = 
                        `<strong>Session:</strong> ${currentSession.session_id} (Tenant: ${currentSession.tenant_id})`;
                } else {
                    alert('Failed to create session. Check your JWT token.');
                }
            }

            async function sendMessage() {
                if (!currentSession) {
                    alert('Please create a session first');
                    return;
                }
                
                const message = document.getElementById('messageInput').value;
                if (!message) return;
                
                // Add user message to chat
                addMessageToChat('user', message);
                document.getElementById('messageInput').value = '';
                
                const response = await fetch('/api/chat', {
                    method: 'POST',
                    headers: { 
                        'Authorization': `Bearer ${authToken}`,
                        'Content-Type': 'application/json' 
                    },
                    body: JSON.stringify({
                        message: message,
                        tenant_context: {
                            tenant_id: currentSession.tenant_id,
                            user_id: currentSession.user_id,
                            session_id: currentSession.session_id
                        }
                    })
                });
                
                const result = await response.json();
                addMessageToChat('agent', result.response);
            }

            function addMessageToChat(sender, message) {
                const chatBox = document.getElementById('chatBox');
                const messageDiv = document.createElement('div');
                messageDiv.className = `message ${sender}`;
                messageDiv.innerHTML = `<strong>${sender}:</strong> ${message}`;
                chatBox.appendChild(messageDiv);
                chatBox.scrollTop = chatBox.scrollHeight;
            }

            async function getUsage() {
                if (!currentSession) return;
                
                const response = await fetch(`/api/tenants/${currentSession.tenant_id}/usage`, {
                    headers: { 'Authorization': `Bearer ${authToken}` }
                });
                const usage = await response.json();
                
                document.getElementById('usageInfo').innerHTML = 
                    `<h3>Usage for ${usage.tenant_id}</h3>
                     <p>Total Messages: ${usage.total_messages}</p>
                     <p>Active Sessions: ${usage.sessions}</p>
                     <pre>${JSON.stringify(usage.metrics, null, 2)}</pre>`;
            }

            async function getSessions() {
                if (!currentSession) return;
                
                const response = await fetch(`/api/tenants/${currentSession.tenant_id}/sessions`, {
                    headers: { 'Authorization': `Bearer ${authToken}` }
                });
                const sessions = await response.json();
                
                document.getElementById('usageInfo').innerHTML = 
                    `<h3>Sessions for ${sessions.tenant_id}</h3>
                     <pre>${JSON.stringify(sessions.sessions, null, 2)}</pre>`;
            }
            
            async function getTraceAnalytics() {
                if (!currentSession) return;
                
                const response = await fetch(`/api/tenants/${currentSession.tenant_id}/analytics`, {
                    headers: { 'Authorization': `Bearer ${authToken}` }
                });
                
                if (response.ok) {
                    const analytics = await response.json();
                    document.getElementById('usageInfo').innerHTML = 
                        `<h3>Trace Analytics for ${analytics.tenant_id}</h3>
                         <p>Processing Patterns: ${JSON.stringify(analytics.processing_patterns, null, 2)}</p>
                         <p>Resource Usage: ${JSON.stringify(analytics.resource_breakdown, null, 2)}</p>`;
                }
            }
            
            async function getRuntimeContext() {
                if (!currentSession) return;
                
                document.getElementById('usageInfo').innerHTML = 
                    `<h3>Runtime Context</h3>
                     <p><strong>Session ID:</strong> ${currentSession.tenant_id}-${currentSession.user_id}-${currentSession.session_id}</p>
                     <p><strong>Tenant Context:</strong> Organization ${currentSession.tenant_id}</p>
                     <p><strong>Session Attributes:</strong> Persistent across conversation</p>
                     <p><strong>Prompt Attributes:</strong> Dynamic per message</p>`;
            }
            
            async function getAgenticCapabilities() {
                document.getElementById('usageInfo').innerHTML = 
                    `<h3>Agentic Framework Capabilities</h3>
                     <p><strong>🧠 Planning:</strong> Multi-step reasoning and task decomposition</p>
                     <p><strong>🔧 Tool Calling:</strong> Action groups for tenant-specific operations</p>
                     <p><strong>📚 Knowledge Retrieval:</strong> RAG with tenant-scoped knowledge bases</p>
                     <p><strong>🔄 Orchestration:</strong> Complex workflow management</p>
                     <p><strong>📊 Trace Analysis:</strong> Detailed agentic behavior tracking</p>`;
            }

            // Allow Enter key to send message
            document.getElementById('messageInput').addEventListener('keypress', function(e) {
                if (e.key === 'Enter') {
                    sendMessage();
                }
            });
        </script>
    </body>
    </html>
    """

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)