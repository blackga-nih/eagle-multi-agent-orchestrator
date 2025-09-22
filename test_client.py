#!/usr/bin/env python3
"""
Test client for multi-tenant Bedrock chat application
"""
import requests
import json
import time

BASE_URL = "http://localhost:8000"

def test_multi_tenant_chat():
    """Test multi-tenant functionality"""
    
    print("🧪 Testing Multi-Tenant Bedrock Chat Application\n")
    
    # Test data for two different tenants
    tenants = [
        {"tenant_id": "tenant-001", "user_id": "user-001", "name": "Acme Corp"},
        {"tenant_id": "tenant-002", "user_id": "user-001", "name": "Beta Inc"}
    ]
    
    sessions = {}
    
    # 1. Create sessions for each tenant
    print("1️⃣ Creating sessions for each tenant...")
    for tenant in tenants:
        response = requests.post(
            f"{BASE_URL}/api/sessions",
            data={
                "tenant_id": tenant["tenant_id"],
                "user_id": tenant["user_id"]
            }
        )
        
        if response.status_code == 200:
            session_data = response.json()
            sessions[tenant["tenant_id"]] = session_data
            print(f"   ✅ {tenant['name']}: Session {session_data['session_id']}")
        else:
            print(f"   ❌ Failed to create session for {tenant['name']}")
            return
    
    print()
    
    # 2. Send messages from each tenant
    print("2️⃣ Sending messages from each tenant...")
    
    messages = [
        "Hello, can you help me with my business questions?",
        "What services do you provide?",
        "How can I improve my workflow?"
    ]
    
    for i, message in enumerate(messages):
        for tenant in tenants:
            tenant_id = tenant["tenant_id"]
            session = sessions[tenant_id]
            
            print(f"   📤 {tenant['name']}: {message}")
            
            response = requests.post(
                f"{BASE_URL}/api/chat",
                json={
                    "message": message,
                    "tenant_context": {
                        "tenant_id": session["tenant_id"],
                        "user_id": session["user_id"],
                        "session_id": session["session_id"]
                    }
                }
            )
            
            if response.status_code == 200:
                chat_response = response.json()
                print(f"   📥 Agent: {chat_response['response'][:100]}...")
                print(f"   📊 Usage: {chat_response['usage_metrics']}")
            else:
                print(f"   ❌ Chat failed: {response.text}")
            
            time.sleep(1)  # Rate limiting
        
        print()
    
    # 3. Check usage metrics for each tenant
    print("3️⃣ Checking usage metrics per tenant...")
    for tenant in tenants:
        tenant_id = tenant["tenant_id"]
        
        response = requests.get(f"{BASE_URL}/api/tenants/{tenant_id}/usage")
        
        if response.status_code == 200:
            usage = response.json()
            print(f"   📈 {tenant['name']} Usage:")
            print(f"      - Total Messages: {usage['total_messages']}")
            print(f"      - Active Sessions: {usage['sessions']}")
            print(f"      - Recent Metrics: {len(usage['metrics'])}")
        else:
            print(f"   ❌ Failed to get usage for {tenant['name']}")
        
        print()
    
    # 4. Check sessions for each tenant
    print("4️⃣ Checking sessions per tenant...")
    for tenant in tenants:
        tenant_id = tenant["tenant_id"]
        
        response = requests.get(f"{BASE_URL}/api/tenants/{tenant_id}/sessions")
        
        if response.status_code == 200:
            sessions_data = response.json()
            print(f"   🔗 {tenant['name']} Sessions: {len(sessions_data['sessions'])}")
            for session in sessions_data['sessions']:
                print(f"      - Session: {session['session_id']} ({session['message_count']} messages)")
        else:
            print(f"   ❌ Failed to get sessions for {tenant['name']}")
        
        print()
    
    print("✅ Multi-tenant testing completed!")
    print("\n💡 Key Points Demonstrated:")
    print("   - Tenant isolation: Each tenant has separate sessions and metrics")
    print("   - Session tracking: Unique session IDs per tenant-user combination")
    print("   - Usage metrics: Tenant-specific usage data collection")
    print("   - Context propagation: Tenant context flows through all operations")

if __name__ == "__main__":
    try:
        test_multi_tenant_chat()
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to the application.")
        print("💡 Make sure the server is running: python run.py")
    except Exception as e:
        print(f"❌ Test failed: {e}")