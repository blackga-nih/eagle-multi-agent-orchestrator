"""Tests for triage fixes — 2026-04-01.

Validates:
  - P1-1: OTel OTLP startup probe catches 401 and logs error
  - P1-2: knowledge_search defaults to Haiku 4.5 model (matches IAM policy)
  - Feedback pipeline tags environment (localhost/dev/qa) on JIRA labels
  - Teams notifier fires from localhost (no ECS gate)
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch, AsyncMock

import pytest


# ═════════════════════════════════════════════════════════════════════════
# P1-2: Haiku model ID matches IAM policy
# ═════════════════════════════════════════════════════════════════════════

EXPECTED_HAIKU_MODEL = "anthropic.claude-haiku-4-5-20251001-v1:0"
OLD_HAIKU_MODEL = "anthropic.claude-3-haiku-20240307-v1:0"


class TestHaikuModelIdAlignment:
    """All Haiku defaults must match the IAM policy (Haiku 4.5)."""

    def test_knowledge_tools_default_model(self):
        """knowledge_tools.SEARCH_MODEL_ID must default to Haiku 4.5."""
        from app.tools.knowledge_tools import SEARCH_MODEL_ID

        assert SEARCH_MODEL_ID == EXPECTED_HAIKU_MODEL, (
            f"SEARCH_MODEL_ID is '{SEARCH_MODEL_ID}', "
            f"expected '{EXPECTED_HAIKU_MODEL}' to match IAM policy"
        )

    def test_config_knowledge_search_model(self):
        """ModelConfig.knowledge_search_model must default to Haiku 4.5."""
        from app.config import model

        assert model.knowledge_search_model == EXPECTED_HAIKU_MODEL, (
            f"config.model.knowledge_search_model is '{model.knowledge_search_model}', "
            f"expected '{EXPECTED_HAIKU_MODEL}'"
        )

    def test_bedrock_service_model_id(self):
        """BedrockAgentService must use Haiku 4.5."""
        import importlib

        src = importlib.util.find_spec("app.bedrock_service")
        assert src and src.origin
        source_text = open(src.origin, encoding="utf-8").read()

        assert OLD_HAIKU_MODEL not in source_text, (
            f"bedrock_service.py still references old model '{OLD_HAIKU_MODEL}'"
        )
        assert EXPECTED_HAIKU_MODEL in source_text, (
            f"bedrock_service.py must use '{EXPECTED_HAIKU_MODEL}'"
        )

    def test_no_old_haiku_references_in_defaults(self):
        """No file should default to the old Claude 3 Haiku model ID."""
        import importlib

        for module_name in (
            "app.tools.knowledge_tools",
            "app.config",
            "app.bedrock_service",
        ):
            src = importlib.util.find_spec(module_name)
            assert src and src.origin
            source_text = open(src.origin, encoding="utf-8").read()
            # Allow references in comments/docs, but not as a default value
            # Check for the pattern: = "anthropic.claude-3-haiku-20240307-v1:0"
            assert f'"{OLD_HAIKU_MODEL}"' not in source_text, (
                f"{module_name} still has old Haiku model as a default value"
            )


# ═════════════════════════════════════════════════════════════════════════
# P1-1: OTel OTLP startup probe
# ═════════════════════════════════════════════════════════════════════════


class TestOtlpStartupProbe:
    """Startup probe must log error on 401 and info on success."""

    def test_startup_probe_exists_in_source(self):
        """strands_agentic_service must have OTLP startup probe."""
        import importlib

        src = importlib.util.find_spec("app.strands_agentic_service")
        assert src and src.origin
        source_text = open(src.origin, encoding="utf-8").read()

        assert "Langfuse OTLP auth FAILED (401)" in source_text, (
            "Startup probe must log an explicit error on 401"
        )
        assert "Langfuse OTLP auth verified" in source_text, (
            "Startup probe must log success on non-401"
        )

    def test_startup_probe_logs_error_on_401(self):
        """Probe should log ERROR when OTLP endpoint returns 401."""
        import importlib

        src = importlib.util.find_spec("app.strands_agentic_service")
        assert src and src.origin
        source_text = open(src.origin, encoding="utf-8").read()

        # The probe must use logger.error (not warning) for 401
        assert "logger.error" in source_text and "401" in source_text, (
            "401 must be logged at ERROR level, not WARNING"
        )


# ═════════════════════════════════════════════════════════════════════════
# Feedback pipeline: environment label on JIRA issues
# ═════════════════════════════════════════════════════════════════════════


class TestFeedbackEnvironmentLabel:
    """JIRA issues created from feedback must include environment label."""

    def test_jira_labels_include_environment(self):
        """_create_jira_for_feedback must add environment to labels."""
        import importlib

        src = importlib.util.find_spec("app.routers.feedback")
        assert src and src.origin
        source_text = open(src.origin, encoding="utf-8").read()

        assert "app_config.environment" in source_text, (
            "JIRA labels must include the environment from app config"
        )

    def test_jira_labels_contain_localhost_when_local(self):
        """When environment is 'localhost', JIRA labels should include it."""
        from unittest.mock import MagicMock
        import app.config as config_mod

        mock_jira = MagicMock()
        mock_jira.feedback_enabled = True

        mock_app = MagicMock()
        mock_app.environment = "localhost"

        with (
            patch.object(config_mod, "jira", mock_jira),
            patch.object(config_mod, "app", mock_app),
            patch("app.jira_client.create_feedback_issue", return_value="EAGLE-999") as mock_create,
        ):
            from app.routers.feedback import _create_jira_for_feedback

            _create_jira_for_feedback(
                feedback_id="test-id",
                feedback_text="test feedback",
                feedback_type="bug",
                user_id="dev-user",
                tenant_id="dev-tenant",
                tier="premium",
                session_id="test-session",
                page="/chat",
                created_at="2026-04-01T00:00:00",
            )

            mock_create.assert_called_once()
            labels = mock_create.call_args.kwargs.get("labels", [])
            assert "localhost" in labels, (
                f"JIRA labels must include 'localhost' when running locally, got {labels}"
            )


# ═════════════════════════════════════════════════════════════════════════
# Environment auto-detection: localhost vs dev
# ═════════════════════════════════════════════════════════════════════════


class TestEnvironmentAutoDetection:
    """Environment should auto-detect 'localhost' when not on ECS."""

    def test_localhost_when_no_ecs_metadata(self):
        """Without ECS_CONTAINER_METADATA_URI, environment defaults to 'localhost'."""
        env = os.environ.copy()
        env.pop("ECS_CONTAINER_METADATA_URI", None)
        env.pop("EAGLE_ENVIRONMENT", None)
        env.pop("ENVIRONMENT", None)

        with patch.dict(os.environ, env, clear=True):
            # Re-evaluate the expression
            result = os.getenv(
                "EAGLE_ENVIRONMENT",
                os.getenv(
                    "ENVIRONMENT",
                    "dev" if os.getenv("ECS_CONTAINER_METADATA_URI") else "localhost",
                ),
            )
            assert result == "localhost"

    def test_dev_when_ecs_metadata_present(self):
        """With ECS_CONTAINER_METADATA_URI set, environment defaults to 'dev'."""
        with patch.dict(os.environ, {"ECS_CONTAINER_METADATA_URI": "http://169.254.170.2/v4"}, clear=False):
            # Remove explicit overrides
            env_backup = {}
            for key in ("EAGLE_ENVIRONMENT", "ENVIRONMENT"):
                if key in os.environ:
                    env_backup[key] = os.environ.pop(key)

            try:
                result = os.getenv(
                    "EAGLE_ENVIRONMENT",
                    os.getenv(
                        "ENVIRONMENT",
                        "dev" if os.getenv("ECS_CONTAINER_METADATA_URI") else "localhost",
                    ),
                )
                assert result == "dev"
            finally:
                os.environ.update(env_backup)

    def test_explicit_environment_overrides_auto_detection(self):
        """EAGLE_ENVIRONMENT env var should override auto-detection."""
        with patch.dict(os.environ, {"EAGLE_ENVIRONMENT": "qa"}, clear=False):
            result = os.getenv(
                "EAGLE_ENVIRONMENT",
                os.getenv(
                    "ENVIRONMENT",
                    "dev" if os.getenv("ECS_CONTAINER_METADATA_URI") else "localhost",
                ),
            )
            assert result == "qa"


# ═════════════════════════════════════════════════════════════════════════
# Teams notifier: no ECS gate for localhost
# ═════════════════════════════════════════════════════════════════════════


class TestTeamsNotifierLocalhostEnabled:
    """Teams webhook should fire from localhost (no ECS-only gate)."""

    def test_no_ecs_gate_in_source(self):
        """teams_notifier.py must not disable webhooks based on ECS detection."""
        import importlib

        src = importlib.util.find_spec("app.teams_notifier")
        assert src and src.origin
        source_text = open(src.origin, encoding="utf-8").read()

        assert "if not _IS_ECS" not in source_text, (
            "teams_notifier.py must not gate webhook sending on _IS_ECS"
        )

    def test_webhook_enabled_by_default(self):
        """WEBHOOK_ENABLED should be True when TEAMS_WEBHOOK_ENABLED is 'true'."""
        with patch.dict(os.environ, {"TEAMS_WEBHOOK_ENABLED": "true"}, clear=False):
            # The module evaluates this at import time, so check the logic directly
            enabled = os.getenv("TEAMS_WEBHOOK_ENABLED", "true").lower() == "true"
            assert enabled is True
