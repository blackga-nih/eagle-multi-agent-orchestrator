"""
Cognito JWT Authentication
Validates AWS Cognito JWTs and extracts user/tenant context.
"""
import os
import json
import time
import logging
import httpx
from typing import Optional, Dict, Any, Tuple
from functools import lru_cache

logger = logging.getLogger("eagle.auth")

# ── Configuration ────────────────────────────────────────────────────
COGNITO_REGION = os.getenv("COGNITO_REGION", os.getenv("AWS_REGION", "us-east-1"))
COGNITO_USER_POOL_ID = os.getenv("COGNITO_USER_POOL_ID", "")
COGNITO_CLIENT_ID = os.getenv("COGNITO_CLIENT_ID", "")
COGNITO_ISSUER = f"https://cognito-idp.{COGNITO_REGION}.amazonaws.com/{COGNITO_USER_POOL_ID}"
COGNITO_JWKS_URL = f"{COGNITO_ISSUER}/.well-known/jwks.json"

# Dev mode bypass
DEV_MODE = os.getenv("DEV_MODE", "false").lower() == "true"
DEV_USER_ID = os.getenv("DEV_USER_ID", "dev-user")
DEV_TENANT_ID = os.getenv("DEV_TENANT_ID", "dev-tenant")

# ── JWKS Cache ───────────────────────────────────────────────────────
_jwks_cache: Dict[str, Any] = {}
_jwks_cache_time: float = 0
JWKS_CACHE_DURATION = 3600  # 1 hour


def _get_jwks() -> Dict[str, Any]:
    """Fetch and cache JWKS from Cognito."""
    global _jwks_cache, _jwks_cache_time
    
    now = time.time()
    if _jwks_cache and now - _jwks_cache_time < JWKS_CACHE_DURATION:
        return _jwks_cache
    
    try:
        response = httpx.get(COGNITO_JWKS_URL, timeout=10.0)
        response.raise_for_status()
        _jwks_cache = response.json()
        _jwks_cache_time = now
        logger.info("Refreshed JWKS cache")
        return _jwks_cache
    except Exception as e:
        logger.error("Failed to fetch JWKS: %s", e)
        if _jwks_cache:
            return _jwks_cache
        raise


def _get_signing_key(kid: str) -> Optional[Dict]:
    """Get the signing key for a specific key ID."""
    jwks = _get_jwks()
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            return key
    return None


# ── JWT Validation ───────────────────────────────────────────────────

def validate_token(token: str) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
    """
    Validate a Cognito JWT token.
    
    Returns:
        Tuple of (is_valid, claims, error_message)
    """
    # Dev mode bypass
    if DEV_MODE:
        logger.debug("Dev mode: bypassing token validation")
        return True, {
            "sub": DEV_USER_ID,
            "cognito:username": DEV_USER_ID,
            "custom:tenant_id": DEV_TENANT_ID,
            "email": f"{DEV_USER_ID}@example.com",
            "iss": "dev-mode",
            "exp": int(time.time()) + 3600,
        }, None
    
    if not COGNITO_USER_POOL_ID or not COGNITO_CLIENT_ID:
        return False, None, "Cognito not configured"
    
    try:
        import jwt
        from jwt import PyJWKClient
    except ImportError:
        logger.error("PyJWT not installed")
        return False, None, "JWT library not available"
    
    try:
        # Decode header to get key ID
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        
        if not kid:
            return False, None, "No key ID in token header"
        
        # Get signing key
        signing_key = _get_signing_key(kid)
        if not signing_key:
            return False, None, f"Unknown key ID: {kid}"
        
        # Build public key
        jwk_client = PyJWKClient(COGNITO_JWKS_URL)
        signing_key_obj = jwk_client.get_signing_key_from_jwt(token)
        
        # Decode and verify token
        claims = jwt.decode(
            token,
            signing_key_obj.key,
            algorithms=["RS256"],
            audience=COGNITO_CLIENT_ID,
            issuer=COGNITO_ISSUER,
            options={
                "verify_exp": True,
                "verify_aud": True,
                "verify_iss": True,
            }
        )
        
        return True, claims, None
        
    except jwt.ExpiredSignatureError:
        return False, None, "Token expired"
    except jwt.InvalidTokenError as e:
        return False, None, f"Invalid token: {str(e)}"
    except Exception as e:
        logger.error("Token validation error: %s", e)
        return False, None, f"Validation error: {str(e)}"


def validate_token_simple(token: str) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
    """
    Simple JWT validation without full Cognito verification.
    For use when Cognito is not configured but basic JWT structure is needed.
    """
    # Dev mode bypass
    if DEV_MODE:
        return True, {
            "sub": DEV_USER_ID,
            "cognito:username": DEV_USER_ID,
            "custom:tenant_id": DEV_TENANT_ID,
            "email": f"{DEV_USER_ID}@example.com",
        }, None
    
    try:
        import jwt
        
        # Decode without verification (for development/demo)
        claims = jwt.decode(token, options={"verify_signature": False})
        return True, claims, None
    except Exception as e:
        return False, None, f"Invalid token format: {str(e)}"


