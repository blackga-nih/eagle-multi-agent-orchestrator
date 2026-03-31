"""Tests for admin CRUD tool handlers — manage_skills, manage_prompts, manage_templates."""

from __future__ import annotations

from unittest.mock import patch

from app.tools.admin_tools import (
    exec_manage_prompts,
    exec_manage_skills,
    exec_manage_templates,
)

TENANT = "dev-tenant"


def _assert_keys(result: dict, *keys: str) -> None:
    for key in keys:
        assert key in result, f"Missing key '{key}' in {list(result.keys())}"


# ---------------------------------------------------------------------------
# TestManageSkills
# ---------------------------------------------------------------------------

SKILL_ITEM = {
    "skill_id": "sk-001",
    "tenant_id": TENANT,
    "name": "test_skill",
    "display_name": "Test Skill",
    "description": "A test skill",
    "prompt_body": "Do the thing",
    "status": "draft",
}


class TestManageSkills:
    @patch("app.skill_store.list_skills", return_value=[SKILL_ITEM])
    def test_list_returns_action_count_skills(self, mock_list):
        result = exec_manage_skills({"action": "list"}, TENANT)
        _assert_keys(result, "action", "count", "skills")
        assert result["action"] == "list"
        assert result["count"] == 1
        assert len(result["skills"]) == 1
        mock_list.assert_called_once_with(TENANT, status=None)

    @patch("app.skill_store.list_skills", return_value=[SKILL_ITEM])
    def test_list_is_default_action(self, mock_list):
        result = exec_manage_skills({}, TENANT)
        assert result["action"] == "list"

    @patch("app.skill_store.get_skill", return_value=SKILL_ITEM)
    def test_get_returns_action_skill(self, mock_get):
        result = exec_manage_skills({"action": "get", "skill_id": "sk-001"}, TENANT)
        _assert_keys(result, "action", "skill")
        assert result["action"] == "get"

    @patch("app.skill_store.get_skill", return_value=None)
    def test_get_not_found_returns_error(self, mock_get):
        result = exec_manage_skills({"action": "get", "skill_id": "nope"}, TENANT)
        assert "error" in result

    def test_get_missing_skill_id_returns_error(self):
        result = exec_manage_skills({"action": "get"}, TENANT)
        assert "error" in result
        assert "skill_id" in result["error"]

    @patch("app.skill_store.create_skill", return_value=SKILL_ITEM)
    def test_create_returns_action_skill(self, mock_create):
        result = exec_manage_skills(
            {
                "action": "create",
                "name": "s",
                "display_name": "S",
                "description": "d",
                "prompt_body": "p",
            },
            TENANT,
        )
        _assert_keys(result, "action", "skill")
        assert result["action"] == "create"

    def test_create_missing_required_fields_returns_error(self):
        # Missing prompt_body
        result = exec_manage_skills(
            {"action": "create", "name": "s", "display_name": "S", "description": "d"},
            TENANT,
        )
        assert "error" in result
        assert "prompt_body" in result["error"]

    @patch("app.skill_store.update_skill", return_value=SKILL_ITEM)
    def test_update_returns_action_skill(self, mock_update):
        result = exec_manage_skills(
            {"action": "update", "skill_id": "sk-001", "name": "new_name"}, TENANT
        )
        _assert_keys(result, "action", "skill")
        assert result["action"] == "update"

    @patch("app.skill_store.update_skill", return_value=None)
    def test_update_not_found_returns_error(self, mock_update):
        result = exec_manage_skills(
            {"action": "update", "skill_id": "nope", "name": "x"}, TENANT
        )
        assert "error" in result

    def test_update_missing_skill_id_returns_error(self):
        result = exec_manage_skills({"action": "update"}, TENANT)
        assert "error" in result

    @patch("app.skill_store.delete_skill", return_value=True)
    def test_delete_returns_action_deleted_skill_id(self, mock_del):
        result = exec_manage_skills(
            {"action": "delete", "skill_id": "sk-001"}, TENANT
        )
        _assert_keys(result, "action", "deleted", "skill_id")
        assert result["deleted"] is True

    def test_delete_missing_skill_id_returns_error(self):
        result = exec_manage_skills({"action": "delete"}, TENANT)
        assert "error" in result

    @patch("app.skill_store.submit_for_review", return_value=SKILL_ITEM)
    def test_submit_returns_action_skill(self, mock_submit):
        result = exec_manage_skills(
            {"action": "submit", "skill_id": "sk-001"}, TENANT
        )
        _assert_keys(result, "action", "skill")
        assert result["action"] == "submit"

    @patch("app.skill_store.submit_for_review", return_value=None)
    def test_submit_not_found_returns_error(self, mock_submit):
        result = exec_manage_skills(
            {"action": "submit", "skill_id": "nope"}, TENANT
        )
        assert "error" in result

    def test_submit_missing_skill_id_returns_error(self):
        result = exec_manage_skills({"action": "submit"}, TENANT)
        assert "error" in result

    @patch("app.skill_store.publish_skill", return_value=SKILL_ITEM)
    def test_publish_returns_action_skill(self, mock_pub):
        result = exec_manage_skills(
            {"action": "publish", "skill_id": "sk-001"}, TENANT
        )
        _assert_keys(result, "action", "skill")
        assert result["action"] == "publish"

    @patch("app.skill_store.publish_skill", return_value=None)
    def test_publish_not_found_returns_error(self, mock_pub):
        result = exec_manage_skills(
            {"action": "publish", "skill_id": "nope"}, TENANT
        )
        assert "error" in result

    @patch("app.skill_store.disable_skill", return_value=SKILL_ITEM)
    def test_disable_returns_action_skill(self, mock_dis):
        result = exec_manage_skills(
            {"action": "disable", "skill_id": "sk-001"}, TENANT
        )
        _assert_keys(result, "action", "skill")
        assert result["action"] == "disable"

    @patch("app.skill_store.disable_skill", return_value=None)
    def test_disable_not_found_returns_error(self, mock_dis):
        result = exec_manage_skills(
            {"action": "disable", "skill_id": "nope"}, TENANT
        )
        assert "error" in result

    def test_unknown_action_returns_error(self):
        result = exec_manage_skills({"action": "explode"}, TENANT)
        assert "error" in result
        assert "explode" in result["error"]


