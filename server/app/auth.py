import jwt
import boto3
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Dict, Optional
import os
import base64
import json
from app.models import SubscriptionTier

DEV_MODE = os.getenv("DEV_MODE", "false").lower() == "true"

security = HTTPBearer(auto_error=not DEV_MODE)

class CognitoAuth:
    def __init__(self):
        self._cognito_client = None
        self.user_pool_id = os.getenv("COGNITO_USER_POOL_ID")
        self.client_id = os.getenv("COGNITO_CLIENT_ID")

    @property
    def cognito_client(self):
        if self._cognito_client is None:
            region = os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "us-east-1"))
            self._cognito_client = boto3.client('cognito-idp', region_name=region)
        return self._cognito_client
    
    def verify_token(self, token: str) -> Dict:
        """Verify Cognito JWT token and extract tenant context"""
        try:
            # Decode JWT token without verification (for development)
            # In production, you should verify the signature with Cognito's public keys
            parts = token.split('.')
            if len(parts) != 3:
                raise HTTPException(status_code=401, detail="Invalid token format")
            
            # Decode payload
            payload_encoded = parts[1]
            # Add padding if needed
            payload_encoded += '=' * (4 - len(payload_encoded) % 4)
            payload_bytes = base64.urlsafe_b64decode(payload_encoded)
            payload = json.loads(payload_bytes)
            
            # Debug: Print actual JWT payload
            print(f"🔍 Actual JWT Payload: {json.dumps(payload, indent=2)}")
            
            # Extract tenant_id and subscription_tier from custom attributes
            tenant_id = payload.get("custom:tenant_id")
            subscription_tier = payload.get("custom:subscription_tier", "basic")
            
            # Determine role from Cognito Groups
            user_groups = payload.get("cognito:groups", [])
            role = "admin" if any(group.endswith("-admins") for group in user_groups) else "user"
            
            if not tenant_id:
                raise HTTPException(status_code=403, detail="No tenant ID found in token")
            
            return {
                "user_id": payload.get("sub"),
                "tenant_id": tenant_id,
                "subscription_tier": SubscriptionTier(subscription_tier),
                "email": payload.get("email"),
                "username": payload.get("cognito:username", payload.get("email")),
                "role": role,
                "cognito:groups": user_groups
            }
            
        except json.JSONDecodeError:
            raise HTTPException(status_code=401, detail="Invalid token payload")
        except Exception as e:
            raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")

auth_service = CognitoAuth()

async def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> Dict:
    """Dependency to get current authenticated user with tenant context"""
    if DEV_MODE and (credentials is None or credentials.credentials == "dev-mode-token"):
        return {
            "user_id": os.getenv("DEV_USER_ID", "dev-user"),
            "tenant_id": os.getenv("DEV_TENANT_ID", "dev-tenant"),
            "subscription_tier": SubscriptionTier.PREMIUM,
            "email": "dev@nci.nih.gov",
            "username": "dev-user",
            "role": "admin",
            "cognito:groups": ["dev-tenant-admins"],
        }
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return auth_service.verify_token(credentials.credentials)