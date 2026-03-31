"""
Centralized configuration for EAGLE backend.

All environment variables should be accessed through this module where practical.
This provides type safety, validation, and a single source of truth for configuration.

Created: 2026-03-19 (Phase 2 refactor)

Usage:
    from app.config import aws, auth, cost, telemetry, webhooks, jira, session, bedrock

    # Access typed config values
    region = aws.region
    table = aws.sessions_table
    if auth.require_auth:
        ...
"""

import os
from dataclasses import dataclass
from typing import Optional

DEFAULT_BEDROCK_SONNET_46_MODEL = "us.anthropic.claude-sonnet-4-6"
DEFAULT_BEDROCK_SONNET_45_MODEL = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
DEFAULT_BEDROCK_SONNET_40_MODEL = "us.anthropic.claude-sonnet-4-20250514-v1:0"
DEFAULT_BEDROCK_HAIKU_MODEL = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
# Backward-compat aliases
DEFAULT_BEDROCK_SONNET_MODEL = DEFAULT_BEDROCK_SONNET_46_MODEL
DEFAULT_ANTHROPIC_SONNET_MODEL = "claude-sonnet-4-6"
DEFAULT_ANTHROPIC_HAIKU_MODEL = "claude-haiku-4-5-20251001"


# ── Helper Functions ─────────────────────────────────────────────────────────


def resolve_model_id(*env_vars: str, default: str) -> str:
    """Return the first non-empty model env var, otherwise default."""
    for env_var in env_vars:
        value = os.getenv(env_var)
        if value:
            return value
    return default


def _bool(env_var: str, default: str = "false") -> bool:
    """Parse boolean from environment variable."""
    return os.getenv(env_var, default).lower() in ("true", "1", "yes")


def _int(env_var: str, default: int) -> int:
    """Parse integer from environment variable with fallback."""
    try:
        return int(os.getenv(env_var, str(default)))
    except (ValueError, TypeError):
        return default


def _float(env_var: str, default: float) -> float:
    """Parse float from environment variable with fallback."""
    try:
        return float(os.getenv(env_var, str(default)))
    except (ValueError, TypeError):
        return default


# ── Configuration Classes ────────────────────────────────────────────────────


@dataclass(frozen=True)
class AWSConfig:
    """AWS infrastructure configuration."""

    region: str = os.getenv("AWS_REGION", "us-east-1")
    sessions_table: str = os.getenv("EAGLE_SESSIONS_TABLE", "eagle")
    s3_bucket: str = os.getenv("S3_BUCKET", "eagle-documents-695681773636-dev")
    metadata_table: str = os.getenv("METADATA_TABLE", "eagle-document-metadata-dev")
    document_bucket: str = os.getenv(
        "DOCUMENT_BUCKET", os.getenv("S3_BUCKET", "eagle-documents-695681773636-dev")
    )


@dataclass(frozen=True)
class AuthConfig:
    """Authentication and authorization configuration."""

    require_auth: bool = _bool("REQUIRE_AUTH", "false")
    dev_mode: bool = _bool("DEV_MODE", "false")
    dev_user_id: str = os.getenv("DEV_USER_ID", "dev-user")
    dev_tenant_id: str = os.getenv("DEV_TENANT_ID", "dev-tenant")
    cognito_region: str = os.getenv(
        "COGNITO_REGION", os.getenv("AWS_REGION", "us-east-1")
    )
    cognito_user_pool_id: str = os.getenv("COGNITO_USER_POOL_ID", "")
    cognito_client_id: str = os.getenv("COGNITO_CLIENT_ID", "")


@dataclass(frozen=True)
class BedrockConfig:
    """AWS Bedrock model configuration."""

    model_id: Optional[str] = os.getenv("EAGLE_BEDROCK_MODEL_ID")
    connect_timeout: int = _int("EAGLE_BEDROCK_CONNECT_TIMEOUT", 60)
    read_timeout: int = _int("EAGLE_BEDROCK_READ_TIMEOUT", 300)
    max_attempts: int = _int("EAGLE_BEDROCK_MAX_ATTEMPTS", 4)
    retry_mode: str = os.getenv("EAGLE_BEDROCK_RETRY_MODE", "adaptive")
    use_bedrock: bool = _bool("USE_BEDROCK", "false")


@dataclass(frozen=True)
class CostConfig:
    """Token cost calculation configuration (Claude 3.5 Sonnet via Bedrock)."""

    input_per_1k: float = _float("COST_INPUT_PER_1K", 0.003)
    output_per_1k: float = _float("COST_OUTPUT_PER_1K", 0.015)


