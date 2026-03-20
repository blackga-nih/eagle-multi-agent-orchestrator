"""
EAGLE Strands Service Tools

All 14 service @tool functions with proper named parameters,
plus KB tools and progressive disclosure tools.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any

from strands import Agent, tool

from .model import shared_model
from .package_state import emit_package_state
from .prompt_utils import (
    DOC_TYPE_LABELS,
    extract_context_data_from_prompt,
    extract_document_context_from_prompt,
    infer_doc_type_from_prompt,
)
from .registry import (
    PLUGIN_DIR,
    SKILL_AGENT_REGISTRY,
    load_plugin_config,
    truncate_skill,
)
from .telemetry import build_trace_attrs, ensure_langfuse_exporter

logger = logging.getLogger("eagle.strands_agent")

# Add server/ to path for eagle_skill_constants
_server_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)

from eagle_skill_constants import AGENTS, PLUGIN_CONTENTS, SKILLS


def _emit_tool_result(
    tool_name: str,
    result_str: str,
    result_queue: asyncio.Queue | None,
    loop: asyncio.AbstractEventLoop | None,
) -> None:
    """Emit a tool_result event to the frontend via result_queue."""
    if not result_queue or not loop:
        return
    try:
        parsed = json.loads(result_str) if isinstance(result_str, str) else result_str
    except (json.JSONDecodeError, TypeError):
        parsed = {"raw": result_str[:2000]} if result_str else {}
    # Truncate large text fields to avoid SSE bloat
    if isinstance(parsed, dict):
        for key in ("content", "text", "body"):
            val = parsed.get(key)
            if isinstance(val, str) and len(val) > 2000:
                parsed = {**parsed, key: val[:2000] + "..."}
                break
    loop.call_soon_threadsafe(
        result_queue.put_nowait,
        {"type": "tool_result", "name": tool_name, "result": parsed},
    )


# -- Progressive Disclosure @tools ------------------------------------


def make_list_skills_tool(
    result_queue: asyncio.Queue | None = None,
    loop: asyncio.AbstractEventLoop | None = None,
):
    """Create the list_skills tool for progressive disclosure."""

    @tool(name="list_skills")
    def list_skills_tool(category: str = "") -> str:
        """List available skills, agents, and data files with descriptions and triggers. Use this to discover what capabilities and reference data are available before diving deeper.

        Args:
            category: Filter by category: "skills", "agents", "data", or "" for all
        """
        result: dict[str, Any] = {}

        if category in ("", "skills"):
            skills_list = []
            for name, entry in SKILLS.items():
                skills_list.append(
                    {
                        "name": name,
                        "description": entry.get("description", ""),
                        "triggers": entry.get("triggers", []),
                    }
                )
            result["skills"] = skills_list

        if category in ("", "agents"):
            agents_list = []
            for name, entry in AGENTS.items():
                if name == "supervisor":
                    continue
                agents_list.append(
                    {
                        "name": name,
                        "description": entry.get("description", ""),
                        "triggers": entry.get("triggers", []),
                    }
                )
            result["agents"] = agents_list

        if category in ("", "data"):
            config = load_plugin_config()
            data_index = config.get("data", {})
            data_list = []
            if isinstance(data_index, dict):
                for name, meta in data_index.items():
                    data_list.append(
                        {
                            "name": name,
                            "description": meta.get("description", ""),
                            "sections": meta.get("sections", []),
                        }
                    )
            result["data"] = data_list

        out = json.dumps(result, indent=2)
        _emit_tool_result("list_skills", out, result_queue, loop)
        return out

    return list_skills_tool


def make_load_skill_tool(
    result_queue: asyncio.Queue | None = None,
    loop: asyncio.AbstractEventLoop | None = None,
):
    """Create the load_skill tool for progressive disclosure."""

    @tool(name="load_skill")
    def load_skill_tool(name: str) -> str:
        """Load full skill or agent instructions by name. Returns the complete SKILL.md or agent.md content so you can follow the workflow yourself without spawning a subagent. Use this when you need to understand a skill's detailed procedures, decision trees, or templates.

        Args:
            name: Skill or agent name (e.g. "oa-intake", "legal-counsel", "compliance")
        """
        entry = PLUGIN_CONTENTS.get(name)
        if not entry:
            available = sorted(PLUGIN_CONTENTS.keys())
            out = json.dumps(
                {
                    "error": f"No skill or agent named '{name}'",
                    "available": available,
                }
            )
        else:
            out = entry["body"]
        _emit_tool_result("load_skill", out, result_queue, loop)
        return out

    return load_skill_tool


def make_load_data_tool(
    result_queue: asyncio.Queue | None = None,
    loop: asyncio.AbstractEventLoop | None = None,
):
    """Create the load_data tool for progressive disclosure."""

    @tool(name="load_data")
    def load_data_tool(name: str, section: str = "") -> str:
        """Load reference data from the eagle-plugin data directory. Use this to access thresholds, contract types, document requirements, approval chains, contract vehicles, and other acquisition reference data on demand.

        Args:
            name: Data file name (e.g. "matrix", "thresholds", "contract-vehicles")
            section: Optional top-level key to extract (e.g. "thresholds", "doc_rules", "approval_chains", "contract_types"). Omit to get the full file.
        """
        config = load_plugin_config()
        data_index = config.get("data", {})

        # Handle legacy array format: convert ["far-database.json", ...] → dict
        if isinstance(data_index, list):
            data_index = {
                f.replace(".json", ""): {"file": f"data/{f}"}
                for f in data_index
                if isinstance(f, str)
            }

        meta = data_index.get(name)
        if not meta:
            out = json.dumps(
                {
                    "error": f"No data file named '{name}'",
                    "available": sorted(data_index.keys()),
                }
            )
            _emit_tool_result("load_data", out, result_queue, loop)
            return out

        file_rel = meta.get("file", f"data/{name}.json")
        file_path = os.path.join(PLUGIN_DIR, file_rel)

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            out = json.dumps({"error": f"Data file not found: {file_rel}"})
            _emit_tool_result("load_data", out, result_queue, loop)
            return out
        except json.JSONDecodeError as exc:
            out = json.dumps({"error": f"Invalid JSON in {file_rel}: {str(exc)}"})
            _emit_tool_result("load_data", out, result_queue, loop)
            return out

        if section:
            value = data.get(section)
            if value is None:
                out = json.dumps(
                    {
                        "error": f"Section '{section}' not found in '{name}'",
                        "available_sections": list(data.keys()),
                    }
                )
                _emit_tool_result("load_data", out, result_queue, loop)
                return out
            out = json.dumps({section: value}, indent=2, default=str)
            _emit_tool_result("load_data", out, result_queue, loop)
            return out

        out = json.dumps(data, indent=2, default=str)
        _emit_tool_result("load_data", out, result_queue, loop)
        return out

    return load_data_tool


# -- KB Service Tools --------------------------------------------------


def build_kb_service_tools(
    tenant_id: str,
    user_id: str,
    session_id: str | None,
    result_queue: asyncio.Queue | None = None,
    loop: asyncio.AbstractEventLoop | None = None,
) -> list:
    """Build KB tools with proper named parameters so Bedrock models send structured args."""
    from ..tools.strands_tools import exec_search_far
    from ..tools.knowledge_tools import exec_knowledge_fetch, exec_knowledge_search

    def _emit(name: str, result: dict) -> None:
        if result_queue and loop:
            truncated_result = (
                {
                    k: (v[:3000] + "..." if isinstance(v, str) and len(v) > 3000 else v)
                    for k, v in result.items()
                }
                if isinstance(result, dict)
                else result
            )
            loop.call_soon_threadsafe(
                result_queue.put_nowait,
                {"type": "tool_result", "name": name, "result": truncated_result},
            )

    @tool(name="search_far")
    def search_far(query: str, parts: list[str] | None = None) -> str:
        """Search FAR/DFARS for clauses, requirements, and guidance. Returns s3_keys for full document retrieval — ALWAYS call knowledge_fetch on returned s3_keys before responding.

        Args:
            query: Search query — topic, clause number, or keyword
            parts: Optional list of FAR part numbers to filter (e.g. ["6", "16"])
        """
        result = exec_search_far({"query": query, "parts": parts}, tenant_id)
        _emit("search_far", result)
        return json.dumps(result, indent=2, default=str)

    @tool(name="knowledge_search")
    def knowledge_search(
        query: str = "",
        topic: str = "",
        document_type: str = "",
        agent: str = "",
        authority_level: str = "",
        keywords: list[str] | None = None,
        limit: int = 10,
    ) -> str:
        """Search the acquisition knowledge base metadata in DynamoDB. Use 'query' for specific identifiers like case numbers, citations, or keywords. Use 'topic' for broad subject searches.

        Args:
            query: Search query — case numbers, citations, identifiers, or keywords
            topic: Broad topic filter (e.g. "competition", "small business")
            document_type: Filter by document type
            agent: Filter by agent/specialist
            authority_level: Filter by authority level
            keywords: List of keyword filters
            limit: Maximum results to return (default 10)
        """
        params = {
            k: v
            for k, v in {
                "query": query,
                "topic": topic,
                "document_type": document_type,
                "agent": agent,
                "authority_level": authority_level,
                "keywords": keywords,
                "limit": limit,
            }.items()
            if v
        }
        result = exec_knowledge_search(params, tenant_id, session_id)
        _emit("knowledge_search", result)
        return json.dumps(result, indent=2, default=str)

    @tool(name="knowledge_fetch")
    def knowledge_fetch(s3_key: str) -> str:
        """Fetch full knowledge document content from S3. REQUIRES an s3_key from a prior knowledge_search or search_far result.

        Args:
            s3_key: S3 key path from a knowledge_search or search_far result
        """
        result = exec_knowledge_fetch({"s3_key": s3_key}, tenant_id, session_id)
        _emit("knowledge_fetch", result)
        return json.dumps(result, indent=2, default=str)

    return [search_far, knowledge_search, knowledge_fetch]


# -- Subagent KB Tools (for subagents) ---------------------------------


def build_subagent_kb_tools(tenant_id: str, session_id: str) -> list:
    """Build knowledge-base tools that subagents can use to ground analysis.

    Gives subagents access to knowledge_search, knowledge_fetch, and search_far
    so they can retrieve actual documents instead of relying solely on
    parametric knowledge.
    """
    from ..tools.strands_tools import exec_search_far
    from ..tools.knowledge_tools import exec_knowledge_fetch, exec_knowledge_search

    @tool(name="knowledge_search")
    def kb_search(
        query: str = "",
        topic: str = "",
        document_type: str = "",
        agent: str = "",
        authority_level: str = "",
        keywords: list[str] | None = None,
        limit: int = 10,
    ) -> str:
        """Search the acquisition knowledge base for relevant documents, templates, and guidance. Use 'query' for specific identifiers like case numbers or citations. Use 'topic' for broad subject searches.

        Args:
            query: Search query — case numbers, citations, identifiers, or keywords
            topic: Broad topic filter (e.g. "competition", "small business")
            document_type: Filter by document type
            agent: Filter by agent/specialist
            authority_level: Filter by authority level
            keywords: List of keyword filters
            limit: Maximum results to return (default 10)
        """
        params = {
            k: v
            for k, v in {
                "query": query,
                "topic": topic,
                "document_type": document_type,
                "agent": agent,
                "authority_level": authority_level,
                "keywords": keywords,
                "limit": limit,
            }.items()
            if v
        }
        result = exec_knowledge_search(params, tenant_id, session_id)
        return json.dumps(result, indent=2, default=str)

    @tool(name="knowledge_fetch")
    def kb_fetch(s3_key: str) -> str:
        """Fetch full document content from the knowledge base by s3_key. REQUIRES an s3_key from a prior knowledge_search or search_far result.

        Args:
            s3_key: S3 key path from a knowledge_search or search_far result
        """
        result = exec_knowledge_fetch({"s3_key": s3_key}, tenant_id, session_id)
        return json.dumps(result, indent=2, default=str)

    @tool(name="search_far")
    def far_search(query: str, parts: list[str] | None = None) -> str:
        """Search FAR/DFARS for clauses, requirements, and guidance. Returns s3_keys for full documents — ALWAYS call knowledge_fetch on returned s3_keys before responding.

        Args:
            query: Search query — topic, clause number, or keyword
            parts: Optional list of FAR part numbers to filter (e.g. ["6", "16"])
        """
        result = exec_search_far({"query": query, "parts": parts}, tenant_id)
        return json.dumps(result, indent=2, default=str)

    return [kb_search, kb_fetch, far_search]


# -- Subagent Tool Factory ---------------------------------------------


def make_subagent_tool(
    skill_name: str,
    description: str,
    prompt_body: str,
    result_queue: asyncio.Queue | None = None,
    loop: asyncio.AbstractEventLoop | None = None,
    tenant_id: str = "",
    user_id: str = "",
    tier: str = "",
    session_id: str = "",
):
    """Create a @tool-wrapped subagent from skill registry entry.

    Each invocation constructs a fresh Agent with the resolved prompt.
    The shared model is reused (no per-request boto3 overhead).
    Subagents receive knowledge_search, knowledge_fetch, and search_far
    tools so they can ground analysis in actual documents.
    """
    safe_name = skill_name.replace("-", "_")

    @tool(name=safe_name)
    def subagent_tool(query: str) -> str:
        """Placeholder docstring replaced below."""
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S UTC")
        subagent_context = (
            f"Tenant: {tenant_id} | User: {user_id} | Tier: {tier} | Current datetime: {now_utc}\n"
            f"You are the {skill_name} specialist.\n\n"
        )
        ensure_langfuse_exporter()

        # Give subagents KB tools so they can retrieve actual documents
        kb_tools = build_subagent_kb_tools(tenant_id, session_id)

        agent = Agent(
            model=shared_model,
            system_prompt=subagent_context + prompt_body,
            tools=kb_tools,
            callback_handler=None,
            trace_attributes=build_trace_attrs(
                tenant_id=tenant_id,
                user_id=user_id,
                tier=tier,
                session_id=session_id,
                subagent=safe_name,
            ),
        )
        raw = str(agent(query))

        # Emit tool_result so the frontend can show the specialist's report
        if result_queue and loop:
            truncated = raw[:3000] + "..." if len(raw) > 3000 else raw
            loop.call_soon_threadsafe(
                result_queue.put_nowait,
                {"type": "tool_result", "name": safe_name, "result": {"report": truncated}},
            )

        return raw

    # Override docstring (required for Strands schema extraction)
    subagent_tool.__doc__ = (
        f"{description}\n\n" f"Args:\n" f"    query: The question or task for this specialist"
    )
    return subagent_tool


# -- All Service @tools ------------------------------------------------


def build_all_service_tools(
    tenant_id: str,
    user_id: str,
    session_id: str | None,
    prompt_context: str | None = None,
    package_context: Any = None,
    result_queue: asyncio.Queue | None = None,
    loop: asyncio.AbstractEventLoop | None = None,
) -> list:
    """Build 14 service @tool functions with proper named parameters."""
    from ..tools.strands_tools import get_tool_dispatch
    from ..compliance_matrix import execute_operation
    tool_dispatch = get_tool_dispatch()

    # Compute scoped session id once for per-user S3 scoping
    scoped_session_id = session_id
    if not scoped_session_id or "#" not in scoped_session_id:
        scoped_session_id = f"{tenant_id}#advanced#{user_id}#{session_id or ''}"

    def _emit(name: str, result) -> None:
        """Emit tool_result to frontend, truncating large text fields for non-document tools."""
        if not result_queue or not loop:
            return
        emit_result = result
        if name != "create_document" and isinstance(result, dict):
            text_val = result.get("content") or result.get("text") or result.get("result")
            if isinstance(text_val, str) and len(text_val) > 2000:
                emit_result = {**result}
                key = "content" if "content" in result else "text" if "text" in result else "result"
                emit_result[key] = text_val[:2000] + "..."
        loop.call_soon_threadsafe(
            result_queue.put_nowait,
            {"type": "tool_result", "name": name, "result": emit_result},
        )

    # ---- 1. s3_document_ops ----
    @tool(name="s3_document_ops")
    def s3_document_ops_tool(
        operation: str, bucket: str = "", key: str = "", content: str = ""
    ) -> str:
        """Read, write, or list documents in S3 scoped per-tenant. Operations: list, read, write.

        Args:
            operation: S3 operation — 'list', 'read', or 'write'
            bucket: S3 bucket name (defaults to tenant bucket)
            key: S3 object key path
            content: Content to write (for 'write' operation)
        """
        parsed = {"operation": operation, "bucket": bucket, "key": key, "content": content}
        try:
            result = tool_dispatch["s3_document_ops"](parsed, tenant_id, scoped_session_id)
            _emit("s3_document_ops", result)
            return json.dumps(result, indent=2, default=str)
        except Exception as exc:
            logger.error("Service tool s3_document_ops failed: %s", exc, exc_info=True)
            return json.dumps({"error": str(exc), "tool": "s3_document_ops"})

    # ---- 2. dynamodb_intake ----
    @tool(name="dynamodb_intake")
    def dynamodb_intake_tool(
        operation: str, table: str = "eagle", item_id: str = "", data: dict | None = None
    ) -> str:
        """Create, read, update, list, or query intake records in DynamoDB. Operations: create, read, update, list, query.

        Args:
            operation: DynamoDB operation — 'create', 'read', 'update', 'list', or 'query'
            table: DynamoDB table name (default 'eagle')
            item_id: Item identifier for read/update operations
            data: Data payload for create/update operations
        """
        parsed = {"operation": operation, "table": table, "item_id": item_id, "data": data or {}}
        try:
            result = tool_dispatch["dynamodb_intake"](parsed, tenant_id)
            _emit("dynamodb_intake", result)
            return json.dumps(result, indent=2, default=str)
        except Exception as exc:
            logger.error("Service tool dynamodb_intake failed: %s", exc, exc_info=True)
            return json.dumps({"error": str(exc), "tool": "dynamodb_intake"})

    # ---- 3. create_document (special prompt-context enrichment) ----
    @tool(name="create_document")
    def create_document_tool(
        doc_type: str,
        title: str = "",
        content: str = "",
        data: dict | None = None,
        package_id: str = "",
        output_format: str = "",
        update_existing_key: str = "",
        template_id: str = "",
    ) -> str:
        """Generate acquisition documents (SOW, IGCE, Market Research, J&A, Acquisition Plan, Eval Criteria, Security Checklist, Section 508, COR Certification, Contract Type Justification). Documents are saved to S3.

        Args:
            doc_type: Document type (sow, igce, market_research, justification, acquisition_plan, eval_criteria, security_checklist, section_508, cor_certification, contract_type_justification)
            title: Descriptive document title that includes the program or acquisition name — e.g. "SOW - Cloud Computing Services for NCI Research Portal" or "IGCE - IT Support Services FY2026". Never use a generic label like "Statement of Work" alone.
            content: Full document content in markdown with filled-in sections
            data: Structured data fields (description, estimated_value, period_of_performance, etc.)
            package_id: Acquisition package ID to associate document with
            output_format: Output format override
            update_existing_key: S3 key of existing document to update/revise
            template_id: Template ID to use for generation
        """
        parsed = {
            "doc_type": doc_type,
            "title": title,
            "content": content,
            "data": data,
            "package_id": package_id,
            "output_format": output_format,
            "update_existing_key": update_existing_key,
            "template_id": template_id,
        }
        try:
            # -- Prompt-context enrichment --
            prompt_doc_ctx = extract_document_context_from_prompt(prompt_context or "")

            dt = str(parsed.get("doc_type", "")).strip().lower()
            if not dt:
                dt = (
                    prompt_doc_ctx.get("document_type")
                    or infer_doc_type_from_prompt(prompt_context or "")
                    or ""
                )
                if dt:
                    parsed["doc_type"] = dt

            t = str(parsed.get("title", "")).strip()
            if not t:
                inferred_title = (
                    prompt_doc_ctx.get("title")
                    or DOC_TYPE_LABELS.get(dt or "", "")
                    or "Untitled Acquisition"
                )
                parsed["title"] = inferred_title

            prompt_data = extract_context_data_from_prompt(prompt_context or "", dt)
            existing_data = parsed.get("data")
            if not isinstance(existing_data, dict):
                existing_data = {}
            if prompt_data:
                for k, v in prompt_data.items():
                    existing_data.setdefault(k, v)
            current_content = prompt_doc_ctx.get("current_content")
            if current_content:
                existing_data.setdefault("current_content", current_content)
            user_request = prompt_doc_ctx.get("user_request")
            if user_request:
                existing_data.setdefault("edit_request", user_request)
            if existing_data:
                parsed["data"] = existing_data

            # Package context injection
            if (
                package_context is not None
                and getattr(package_context, "is_package_mode", False)
                and getattr(package_context, "package_id", None)
            ):
                parsed.setdefault("package_id", package_context.package_id)

            # Auto-detect existing document
            _pkg_id = parsed.get("package_id")
            _dt = parsed.get("doc_type", "").strip().lower()
            _upd_key = parsed.get("update_existing_key", "").strip()
            if _pkg_id and _dt and not _upd_key:
                try:
                    existing = tool_dispatch["get_latest_document"](
                        {"package_id": _pkg_id, "doc_type": _dt},
                        tenant_id,
                    )
                    existing_s3_key = (existing.get("document") or {}).get("s3_key", "")
                    if existing_s3_key:
                        parsed["update_existing_key"] = existing_s3_key
                        logger.info(
                            "create_document: existing %s found in package %s — routing to update (%s)",
                            _dt,
                            _pkg_id,
                            existing_s3_key,
                        )
                except Exception:
                    pass  # No existing doc or lookup failed — create new

            result = tool_dispatch["create_document"](parsed, tenant_id, scoped_session_id)
            _emit("create_document", result)

            if result_queue and loop and isinstance(result, dict):
                emit_package_state(result, "create_document", tenant_id, result_queue, loop)

            return json.dumps(result, indent=2, default=str)
        except Exception as exc:
            logger.error("Service tool create_document failed: %s", exc, exc_info=True)
            return json.dumps({"error": str(exc), "tool": "create_document"})

    # ---- 4. edit_docx_document ----
    @tool(name="edit_docx_document")
    def edit_docx_document_tool(
        document_key: str,
        edits: list | None = None,
        checkbox_edits: list | None = None,
    ) -> str:
        """Apply targeted edits to an existing DOCX document. Use for text replacements or checkbox toggles.

        Args:
            document_key: S3 key of the DOCX document to edit
            edits: List of edit objects, each with 'search_text' and 'replacement_text'
            checkbox_edits: List of checkbox edit objects, each with 'label_text' and 'checked' (bool)
        """
        parsed = {
            "document_key": document_key,
            "edits": edits or [],
            "checkbox_edits": checkbox_edits or [],
        }
        try:
            result = tool_dispatch["edit_docx_document"](parsed, tenant_id, scoped_session_id)
            _emit("edit_docx_document", result)
            return json.dumps(result, indent=2, default=str)
        except Exception as exc:
            logger.error("Service tool edit_docx_document failed: %s", exc, exc_info=True)
            return json.dumps({"error": str(exc), "tool": "edit_docx_document"})

    # ---- 5. get_intake_status ----
    @tool(name="get_intake_status")
    def get_intake_status_tool(intake_id: str = "") -> str:
        """Get current intake package status and completeness — shows which documents exist, which are missing, and next actions.

        Args:
            intake_id: Optional intake ID to check status for
        """
        parsed = {"intake_id": intake_id}
        try:
            result = tool_dispatch["get_intake_status"](parsed, tenant_id, scoped_session_id)
            _emit("get_intake_status", result)
            return json.dumps(result, indent=2, default=str)
        except Exception as exc:
            logger.error("Service tool get_intake_status failed: %s", exc, exc_info=True)
            return json.dumps({"error": str(exc), "tool": "get_intake_status"})

    # ---- 6. intake_workflow ----
    @tool(name="intake_workflow")
    def intake_workflow_tool(action: str, intake_id: str = "", data: dict | None = None) -> str:
        """Manage the acquisition intake workflow: start, advance, status, complete, reset.

        Args:
            action: Workflow action — 'start', 'advance', 'status', 'complete', or 'reset'
            intake_id: Intake ID to act on
            data: Additional data for the action
        """
        parsed = {"action": action, "intake_id": intake_id, "data": data or {}}
        try:
            result = tool_dispatch["intake_workflow"](parsed, tenant_id)
            _emit("intake_workflow", result)
            return json.dumps(result, indent=2, default=str)
        except Exception as exc:
            logger.error("Service tool intake_workflow failed: %s", exc, exc_info=True)
            return json.dumps({"error": str(exc), "tool": "intake_workflow"})

    # ---- 7. manage_skills ----
    @tool(name="manage_skills")
    def manage_skills_tool(
        action: str = "list",
        skill_id: str = "",
        name: str = "",
        display_name: str = "",
        description: str = "",
        prompt_body: str = "",
        triggers: list | None = None,
        tools_list: list | None = None,
        model: str = "",
        visibility: str = "private",
    ) -> str:
        """Create, list, update, delete, or publish custom skills. Actions: list, get, create, update, delete, submit, publish, disable.

        Args:
            action: Skill action — 'list', 'get', 'create', 'update', 'delete', 'submit', 'publish', 'disable'
            skill_id: Skill identifier for get/update/delete
            name: Skill name for create
            display_name: Human-readable display name
            description: Skill description
            prompt_body: Skill prompt content
            triggers: List of trigger phrases
            tools_list: List of tool names the skill can use
            model: Model override for the skill
            visibility: Skill visibility — 'private' or 'shared'
        """
        parsed = {
            "action": action,
            "skill_id": skill_id,
            "name": name,
            "display_name": display_name,
            "description": description,
            "prompt_body": prompt_body,
            "triggers": triggers or [],
            "tools": tools_list or [],
            "model": model,
            "visibility": visibility,
        }
        try:
            result = tool_dispatch["manage_skills"](parsed, tenant_id)
            _emit("manage_skills", result)
            return json.dumps(result, indent=2, default=str)
        except Exception as exc:
            logger.error("Service tool manage_skills failed: %s", exc, exc_info=True)
            return json.dumps({"error": str(exc), "tool": "manage_skills"})

    # ---- 8. manage_prompts ----
    @tool(name="manage_prompts")
    def manage_prompts_tool(
        action: str = "list",
        agent_name: str = "",
        prompt_body: str = "",
        is_append: bool = False,
    ) -> str:
        """List, view, set, or delete agent prompt overrides. Actions: list, get, set, delete, resolve.

        Args:
            action: Prompt action — 'list', 'get', 'set', 'delete', 'resolve'
            agent_name: Agent name to manage prompts for
            prompt_body: Prompt content for set action
            is_append: Whether to append to existing prompt (default false)
        """
        parsed = {
            "action": action,
            "agent_name": agent_name,
            "prompt_body": prompt_body,
            "is_append": is_append,
        }
        try:
            result = tool_dispatch["manage_prompts"](parsed, tenant_id)
            _emit("manage_prompts", result)
            return json.dumps(result, indent=2, default=str)
        except Exception as exc:
            logger.error("Service tool manage_prompts failed: %s", exc, exc_info=True)
            return json.dumps({"error": str(exc), "tool": "manage_prompts"})

    # ---- 9. manage_templates ----
    @tool(name="manage_templates")
    def manage_templates_tool(
        action: str = "list",
        doc_type: str = "",
        template_body: str = "",
        display_name: str = "",
        scope: str = "shared",
    ) -> str:
        """List, view, set, or delete document templates. Actions: list, get, set, delete, resolve.

        Args:
            action: Template action — 'list', 'get', 'set', 'delete', 'resolve'
            doc_type: Document type for the template
            template_body: Template content for set action
            display_name: Human-readable template name
            scope: Template scope — 'shared' or user-specific identifier
        """
        parsed = {
            "action": action,
            "doc_type": doc_type,
            "template_body": template_body,
            "display_name": display_name,
            "user_id": scope,
        }
        try:
            result = tool_dispatch["manage_templates"](parsed, tenant_id)
            _emit("manage_templates", result)
            return json.dumps(result, indent=2, default=str)
        except Exception as exc:
            logger.error("Service tool manage_templates failed: %s", exc, exc_info=True)
            return json.dumps({"error": str(exc), "tool": "manage_templates"})

    # ---- 10. document_changelog_search ----
    @tool(name="document_changelog_search")
    def document_changelog_search_tool(package_id: str, doc_type: str = "", limit: int = 20) -> str:
        """Search changelog history for a document or package.

        Args:
            package_id: Acquisition package ID (required)
            doc_type: Optional document type filter
            limit: Maximum results to return (default 20)
        """
        parsed = {"package_id": package_id, "doc_type": doc_type, "limit": limit}
        try:
            result = tool_dispatch["document_changelog_search"](parsed, tenant_id)
            _emit("document_changelog_search", result)
            return json.dumps(result, indent=2, default=str)
        except Exception as exc:
            logger.error("Service tool document_changelog_search failed: %s", exc, exc_info=True)
            return json.dumps({"error": str(exc), "tool": "document_changelog_search"})

    # ---- 11. get_latest_document ----
    @tool(name="get_latest_document")
    def get_latest_document_tool(package_id: str, doc_type: str) -> str:
        """Get latest document version with recent changelog entries.

        Args:
            package_id: Acquisition package ID (required)
            doc_type: Document type (required)
        """
        parsed = {"package_id": package_id, "doc_type": doc_type}
        try:
            result = tool_dispatch["get_latest_document"](parsed, tenant_id)
            _emit("get_latest_document", result)
            return json.dumps(result, indent=2, default=str)
        except Exception as exc:
            logger.error("Service tool get_latest_document failed: %s", exc, exc_info=True)
            return json.dumps({"error": str(exc), "tool": "get_latest_document"})

    # ---- 12. finalize_package (emits package state) ----
    @tool(name="finalize_package")
    def finalize_package_tool(package_id: str, auto_submit: bool = False) -> str:
        """Validate acquisition package completeness — checks for missing documents, draft-status docs, unfilled template markers, and compliance warnings.

        Args:
            package_id: Acquisition package ID (required)
            auto_submit: Whether to auto-submit if validation passes (default false)
        """
        parsed = {"package_id": package_id, "auto_submit": auto_submit}
        try:
            result = tool_dispatch["finalize_package"](parsed, tenant_id)
            _emit("finalize_package", result)
            if result_queue and loop and isinstance(result, dict):
                emit_package_state(result, "finalize_package", tenant_id, result_queue, loop)
            return json.dumps(result, indent=2, default=str)
        except Exception as exc:
            logger.error("Service tool finalize_package failed: %s", exc, exc_info=True)
            return json.dumps({"error": str(exc), "tool": "finalize_package"})

    # ---- 13. cloudwatch_logs ----
    @tool(name="cloudwatch_logs")
    def cloudwatch_logs_tool(
        operation: str = "recent",
        log_group: str = "/eagle/app",
        filter_pattern: str = "",
        start_time: str = "",
        end_time: str = "",
        limit: int = 50,
    ) -> str:
        """Query CloudWatch Logs for application monitoring. Operations: recent, search, filter.

        Args:
            operation: Log operation — 'recent', 'search', or 'filter'
            log_group: CloudWatch log group path (default '/eagle/app')
            filter_pattern: CloudWatch filter pattern expression
            start_time: Start time — ISO 8601 or relative like '-1h', '-30m'
            end_time: End time — ISO 8601 or relative
            limit: Maximum log entries to return (default 50)
        """
        parsed = {
            "operation": operation,
            "log_group": log_group,
            "filter_pattern": filter_pattern,
            "start_time": start_time,
            "end_time": end_time,
            "limit": limit,
            "user_id": user_id,
        }
        try:
            result = tool_dispatch["cloudwatch_logs"](parsed, tenant_id)
            _emit("cloudwatch_logs", result)
            return json.dumps(result, indent=2, default=str)
        except Exception as exc:
            logger.error("Service tool cloudwatch_logs failed: %s", exc, exc_info=True)
            return json.dumps({"error": str(exc), "tool": "cloudwatch_logs"})

    # ---- 14. query_compliance_matrix ----
    @tool(name="query_compliance_matrix")
    def query_compliance_matrix_tool(
        operation: str,
        contract_value: float = 0,
        acquisition_method: str = "",
        contract_type: str = "",
        is_it: bool = False,
        is_small_business: bool = False,
        is_rd: bool = False,
        is_human_subjects: bool = False,
        is_services: bool = True,
        keyword: str = "",
    ) -> str:
        """Query NCI/NIH contract requirements decision tree. Operations: query, list_methods, list_types, list_thresholds, search_far, suggest_vehicle.

        Args:
            operation: Matrix operation — 'query', 'list_methods', 'list_types', 'list_thresholds', 'search_far', 'suggest_vehicle'
            contract_value: Contract dollar value
            acquisition_method: Acquisition method code (e.g. 'sap', 'sealed_bidding')
            contract_type: Contract type code (e.g. 'ffp', 'cpff')
            is_it: Whether this is an IT acquisition
            is_small_business: Whether small business set-aside applies
            is_rd: Whether this is R&D
            is_human_subjects: Whether human subjects are involved
            is_services: Whether this is a services contract (default true)
            keyword: Keyword search term
        """
        parsed = {
            "operation": operation,
            "contract_value": contract_value,
            "acquisition_method": acquisition_method,
            "contract_type": contract_type,
            "is_it": is_it,
            "is_small_business": is_small_business,
            "is_rd": is_rd,
            "is_human_subjects": is_human_subjects,
            "is_services": is_services,
            "keyword": keyword,
        }
        try:
            result = execute_operation(parsed)
            out = json.dumps(result, indent=2, default=str)
            _emit(
                "query_compliance_matrix",
                result if isinstance(result, dict) else {"result": result},
            )
            return out
        except Exception as exc:
            logger.error("Service tool query_compliance_matrix failed: %s", exc, exc_info=True)
            return json.dumps({"error": str(exc), "tool": "query_compliance_matrix"})

    return [
        s3_document_ops_tool,
        dynamodb_intake_tool,
        create_document_tool,
        edit_docx_document_tool,
        get_intake_status_tool,
        intake_workflow_tool,
        manage_skills_tool,
        manage_prompts_tool,
        manage_templates_tool,
        document_changelog_search_tool,
        get_latest_document_tool,
        finalize_package_tool,
        cloudwatch_logs_tool,
        query_compliance_matrix_tool,
    ]


def build_service_tools(
    tenant_id: str,
    user_id: str,
    session_id: str | None,
    prompt_context: str | None = None,
    package_context: Any = None,
    result_queue: asyncio.Queue | None = None,
    loop: asyncio.AbstractEventLoop | None = None,
) -> list:
    """Build @tool wrappers for AWS service tools, scoped to the current tenant/user/session."""
    tools = build_all_service_tools(
        tenant_id,
        user_id,
        session_id,
        prompt_context=prompt_context,
        package_context=package_context,
        result_queue=result_queue,
        loop=loop,
    )
    # Add KB tools with proper named parameters
    tools.extend(build_kb_service_tools(tenant_id, user_id, session_id, result_queue, loop))
    # Add progressive disclosure tools
    tools.append(make_list_skills_tool(result_queue, loop))
    tools.append(make_load_skill_tool(result_queue, loop))
    tools.append(make_load_data_tool(result_queue, loop))
    return tools


# -- build_skill_tools() -----------------------------------------------


def build_skill_tools(
    tier: str = "advanced",
    skill_names: list[str] | None = None,
    tenant_id: str = "demo-tenant",
    user_id: str = "demo-user",
    workspace_id: str | None = None,
    session_id: str = "",
    result_queue: asyncio.Queue | None = None,
    loop: asyncio.AbstractEventLoop | None = None,
) -> list:
    """Build @tool-wrapped subagent functions from skill registry.

    Same 4-layer prompt resolution as sdk_agentic_service.build_skill_agents():
      1. Workspace override (wspc_store)
      2. DynamoDB PLUGIN# canonical (plugin_store)
      3. Bundled eagle-plugin/ files (PLUGIN_CONTENTS)
      4. Tenant custom SKILL# items (skill_store)

    Returns:
        List of @tool-decorated functions suitable for Agent(tools=[...])
    """
    tools = []

    for name, meta in SKILL_AGENT_REGISTRY.items():
        if skill_names and name not in skill_names:
            continue

        # Resolve prompt through workspace chain when workspace_id is available
        prompt_body = ""
        if workspace_id:
            try:
                from ..workspace_override_store import resolve_skill

                prompt_body, _source = resolve_skill(tenant_id, user_id, workspace_id, name)
            except Exception as exc:
                logger.warning(
                    "workspace_override_store.resolve_skill failed for %s: %s -- using bundled",
                    name,
                    exc,
                )
                prompt_body = ""

        # Fall back to bundled PLUGIN_CONTENTS
        if not prompt_body:
            entry = PLUGIN_CONTENTS.get(meta["skill_key"])
            if not entry:
                logger.warning(
                    "Plugin content not found for %s (key=%s)", name, meta["skill_key"]
                )
                continue
            prompt_body = entry["body"]

        tools.append(
            make_subagent_tool(
                skill_name=name,
                description=meta["description"],
                prompt_body=truncate_skill(prompt_body),
                result_queue=result_queue,
                loop=loop,
                tenant_id=tenant_id,
                user_id=user_id,
                tier=tier,
                session_id=session_id,
            )
        )

    # Merge active user-created SKILL# items
    try:
        from ..skill_store import list_active_skills

        user_skills = list_active_skills(tenant_id)
        for skill in user_skills:
            name = skill.get("name", "")
            if not name:
                continue
            if skill_names and name not in skill_names:
                continue
            skill_prompt = skill.get("prompt_body", "")
            if not skill_prompt:
                continue
            tools.append(
                make_subagent_tool(
                    skill_name=name,
                    description=skill.get("description", f"{name} specialist"),
                    prompt_body=truncate_skill(skill_prompt),
                    result_queue=result_queue,
                    loop=loop,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    tier=tier,
                    session_id=session_id,
                )
            )
    except Exception as exc:
        logger.warning(
            "skill_store.list_active_skills failed for %s: %s -- skipping user skills",
            tenant_id,
            exc,
        )

    return tools
