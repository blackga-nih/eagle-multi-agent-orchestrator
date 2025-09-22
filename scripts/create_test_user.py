#!/usr/bin/env python3
"""
Create test users in Cognito for multi-tenant testing
"""
import boto3
import os
import jwt
from datetime import datetime, timedelta

def create_test_users():
    """Create test users with tenant assignments"""
    
    cognito_client = boto3.client('cognito-idp')
    user_pool_id = os.getenv("COGNITO_USER_POOL_ID")
    client_id = os.getenv("COGNITO_CLIENT_ID")
    jwt_secret = os.getenv("JWT_SECRET", "your-secret-key")
    
    if not user_pool_id or not client_id:
        print("❌ COGNITO_USER_POOL_ID and COGNITO_CLIENT_ID must be set")
        return
    
    # Test users for different tenants
    test_users = [
        {
            "username": "tenant1-user1",
            "email": "tenant1-user1@example.com",
            "tenant_id": "tenant-001",
            "password": "TempPass123!"
        },
        {
            "username": "tenant2-user1", 
            "email": "tenant2-user1@example.com",
            "tenant_id": "tenant-002",
            "password": "TempPass123!"
        }
    ]
    
    print("🔧 Creating test users in Cognito...")
    
    for user in test_users:
        try:
            # Create user
            cognito_client.admin_create_user(
                UserPoolId=user_pool_id,
                Username=user["username"],
                UserAttributes=[
                    {"Name": "email", "Value": user["email"]},
                    {"Name": "email_verified", "Value": "true"},
                    {"Name": "custom:tenant_id", "Value": user["tenant_id"]}
                ],
                TemporaryPassword=user["password"],
                MessageAction="SUPPRESS"
            )
            
            # Set permanent password
            cognito_client.admin_set_user_password(
                UserPoolId=user_pool_id,
                Username=user["username"],
                Password=user["password"],
                Permanent=True
            )
            
            # Generate JWT token for testing
            payload = {
                "sub": user["username"],
                "email": user["email"],
                "tenant_id": user["tenant_id"],
                "exp": datetime.utcnow() + timedelta(hours=24)
            }
            
            token = jwt.encode(payload, jwt_secret, algorithm="HS256")
            
            print(f"✅ Created user: {user['username']} (Tenant: {user['tenant_id']})")
            print(f"   JWT Token: {token}")
            print()
            
        except cognito_client.exceptions.UsernameExistsException:
            print(f"⚠️  User {user['username']} already exists")
        except Exception as e:
            print(f"❌ Failed to create user {user['username']}: {e}")

if __name__ == "__main__":
    create_test_users()