@dataclass(frozen=True)
class TelemetryConfig:
    """Observability and telemetry configuration."""

    langfuse_public_key: Optional[str] = os.getenv("LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: Optional[str] = os.getenv("LANGFUSE_SECRET_KEY")
    langfuse_host: str = os.getenv("LANGFUSE_HOST", "https://us.cloud.langfuse.com")
    langfuse_project_id: str = os.getenv("LANGFUSE_PROJECT_ID", "")
    cloudwatch_log_group: str = os.getenv(
        "EAGLE_TELEMETRY_LOG_GROUP", "/eagle/telemetry"
    )
    trace_store_backend: str = os.getenv("TRACE_STORE", "local").lower()
    trace_ttl_days: int = _int("TRACE_TTL_DAYS", 30)


@dataclass(frozen=True)
class WebhookConfig:
    """Webhook notification configuration."""

    # Teams notifications
    teams_url: str = os.getenv(
        "TEAMS_WEBHOOK_URL", os.getenv("TEAMS_QA_WEBHOOK_URL", "")
    )
    teams_enabled: bool = _bool("TEAMS_WEBHOOK_ENABLED", "true")
    teams_timeout: float = _float("TEAMS_WEBHOOK_TIMEOUT", 5.0)
    teams_daily_summary_enabled: bool = _bool("TEAMS_DAILY_SUMMARY_ENABLED", "true")
    teams_daily_summary_hour: int = _int("TEAMS_DAILY_SUMMARY_HOUR", 13)

    # Error notifications
    error_url: str = os.getenv("ERROR_WEBHOOK_URL", "")
    error_enabled: bool = _bool("ERROR_WEBHOOK_ENABLED", "true")
    error_timeout: float = _float("ERROR_WEBHOOK_TIMEOUT", 5.0)
    error_rate_limit: int = _int("ERROR_WEBHOOK_RATE_LIMIT", 10)
    error_include_traceback: bool = _bool("ERROR_WEBHOOK_INCLUDE_TRACEBACK", "true")
    error_min_status: int = _int("ERROR_WEBHOOK_MIN_STATUS", 500)
    error_exclude_paths: list = None  # Initialized in __post_init__

    def __post_init__(self):
        # Handle mutable default for exclude_paths
        if self.error_exclude_paths is None:
            paths = os.getenv("ERROR_WEBHOOK_EXCLUDE_PATHS", "/api/health")
            object.__setattr__(
                self,
                "error_exclude_paths",
                [p.strip() for p in paths.split(",") if p.strip()],
            )


@dataclass(frozen=True)
class JiraConfig:
    """JIRA integration configuration (NCI self-hosted, PAT auth)."""

    base_url: str = os.getenv("JIRA_BASE_URL", "")
    api_token: str = os.getenv("JIRA_API_TOKEN", "")
    project_key: str = os.getenv("JIRA_PROJECT", "EAGLE")
    timeout: float = _float("JIRA_TIMEOUT", 5.0)
    feedback_enabled: bool = _bool("JIRA_FEEDBACK_ENABLED", "false")


@dataclass(frozen=True)
class SessionConfig:
    """Session management configuration."""

    ttl_days: int = _int("SESSION_TTL_DAYS", 30)
    use_persistent: bool = _bool("USE_PERSISTENT_SESSIONS", "true")


@dataclass(frozen=True)
class ModelConfig:
    """AI model configuration."""

    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", DEFAULT_ANTHROPIC_HAIKU_MODEL)
    sdk_model: str = os.getenv("EAGLE_SDK_MODEL", "haiku")
    knowledge_search_model: str = os.getenv(
        "KNOWLEDGE_SEARCH_MODEL", "anthropic.claude-3-haiku-20240307-v1:0"
    )


@dataclass(frozen=True)
class AppConfig:
    """Application-level configuration."""

    environment: str = os.getenv("EAGLE_ENVIRONMENT", os.getenv("ENVIRONMENT", "dev"))
    port: int = _int("APP_PORT", 8000)
    is_ecs: bool = os.getenv("ECS_CONTAINER_METADATA_URI") is not None


# ── Singleton Instances ──────────────────────────────────────────────────────
# These are instantiated at module load time for fast access

aws = AWSConfig()
auth = AuthConfig()
bedrock = BedrockConfig()
cost = CostConfig()
telemetry = TelemetryConfig()
webhooks = WebhookConfig()
jira = JiraConfig()
session = SessionConfig()
model = ModelConfig()
app = AppConfig()


# ── Validation ───────────────────────────────────────────────────────────────


def validate() -> list[str]:
    """
    Validate configuration and return list of warnings.
    Call at startup to catch configuration issues early.
    """
    warnings = []

    # Auth validation
    if auth.require_auth and not auth.cognito_user_pool_id:
        warnings.append("REQUIRE_AUTH=true but COGNITO_USER_POOL_ID not set")
    if auth.require_auth and not auth.cognito_client_id:
        warnings.append("REQUIRE_AUTH=true but COGNITO_CLIENT_ID not set")

    # Telemetry validation
    if telemetry.langfuse_public_key and not telemetry.langfuse_secret_key:
        warnings.append("LANGFUSE_PUBLIC_KEY set but LANGFUSE_SECRET_KEY missing")

    # Webhook validation
    if webhooks.teams_enabled and not webhooks.teams_url:
        warnings.append("TEAMS_WEBHOOK_ENABLED=true but TEAMS_WEBHOOK_URL not set")

    # JIRA validation
    if jira.feedback_enabled and not jira.base_url:
        warnings.append("JIRA_FEEDBACK_ENABLED=true but JIRA_BASE_URL not set")
    if jira.feedback_enabled and not jira.api_token:
        warnings.append("JIRA_FEEDBACK_ENABLED=true but JIRA_API_TOKEN not set")

    return warnings


def print_config_summary():
    """Print a summary of the current configuration (for debugging)."""
    print(f"[CONFIG] Environment: {app.environment}")
    print(f"[CONFIG] AWS Region: {aws.region}")
    print(f"[CONFIG] Auth Required: {auth.require_auth}")
    print(f"[CONFIG] Dev Mode: {auth.dev_mode}")
    print(f"[CONFIG] Sessions Table: {aws.sessions_table}")
    print(f"[CONFIG] S3 Bucket: {aws.s3_bucket}")
    if warnings := validate():
        print(f"[CONFIG] Warnings: {warnings}")