# ---------------------------------------------------------------------------
# TestManagePrompts
# ---------------------------------------------------------------------------

PROMPT_ITEM = {
    "tenant_id": TENANT,
    "agent_name": "supervisor",
    "prompt_body": "You are the supervisor.",
}


class TestManagePrompts:
    @patch("app.prompt_store.list_tenant_prompts", return_value=[PROMPT_ITEM])
    def test_list_returns_action_count_prompts(self, mock_list):
        result = exec_manage_prompts({"action": "list"}, TENANT)
        _assert_keys(result, "action", "count", "prompts")
        assert result["action"] == "list"
        assert result["count"] == 1

    @patch("app.prompt_store.list_tenant_prompts", return_value=[])
    def test_list_is_default_action(self, mock_list):
        result = exec_manage_prompts({}, TENANT)
        assert result["action"] == "list"

    @patch("app.prompt_store.get_prompt", return_value=PROMPT_ITEM)
    def test_get_returns_action_prompt(self, mock_get):
        result = exec_manage_prompts(
            {"action": "get", "agent_name": "supervisor"}, TENANT
        )
        _assert_keys(result, "action", "prompt")
        assert result["action"] == "get"

    @patch("app.prompt_store.get_prompt", return_value=None)
    def test_get_not_found_returns_error(self, mock_get):
        result = exec_manage_prompts(
            {"action": "get", "agent_name": "nope"}, TENANT
        )
        assert "error" in result

    def test_get_missing_agent_name_returns_error(self):
        result = exec_manage_prompts({"action": "get"}, TENANT)
        assert "error" in result
        assert "agent_name" in result["error"]

    @patch("app.prompt_store.put_prompt", return_value=PROMPT_ITEM)
    def test_set_returns_action_prompt(self, mock_put):
        result = exec_manage_prompts(
            {"action": "set", "agent_name": "supervisor", "prompt_body": "New prompt"},
            TENANT,
        )
        _assert_keys(result, "action", "prompt")
        assert result["action"] == "set"

    def test_set_missing_fields_returns_error(self):
        # Missing prompt_body
        result = exec_manage_prompts(
            {"action": "set", "agent_name": "supervisor"}, TENANT
        )
        assert "error" in result

    @patch("app.prompt_store.delete_prompt", return_value=True)
    def test_delete_returns_action_deleted_agent_name(self, mock_del):
        result = exec_manage_prompts(
            {"action": "delete", "agent_name": "supervisor"}, TENANT
        )
        _assert_keys(result, "action", "deleted", "agent_name")
        assert result["deleted"] is True

    def test_delete_missing_agent_name_returns_error(self):
        result = exec_manage_prompts({"action": "delete"}, TENANT)
        assert "error" in result

    @patch("app.prompt_store.resolve_prompt", return_value="Resolved prompt body")
    def test_resolve_returns_action_agent_name_resolved_body(self, mock_resolve):
        result = exec_manage_prompts(
            {"action": "resolve", "agent_name": "supervisor"}, TENANT
        )
        _assert_keys(result, "action", "agent_name", "resolved_body")
        assert result["resolved_body"] == "Resolved prompt body"

    def test_resolve_missing_agent_name_returns_error(self):
        result = exec_manage_prompts({"action": "resolve"}, TENANT)
        assert "error" in result

    def test_unknown_action_returns_error(self):
        result = exec_manage_prompts({"action": "nuke"}, TENANT)
        assert "error" in result
        assert "nuke" in result["error"]