# ── User Context Extraction ──────────────────────────────────────────

class UserContext:
    """User context extracted from JWT claims."""
    
    def __init__(
        self,
        user_id: str,
        tenant_id: str = "default",
        email: Optional[str] = None,
        username: Optional[str] = None,
        roles: Optional[list] = None,
        tier: str = "free",
        claims: Optional[Dict] = None
    ):
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.email = email
        self.username = username or user_id
        self.roles = roles or []
        self.tier = tier
        self.claims = claims or {}
    
    @classmethod
    def from_claims(cls, claims: Dict[str, Any]) -> "UserContext":
        """Create UserContext from JWT claims."""
        return cls(
            user_id=claims.get("sub", claims.get("cognito:username", "anonymous")),
            tenant_id=claims.get("custom:tenant_id", claims.get("tenant_id", "default")),
            email=claims.get("email"),
            username=claims.get("cognito:username", claims.get("preferred_username")),
            roles=claims.get("cognito:groups", claims.get("roles", [])),
            tier=claims.get("custom:tier", claims.get("tier", "free")),
            claims=claims
        )
    
    @classmethod
    def anonymous(cls) -> "UserContext":
        """Create anonymous user context."""
        return cls(
            user_id="anonymous",
            tenant_id="default",
            tier="free"
        )
    
    @classmethod
    def dev_user(cls) -> "UserContext":
        """Create dev mode user context."""
        return cls(
            user_id=DEV_USER_ID,
            tenant_id=DEV_TENANT_ID,
            email=f"{DEV_USER_ID}@example.com",
            username=DEV_USER_ID,
            roles=["admin"],
            tier="premium"
        )
    
    def is_admin(self) -> bool:
        """Check if user has admin role."""
        return "admin" in self.roles or "Admin" in self.roles
    
    def is_premium(self) -> bool:
        """Check if user has premium tier."""
        return self.tier.lower() in ("premium", "enterprise", "pro")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "email": self.email,
            "username": self.username,
            "roles": self.roles,
            "tier": self.tier,
        }


def extract_user_context(
    token: Optional[str] = None,
    validate: bool = True
) -> Tuple[UserContext, Optional[str]]:
    """
    Extract user context from JWT token.
    
    Returns:
        Tuple of (UserContext, error_message)
    """
    # Dev mode
    if DEV_MODE:
        return UserContext.dev_user(), None
    
    # No token provided
    if not token:
        return UserContext.anonymous(), "No token provided"
    
    # Remove "Bearer " prefix if present
    if token.startswith("Bearer "):
        token = token[7:]
    
    # Validate token
    if validate and COGNITO_USER_POOL_ID and COGNITO_CLIENT_ID:
        is_valid, claims, error = validate_token(token)
    else:
        is_valid, claims, error = validate_token_simple(token)
    
    if not is_valid or not claims:
        return UserContext.anonymous(), error
    
    return UserContext.from_claims(claims), None


# ── FastAPI Middleware ───────────────────────────────────────────────

async def get_current_user(
    authorization: Optional[str] = None
) -> UserContext:
    """
    FastAPI dependency for extracting current user.
    
    Usage:
        @app.get("/api/protected")
        async def protected(user: UserContext = Depends(get_current_user)):
            ...
    """
    user, error = extract_user_context(authorization, validate=True)
    return user


def require_auth(user: UserContext) -> UserContext:
    """
    Require authenticated user (not anonymous).
    
    Usage:
        @app.get("/api/protected")
        async def protected(user: UserContext = Depends(require_auth)):
            ...
    """
    if user.user_id == "anonymous":
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def require_admin(user: UserContext) -> UserContext:
    """
    Require admin role.
    """
    if not user.is_admin():
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# ── Token Generation (for testing) ───────────────────────────────────

def generate_test_token(
    user_id: str = "test-user",
    tenant_id: str = "test-tenant",
    roles: Optional[list] = None,
    tier: str = "free",
    expiry_hours: int = 24
) -> str:
    """
    Generate a test JWT token (for development only).
    NOT for production use.
    """
    try:
        import jwt
        
        now = int(time.time())
        claims = {
            "sub": user_id,
            "cognito:username": user_id,
            "custom:tenant_id": tenant_id,
            "cognito:groups": roles or [],
            "custom:tier": tier,
            "email": f"{user_id}@example.com",
            "iss": "eagle-test",
            "aud": "eagle-app",
            "iat": now,
            "exp": now + (expiry_hours * 3600),
        }
        
        # Use a simple secret for test tokens
        token = jwt.encode(claims, "test-secret-key", algorithm="HS256")
        return token
    except ImportError:
        logger.error("PyJWT not installed")
        return ""
