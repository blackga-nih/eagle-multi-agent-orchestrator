"""
EAGLE Strands Model Configuration

BedrockModel setup and tier-based tool access configuration.
"""

import logging
import os

from botocore.config import Config
from strands.models import BedrockModel
from strands.models.model import CacheConfig

logger = logging.getLogger("eagle.strands_agent")

# Model selection constants
_NCI_ACCOUNT = "695681773636"
_SONNET = "us.anthropic.claude-sonnet-4-6"
_HAIKU = "us.anthropic.claude-haiku-4-5-20251001-v1:0"


def _default_model() -> str:
    """Determine default model based on environment and AWS account."""
    env_model = os.getenv("EAGLE_BEDROCK_MODEL_ID")
    if env_model:
        return env_model
    try:
        import boto3

        account = boto3.client("sts").get_caller_identity()["Account"]
        return _SONNET if account == _NCI_ACCOUNT else _HAIKU
    except Exception:
        return _HAIKU


MODEL = _default_model()
logger.info("EAGLE model: %s", MODEL)


# Shared Bedrock client config
_bedrock_client_config = Config(
    connect_timeout=int(os.getenv("EAGLE_BEDROCK_CONNECT_TIMEOUT", "60")),
    read_timeout=int(os.getenv("EAGLE_BEDROCK_READ_TIMEOUT", "300")),
    retries={
        "max_attempts": int(os.getenv("EAGLE_BEDROCK_MAX_ATTEMPTS", "4")),
        "mode": os.getenv("EAGLE_BEDROCK_RETRY_MODE", "adaptive"),
    },
    tcp_keepalive=True,
)

# Shared BedrockModel instance — reused across all requests
# boto3 handles SSO/IAM natively — no credential bridging needed
shared_model = BedrockModel(
    model_id=MODEL,
    region_name=os.getenv("AWS_REGION", "us-east-1"),
    boto_client_config=_bedrock_client_config,
    # Bedrock prompt caching — requires boto3>=1.37.24 (native cachePoint support).
    # cache_tools: appends cachePoint to toolConfig, caching 34 tool schemas (~17K tokens).
    # cache_config: auto-injects cachePoint at last user message for prefix caching.
    # 5-min TTL, refreshes on hit. ~2-4s TTFT reduction, ~90% input token cost savings.
    cache_tools="default",
    cache_config=CacheConfig(strategy="auto"),
)


# Tier-gated tool access (preserved from sdk_agentic_service.py)
# Note: Strands subagents don't use CLI tools like Read/Glob/Grep.
# These are kept for compatibility; in Strands, tool access is managed
# via the @tool functions registered on the Agent.
TIER_TOOLS: dict[str, list[str]] = {
    "basic": [],
    "advanced": ["Read", "Glob", "Grep"],
    "premium": ["Read", "Glob", "Grep", "Bash"],
}

TIER_BUDGETS: dict[str, float] = {
    "basic": 0.10,
    "advanced": 0.25,
    "premium": 0.75,
}
