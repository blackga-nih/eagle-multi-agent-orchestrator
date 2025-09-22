import jwt
import boto3
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Dict, Optional
import os

security = HTTPBearer()

class CognitoAuth:
    def __init__(self):
        self.cognito_client = boto3.client('cognito-idp')
        self.user_pool_id = os.getenv("COGNITO_USER_POOL_ID")
        self.client_id = os.getenv("COGNITO_CLIENT_ID")
        self.jwt_secret = os.getenv("JWT_SECRET", "fallback-secret")
    
    def verify_token(self, token: str) -> Dict:
        """Verify JWT token and extract tenant context"""
        try:
            # Decode JWT token
            payload = jwt.decode(token, self.jwt_secret, algorithms=["HS256"])
            
            # Get user details from Cognito
            user_response = self.cognito_client.admin_get_user(
                UserPoolId=self.user_pool_id,
                Username=payload.get("sub")
            )
            
            # Extract tenant_id from custom attributes
            tenant_id = None
            for attr in user_response.get("UserAttributes", []):
                if attr["Name"] == "custom:tenant_id":
                    tenant_id = attr["Value"]
                    break
            
            if not tenant_id:
                raise HTTPException(status_code=403, detail="No tenant ID found")
            
            return {
                "user_id": payload.get("sub"),
                "tenant_id": tenant_id,
                "email": payload.get("email"),
                "username": user_response.get("Username")
            }
            
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid token")
        except Exception as e:
            raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")

auth_service = CognitoAuth()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict:
    """Dependency to get current authenticated user with tenant context"""
    return auth_service.verify_token(credentials.credentials)