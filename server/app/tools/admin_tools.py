"""Active admin CRUD and compliance handlers."""

from __future__ import annotations

import json
import logging

logger = logging.getLogger("eagle.admin_tools")


def exec_query_compliance_matrix(params: dict, tenant_id: str) -> dict:
    """Execute a compliance matrix operation (read-only, no tenant scoping).

    Returns pmr_checklist_s3_key and frc_checklist_s3_key as metadata —
    the composite ``research`` tool handles dynamic checklist fetching.
    """
    from ..compliance_matrix import execute_operation

    raw = params.get("params", params)
    if isinstance(raw, str):
        raw = json.loads(raw)
    return execute_operation(raw)


def exec_manage_skills(params: dict, tenant_id: str) -> dict:
    from app.skill_store import (
        create_skill,
        delete_skill,
        disable_skill,
        get_skill,
        list_skills,
        publish_skill,
        submit_for_review,
        update_skill,
    )

    action = params.get("action", "list")
    if action == "list":
        items = list_skills(tenant_id, status=params.get("status"))
        return {"action": "list", "count": len(items), "skills": items}
    if action == "get":
        skill_id = params.get("skill_id")
        if not skill_id:
            return {"error": "skill_id is required for get"}
        item = get_skill(tenant_id, skill_id)
        return (
            {"action": "get", "skill": item}
            if item
            else {"error": f"Skill {skill_id} not found"}
        )
    if action == "create":
        required = ["name", "display_name", "description", "prompt_body"]
        missing = [field for field in required if not params.get(field)]
        if missing:
            return {"error": f"Missing required fields: {', '.join(missing)}"}
        item = create_skill(
            tenant_id=tenant_id,
            owner_user_id=params.get("owner_user_id", "admin"),
            name=params["name"],
            display_name=params["display_name"],
            description=params["description"],
            prompt_body=params["prompt_body"],
            triggers=params.get("triggers"),
            tools=params.get("tools"),
            model=params.get("model"),
            visibility=params.get("visibility", "private"),
        )
        return {"action": "create", "skill": item}
    if action == "update":
        skill_id = params.get("skill_id")
        if not skill_id:
            return {"error": "skill_id is required for update"}
        updates = {k: v for k, v in params.items() if k not in ("action", "skill_id")}
        item = update_skill(tenant_id, skill_id, updates)
        return (
            {"action": "update", "skill": item}
            if item
            else {"error": f"Skill {skill_id} not found or no updatable fields"}
        )
    if action == "delete":
        skill_id = params.get("skill_id")
        if not skill_id:
            return {"error": "skill_id is required for delete"}
        ok = delete_skill(tenant_id, skill_id)
        return {"action": "delete", "deleted": ok, "skill_id": skill_id}
    if action == "submit":
        skill_id = params.get("skill_id")
        if not skill_id:
            return {"error": "skill_id is required for submit"}
        item = submit_for_review(tenant_id, skill_id)
        return (
            {"action": "submit", "skill": item}
            if item
            else {"error": f"Skill {skill_id} not found or not in draft status"}
        )
    if action == "publish":
        skill_id = params.get("skill_id")
        if not skill_id:
            return {"error": "skill_id is required for publish"}
        item = publish_skill(tenant_id, skill_id)
        return (
            {"action": "publish", "skill": item}
            if item
            else {"error": f"Skill {skill_id} not found or not in review status"}
        )
    if action == "disable":
        skill_id = params.get("skill_id")
        if not skill_id:
            return {"error": "skill_id is required for disable"}
        item = disable_skill(tenant_id, skill_id)
        return (
            {"action": "disable", "skill": item}
            if item
            else {"error": f"Skill {skill_id} not found or not in active status"}
        )
    return {
        "error": f"Unknown action: {action}. Valid: list, get, create, update, delete, submit, publish, disable"
    }


def exec_manage_prompts(params: dict, tenant_id: str) -> dict:
    from app.prompt_store import (
        delete_prompt,
        get_prompt,
        list_tenant_prompts,
        put_prompt,
        resolve_prompt,
    )

    action = params.get("action", "list")
    if action == "list":
        items = list_tenant_prompts(tenant_id)
        return {"action": "list", "count": len(items), "prompts": items}
    if action == "get":
        agent_name = params.get("agent_name")
        if not agent_name:
            return {"error": "agent_name is required for get"}
        item = get_prompt(tenant_id, agent_name)
        return (
            {"action": "get", "prompt": item}
            if item
            else {"error": f"No prompt override for agent '{agent_name}'"}
        )
    if action == "set":
        agent_name = params.get("agent_name")
        prompt_body = params.get("prompt_body")
        if not agent_name or not prompt_body:
            return {"error": "agent_name and prompt_body are required for set"}
        item = put_prompt(
            tenant_id=tenant_id,
            agent_name=agent_name,
            prompt_body=prompt_body,
            is_append=params.get("is_append", False),
        )
        return {"action": "set", "prompt": item}
    if action == "delete":
        agent_name = params.get("agent_name")
        if not agent_name:
            return {"error": "agent_name is required for delete"}
        ok = delete_prompt(tenant_id, agent_name)
        return {"action": "delete", "deleted": ok, "agent_name": agent_name}
    if action == "resolve":
        agent_name = params.get("agent_name")
        if not agent_name:
            return {"error": "agent_name is required for resolve"}
        body = resolve_prompt(tenant_id, agent_name)
        return {"action": "resolve", "agent_name": agent_name, "resolved_body": body}
    return {
        "error": f"Unknown action: {action}. Valid: list, get, set, delete, resolve"
    }


def exec_manage_templates(params: dict, tenant_id: str) -> dict:
    from app.template_store import (
        delete_template,
        get_template,
        list_tenant_templates,
        put_template,
        resolve_template,
    )

    action = params.get("action", "list")
    if action == "list":
        items = list_tenant_templates(tenant_id, doc_type=params.get("doc_type"))
        return {"action": "list", "count": len(items), "templates": items}
    if action == "get":
        doc_type = params.get("doc_type")
        if not doc_type:
            return {"error": "doc_type is required for get"}
        item = get_template(
            tenant_id, doc_type, user_id=params.get("user_id", "shared")
        )
        return (
            {"action": "get", "template": item}
            if item
            else {"error": f"No template for doc_type '{doc_type}'"}
        )
    if action == "set":
        doc_type = params.get("doc_type")
        template_body = params.get("template_body")
        if not doc_type or not template_body:
            return {"error": "doc_type and template_body are required for set"}
        item = put_template(
            tenant_id=tenant_id,
            doc_type=doc_type,
            user_id=params.get("user_id", "shared"),
            template_body=template_body,
            display_name=params.get("display_name", ""),
        )
        return {"action": "set", "template": item}
    if action == "delete":
        doc_type = params.get("doc_type")
        if not doc_type:
            return {"error": "doc_type is required for delete"}
        ok = delete_template(
            tenant_id, doc_type, user_id=params.get("user_id", "shared")
        )
        return {"action": "delete", "deleted": ok, "doc_type": doc_type}
    if action == "resolve":
        doc_type = params.get("doc_type")
        if not doc_type:
            return {"error": "doc_type is required for resolve"}
        body, source, metadata = resolve_template(
            tenant_id, doc_type, user_id=params.get("user_id", "shared")
        )
        return {
            "action": "resolve",
            "doc_type": doc_type,
            "resolved_body": body,
            "source": source,
            "metadata": metadata,
        }
    return {
        "error": f"Unknown action: {action}. Valid: list, get, set, delete, resolve"
    }