# ---------------------------------------------------------------------------
# TestManageTemplates
# ---------------------------------------------------------------------------

TEMPLATE_ITEM = {
    "tenant_id": TENANT,
    "doc_type": "sow",
    "template_body": "## Statement of Work\n\n...",
}


class TestManageTemplates:
    @patch("app.template_store.list_tenant_templates", return_value=[TEMPLATE_ITEM])
    def test_list_returns_action_count_templates(self, mock_list):
        result = exec_manage_templates({"action": "list"}, TENANT)
        _assert_keys(result, "action", "count", "templates")
        assert result["action"] == "list"
        assert result["count"] == 1

    @patch("app.template_store.list_tenant_templates", return_value=[])
    def test_list_is_default_action(self, mock_list):
        result = exec_manage_templates({}, TENANT)
        assert result["action"] == "list"

    @patch("app.template_store.get_template", return_value=TEMPLATE_ITEM)
    def test_get_returns_action_template(self, mock_get):
        result = exec_manage_templates(
            {"action": "get", "doc_type": "sow"}, TENANT
        )
        _assert_keys(result, "action", "template")
        assert result["action"] == "get"

    @patch("app.template_store.get_template", return_value=None)
    def test_get_not_found_returns_error(self, mock_get):
        result = exec_manage_templates(
            {"action": "get", "doc_type": "nope"}, TENANT
        )
        assert "error" in result

    def test_get_missing_doc_type_returns_error(self):
        result = exec_manage_templates({"action": "get"}, TENANT)
        assert "error" in result
        assert "doc_type" in result["error"]

    @patch("app.template_store.put_template", return_value=TEMPLATE_ITEM)
    def test_set_returns_action_template(self, mock_put):
        result = exec_manage_templates(
            {"action": "set", "doc_type": "sow", "template_body": "body"},
            TENANT,
        )
        _assert_keys(result, "action", "template")
        assert result["action"] == "set"

    def test_set_missing_fields_returns_error(self):
        # Missing template_body
        result = exec_manage_templates(
            {"action": "set", "doc_type": "sow"}, TENANT
        )
        assert "error" in result

    @patch("app.template_store.delete_template", return_value=True)
    def test_delete_returns_action_deleted_doc_type(self, mock_del):
        result = exec_manage_templates(
            {"action": "delete", "doc_type": "sow"}, TENANT
        )
        _assert_keys(result, "action", "deleted", "doc_type")
        assert result["deleted"] is True

    def test_delete_missing_doc_type_returns_error(self):
        result = exec_manage_templates({"action": "delete"}, TENANT)
        assert "error" in result

    @patch(
        "app.template_store.resolve_template",
        return_value=("Resolved body", "tenant", {"version": 1}),
    )
    def test_resolve_returns_action_doc_type_resolved_body_source_metadata(
        self, mock_resolve
    ):
        result = exec_manage_templates(
            {"action": "resolve", "doc_type": "sow"}, TENANT
        )
        _assert_keys(result, "action", "doc_type", "resolved_body", "source", "metadata")
        assert result["resolved_body"] == "Resolved body"
        assert result["source"] == "tenant"
        assert result["metadata"] == {"version": 1}

    def test_resolve_missing_doc_type_returns_error(self):
        result = exec_manage_templates({"action": "resolve"}, TENANT)
        assert "error" in result

    def test_unknown_action_returns_error(self):
        result = exec_manage_templates({"action": "boom"}, TENANT)
        assert "error" in result
        assert "boom" in result["error"]
