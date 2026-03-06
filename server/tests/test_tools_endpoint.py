"""Integration-style tests for /api/tools exposure."""

from __future__ import annotations

import os
import sys
from typing import AsyncGenerator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

_server_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)


async def _mock_sdk_query(*args, **kwargs) -> AsyncGenerator:
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "Mock response from EAGLE."

    assistant_msg = MagicMock()
    assistant_msg.__class__.__name__ = "AssistantMessage"
    assistant_msg.content = [text_block]

    result_msg = MagicMock()
    result_msg.__class__.__name__ = "ResultMessage"
    result_msg.usage = {"input_tokens": 10, "output_tokens": 5}
    result_msg.result = "Mock response from EAGLE."

    yield assistant_msg
    yield result_msg


@pytest.fixture(scope="module")
def app_instance():
    env_patch = {
        "REQUIRE_AUTH": "false",
        "DEV_MODE": "false",
        "USE_BEDROCK": "false",
        "USE_PERSISTENT_SESSIONS": "false",
    }
    with patch.dict(os.environ, env_patch, clear=False):
        with patch("app.strands_agentic_service.sdk_query", side_effect=_mock_sdk_query):
            import importlib
            import app.main as main_module
            importlib.reload(main_module)
            yield main_module.app


def test_api_tools_includes_knowledge_base_tools(app_instance):
    with TestClient(app_instance) as client:
        resp = client.get("/api/tools")
    assert resp.status_code == 200
    data = resp.json()
    tool_names = {tool["name"] for tool in data["tools"]}
    assert "knowledge_search" in tool_names
    assert "knowledge_fetch" in tool_names
