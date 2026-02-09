import os
from typing import Dict, Any
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    # Bedrock Agent Configuration (Legacy)
    BEDROCK_AGENT_ID = os.getenv("BEDROCK_AGENT_ID", "")
    BEDROCK_AGENT_ALIAS_ID = os.getenv("BEDROCK_AGENT_ALIAS_ID", "TSTALIASID")
    AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

    # Application Configuration
    # Bind to localhost for security - use reverse proxy for external access
    APP_HOST = os.getenv("APP_HOST", "127.0.0.1")
    APP_PORT = int(os.getenv("APP_PORT", "8000"))

    # Cognito Configuration
    COGNITO_USER_POOL_ID = os.getenv("COGNITO_USER_POOL_ID", "")
    COGNITO_CLIENT_ID = os.getenv("COGNITO_CLIENT_ID", "")

    # DynamoDB Configuration
    SESSIONS_TABLE = os.getenv("SESSIONS_TABLE", "tenant-sessions")
    USAGE_TABLE = os.getenv("USAGE_TABLE", "tenant-usage")
    EAGLE_SESSIONS_TABLE = os.getenv("EAGLE_SESSIONS_TABLE", "eagle")

    # JWT Configuration
    JWT_SECRET = os.getenv("JWT_SECRET", "your-secret-key")
    JWT_ALGORITHM = "HS256"
    JWT_EXPIRATION_HOURS = 24

    # EAGLE Configuration
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    USE_BEDROCK = os.getenv("USE_BEDROCK", "false").lower() == "true"
    ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "")
    S3_BUCKET = os.getenv("S3_BUCKET", "nci-documents")
    S3_PREFIX = os.getenv("S3_PREFIX", "eagle/")

    # Feature Flags
    USE_PERSISTENT_SESSIONS = os.getenv("USE_PERSISTENT_SESSIONS", "true").lower() == "true"
    REQUIRE_AUTH = os.getenv("REQUIRE_AUTH", "false").lower() == "true"
    DEV_MODE = os.getenv("DEV_MODE", "false").lower() == "true"

    # OpenClaw Gateway (Optional)
    OPENCLAW_GATEWAY_URL = os.getenv("OPENCLAW_GATEWAY_URL", "ws://localhost:18789")
    OPENCLAW_GATEWAY_TOKEN = os.getenv("OPENCLAW_GATEWAY_TOKEN", "")

    # Cost Configuration
    COST_INPUT_PER_1K = float(os.getenv("COST_INPUT_PER_1K", "0.003"))
    COST_OUTPUT_PER_1K = float(os.getenv("COST_OUTPUT_PER_1K", "0.015"))

    # Session Configuration
    SESSION_TTL_DAYS = int(os.getenv("SESSION_TTL_DAYS", "30"))

    @classmethod
    def validate_config(cls) -> Dict[str, Any]:
        """Validate required configuration"""
        errors = []
        warnings = []

        if not cls.COGNITO_USER_POOL_ID:
            errors.append("COGNITO_USER_POOL_ID is required")

        if not cls.COGNITO_CLIENT_ID:
            errors.append("COGNITO_CLIENT_ID is required")

        if not cls.ANTHROPIC_API_KEY and not cls.USE_BEDROCK:
            warnings.append("ANTHROPIC_API_KEY not set and USE_BEDROCK is false - EAGLE chat will not work")

        if cls.DEV_MODE:
            warnings.append("DEV_MODE is enabled - auth is bypassed")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "config": {
                "agent_id": cls.BEDROCK_AGENT_ID,
                "agent_alias_id": cls.BEDROCK_AGENT_ALIAS_ID,
                "aws_region": cls.AWS_REGION,
                "anthropic_configured": bool(cls.ANTHROPIC_API_KEY) or cls.USE_BEDROCK,
                "use_bedrock": cls.USE_BEDROCK,
                "s3_bucket": cls.S3_BUCKET,
                "persistent_sessions": cls.USE_PERSISTENT_SESSIONS,
                "dev_mode": cls.DEV_MODE,
            }
        }
