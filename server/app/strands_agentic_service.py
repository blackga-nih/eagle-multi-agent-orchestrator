"""
EAGLE - Strands-Based Agentic Service with Skill->Subagent Orchestration

Drop-in replacement for sdk_agentic_service.py. Same function signatures,
Strands Agents SDK under the hood instead of Claude Agent SDK.

Architecture:
  Supervisor (Agent + @tool subagents)
    |- oa-intake (@tool -> Agent, fresh per-call)
    |- legal-counsel (@tool -> Agent, fresh per-call)
    |- market-intelligence (@tool -> Agent, fresh per-call)
    |- tech-translator (@tool -> Agent, fresh per-call)
    |- public-interest (@tool -> Agent, fresh per-call)
    +- document-generator (@tool -> Agent, fresh per-call)

Key differences from sdk_agentic_service.py:
  - No subprocess — Strands runs in-process via boto3 converse
  - No credential bridging — boto3 handles SSO/IAM natively
  - AgentDefinition -> @tool-wrapped Agent()
  - ClaudeAgentOptions -> Agent() constructor
  - query() async generator -> agent() sync call + adapter yield
"""

import asyncio
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator

import boto3

from botocore.config import Config
from strands import Agent, tool
from strands.agent.conversation_manager import SummarizingConversationManager
from strands.hooks import HookProvider
from strands.hooks.events import (
    AfterInvocationEvent,
    AfterModelCallEvent,
    AfterToolCallEvent,
    BeforeToolCallEvent,
)
from strands.models import BedrockModel

# Add server/ to path for eagle_skill_constants
_server_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)

from eagle_skill_constants import AGENTS, SKILLS, PLUGIN_CONTENTS
from .eagle_state import normalize, apply_event, to_trace_attrs, stamp
from .tools.knowledge_tools import KNOWLEDGE_FETCH_TOOL, KNOWLEDGE_SEARCH_TOOL
from .tools.contract_matrix import query_contract_matrix

logger = logging.getLogger("eagle.strands_agent")


# -- Langfuse OTEL exporter (lazy, one-shot) --------------------------
_langfuse_injected = False


def _ensure_langfuse_exporter():
    """Initialize Strands telemetry + Langfuse OTLP exporter (once).

    Must be called **before** the first ``Agent()`` so that the Agent's cached
    tracer references the real SDKTracerProvider (with the Langfuse exporter).

    Flow:
      1. ``StrandsTelemetry()`` creates a real SDKTracerProvider and sets it global.
      2. We add a BatchSpanProcessor(OTLPSpanExporter) to that provider.
      3. When ``Agent()`` later calls ``get_tracer()``, it picks up this provider.
    """
    global _langfuse_injected
    if _langfuse_injected:
        return
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    if not public_key or not secret_key:
        return
    try:
        import base64
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from strands.telemetry import StrandsTelemetry

        # Ensure a real SDKTracerProvider is the global provider
        st = StrandsTelemetry()
        provider = st.tracer_provider

        base = os.getenv(
            "LANGFUSE_OTEL_ENDPOINT",
            "https://us.cloud.langfuse.com/api/public/otel",
        )
        endpoint = f"{base.rstrip('/')}/v1/traces"
        auth = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()

        exporter = OTLPSpanExporter(
            endpoint=endpoint,
            headers={"Authorization": f"Basic {auth}"},
        )
        # SimpleSpanProcessor exports immediately (no batching) — ensures
        # traces reach Langfuse even if the process restarts via --reload.
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        _langfuse_injected = True
        logger.info("[EAGLE] Langfuse OTEL exporter injected → %s", endpoint)
        # Suppress non-fatal OTEL context detach warnings from Strands sync→async bridge
        logging.getLogger("opentelemetry.context").setLevel(logging.CRITICAL)
    except Exception as exc:
        logger.warning("[EAGLE] Langfuse exporter injection failed: %s", exc)


# -- EagleSSEHookProvider --------------------------------------------
# Registers AfterInvocationEvent to flush agent state to DynamoDB
# after every supervisor turn.

class EagleSSEHookProvider(HookProvider):
    """Hook provider that flushes agent state to DynamoDB after each turn.

    Accepts tenant_id/user_id/session_id so state is persisted under the
    correct DynamoDB PK/SK. Parameters default so existing call sites that
    don't pass them still work (state flush is simply skipped).
    """

    def __init__(
        self,
        tenant_id: str = "default",
        user_id: str = "anonymous",
        session_id: str | None = None,
    ):
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.session_id = session_id
        # Tracks whether update_state was called in the current model cycle.
        # Reset to False by _on_after_model_call after each end_turn.
        self._update_state_called_this_turn: bool = False
        # Last known state snapshot for computing per-tool deltas.
        self._last_state_snapshot: dict = {}

    def register_hooks(self, registry) -> None:
        registry.add_callback(BeforeToolCallEvent, self._on_before_tool_call)
        registry.add_callback(AfterToolCallEvent, self._on_after_tool_call)
        registry.add_callback(AfterModelCallEvent, self._on_after_model_call)
        registry.add_callback(AfterInvocationEvent, self._on_after_invocation)

    def _on_before_tool_call(self, event: BeforeToolCallEvent) -> None:
        """Emit tool.started telemetry and validate doc generation calls."""
        try:
            tool_use = getattr(event, "tool_use", None) or {}
            tool_name = tool_use.get("name", "") if isinstance(tool_use, dict) else getattr(tool_use, "name", "")
            tool_use_id = tool_use.get("toolUseId", "") if isinstance(tool_use, dict) else getattr(tool_use, "toolUseId", "")
            raw_input = tool_use.get("input", {}) if isinstance(tool_use, dict) else getattr(tool_use, "input", {})

            # Emit tool.started to CloudWatch for every tool call.
            # This makes all tool invocations — including update_state —
            # visible in CloudWatch Insights with their full input params.
            # When extended thinking is enabled, the preceding assistant
            # message (which contains reasoning blocks) is already captured
            # in the Langfuse OTEL span for the supervisor trace.
            try:
                from .telemetry.cloudwatch_emitter import emit_tool_started
                emit_tool_started(
                    tenant_id=self.tenant_id,
                    user_id=self.user_id,
                    session_id=self.session_id or "",
                    tool_name=tool_name,
                    tool_input=raw_input,
                    tool_use_id=tool_use_id,
                )
            except Exception:
                pass

            # Track when update_state is called so AfterModelCallEvent can verify it
            # was called before the final end_turn synthesis response.
            if tool_name == "update_state":
                self._update_state_called_this_turn = True

            # Doc gating only applies to create_document / generate_document
            if tool_name not in ("create_document", "generate_document"):
                return

            # Extract doc_type from tool params
            raw_input = tool_use.get("input", {}) if isinstance(tool_use, dict) else getattr(tool_use, "input", {})
            if isinstance(raw_input, str):
                try:
                    raw_input = json.loads(raw_input)
                except (json.JSONDecodeError, TypeError):
                    return
            doc_type = raw_input.get("doc_type", "") if isinstance(raw_input, dict) else ""
            if not doc_type:
                return

            # Get agent state — requires package context to validate
            agent_state = getattr(getattr(event, "agent", None), "state", None)
            if not agent_state or not isinstance(agent_state, dict):
                return

            package_id = agent_state.get("package_id")
            if not package_id:
                return  # Not in package mode — skip validation

            # Load package for acquisition details
            try:
                from .stores.package_store import get_package
                pkg = get_package(self.tenant_id, package_id)
                if not pkg:
                    return
            except Exception:
                return  # Package load failed — fail open

            # Map package acquisition_pathway to contract matrix method
            pathway = pkg.get("acquisition_pathway", "simplified")
            _PATHWAY_TO_METHOD = {
                "micro_purchase": "micro",
                "simplified": "sap",
                "full_competition": "negotiated",
                "sole_source": "sole",
            }
            method = _PATHWAY_TO_METHOD.get(pathway, "sap")

            try:
                value = int(float(str(pkg.get("estimated_value", 0))))
            except (ValueError, TypeError):
                value = 0

            from .hooks.document_gate import validate_document_request
            result = validate_document_request(
                doc_type=doc_type,
                acquisition_method=method,
                contract_type=pkg.get("contract_type", "ffp"),
                dollar_value=value,
                is_it=bool(pkg.get("is_it", False)),
                is_services=bool(pkg.get("is_services", True)),
                is_small_business=bool(pkg.get("is_small_business", False)),
            )

            if result.action == "block":
                required_list = ", ".join(result.required_docs) if result.required_docs else "none"
                event.cancel_tool = (
                    f"BLOCKED: {result.reason}\n"
                    f"FAR Reference: {result.far_citation}\n"
                    f"Required documents for this acquisition: {required_list}"
                )
                try:
                    new_state = apply_event(agent_state, "compliance_alert", {
                        "severity": "critical",
                        "items": [{"name": f"Blocked: {doc_type}", "note": result.reason}],
                    })
                    agent_state.update(new_state)
                except Exception:
                    pass
                try:
                    from .telemetry.cloudwatch_emitter import emit_document_validation
                    emit_document_validation(
                        tenant_id=self.tenant_id,
                        session_id=self.session_id or "",
                        user_id=self.user_id,
                        doc_type=doc_type,
                        action="block",
                        reason=result.reason,
                    )
                except Exception:
                    pass

            elif result.action == "warn":
                try:
                    new_state = apply_event(agent_state, "compliance_alert", {
                        "severity": "warning",
                        "items": [{"name": f"Optional: {doc_type}", "note": result.reason}],
                    })
                    agent_state.update(new_state)
                except Exception:
                    pass
                try:
                    from .telemetry.cloudwatch_emitter import emit_document_validation
                    emit_document_validation(
                        tenant_id=self.tenant_id,
                        session_id=self.session_id or "",
                        user_id=self.user_id,
                        doc_type=doc_type,
                        action="warn",
                        reason=result.reason,
                    )
                except Exception:
                    pass

        except Exception as exc:
            logger.debug("_on_before_tool_call: non-fatal error: %s", exc)

    def _on_after_tool_call(self, event: AfterToolCallEvent) -> None:
        """Capture state delta after every tool call and emit tool.completed telemetry.

        Reads the live agent state from invocation_state, computes a delta against
        the previous snapshot, and emits a tool.completed CloudWatch event with:
          - tool_name, tool_use_id, success
          - state_delta: {field: {before, after}} for changed state fields
        """
        try:
            tool_use = getattr(event, "tool_use", None) or {}
            tool_name = tool_use.get("name", "") if isinstance(tool_use, dict) else getattr(tool_use, "name", "")
            tool_use_id = tool_use.get("toolUseId", "") if isinstance(tool_use, dict) else getattr(tool_use, "toolUseId", "")

            # Read live supervisor state from invocation_state.
            # invocation_state["agent"] is the Agent instance.
            # Agent.state is an AgentState whose underlying dict is ._state.
            invocation_state = getattr(event, "invocation_state", {}) or {}
            agent_obj = invocation_state.get("agent_state", invocation_state.get("agent"))
            raw_state: dict = {}
            if agent_obj is not None:
                agent_state_obj = getattr(agent_obj, "state", agent_obj)
                # AgentState wraps the dict in ._state; fall back to __dict__ or direct
                if hasattr(agent_state_obj, "_state") and isinstance(agent_state_obj._state, dict):
                    raw_state = agent_state_obj._state
                elif isinstance(agent_state_obj, dict):
                    raw_state = agent_state_obj
            current = normalize(raw_state) if raw_state else {}

            # Compute delta vs previous snapshot (only tracked fields)
            prev = self._last_state_snapshot
            _TRACKED = ("phase", "required_documents", "completed_documents", "turn_count", "package_id")
            delta = {
                k: {"before": prev.get(k), "after": current.get(k)}
                for k in _TRACKED
                if prev.get(k) != current.get(k)
            }
            self._last_state_snapshot = dict(current)

            logger.debug(
                "eagle.tool_completed tool=%s session=%s delta_keys=%s success=%s",
                tool_name, self.session_id, list(delta.keys()), event.exception is None,
            )

            try:
                from .telemetry.cloudwatch_emitter import emit_tool_completed
                emit_tool_completed(
                    tenant_id=self.tenant_id,
                    user_id=self.user_id,
                    session_id=self.session_id or "",
                    tool_name=tool_name,
                    tool_use_id=tool_use_id,
                    state_delta=delta,
                    success=event.exception is None,
                )
            except Exception:
                pass
        except Exception as exc:
            logger.debug("_on_after_tool_call: non-fatal error: %s", exc)

    def _on_after_model_call(self, event: AfterModelCallEvent) -> None:
        """Detect when the model gives a final response without calling update_state.

        Fires after every LLM call. When stop_reason is 'end_turn' (model is about
        to return the final text response with no further tool calls), checks whether
        update_state was called during this invocation cycle. Emits a warning to
        CloudWatch if not, then resets the tracking flag for the next cycle.
        """
        try:
            sr = getattr(event, "stop_response", None)
            if not sr:
                return
            stop_reason = getattr(sr, "stop_reason", None)
            # stop_reason is a StopReason enum or string
            sr_str = str(stop_reason).lower() if stop_reason else ""
            if "end_turn" not in sr_str:
                return

            if not self._update_state_called_this_turn:
                logger.info(
                    "eagle.state_not_updated_before_final_response session=%s "
                    "(update_state was not called before end_turn — prompt may need updating)",
                    self.session_id,
                )
                try:
                    from .telemetry.cloudwatch_emitter import emit_warning
                    emit_warning(
                        tenant_id=self.tenant_id,
                        session_id=self.session_id or "",
                        user_id=self.user_id,
                        message="update_state not called before final response",
                    )
                except Exception:
                    pass
            else:
                logger.debug(
                    "eagle.state_updated_before_final_response session=%s ✓",
                    self.session_id,
                )

            # Reset for next model cycle
            self._update_state_called_this_turn = False
        except Exception as exc:
            logger.debug("_on_after_model_call: non-fatal error: %s", exc)

    def _on_after_invocation(self, event: AfterInvocationEvent) -> None:
        """Flush agent state to DynamoDB and CloudWatch after every supervisor turn."""
        if not self.session_id:
            return
        try:
            # event.agent.state is the live dict on the Agent instance
            raw_state = getattr(getattr(event, "agent", None), "state", None)
            if not raw_state or not isinstance(raw_state, dict):
                return

            state = normalize(raw_state)
            state["turn_count"] = state.get("turn_count", 0) + 1
            state = stamp(state)

            from .stores.session_store import save_agent_state
            save_agent_state(
                session_id=self.session_id,
                state=state,
                tenant_id=self.tenant_id,
                user_id=self.user_id,
            )
            logger.debug(
                "eagle.state_flushed session=%s phase=%s docs=%d/%d turn=%d",
                self.session_id,
                state.get("phase"),
                len(state.get("completed_documents", [])),
                len(state.get("required_documents", [])),
                state.get("turn_count"),
            )
            try:
                from .telemetry.cloudwatch_emitter import emit_agent_state_flush
                emit_agent_state_flush(
                    tenant_id=self.tenant_id,
                    session_id=self.session_id,
                    user_id=self.user_id,
                    state=state,
                )
            except Exception as cw_exc:
                logger.debug("CloudWatch state flush failed (non-fatal): %s", cw_exc)
        except Exception as exc:
            logger.warning("State flush failed (non-fatal): %s", exc)


# -- Adapter Messages ------------------------------------------------
# These match the interface expected by streaming_routes.py and main.py:
#   type(msg).__name__ == "AssistantMessage" | "ResultMessage"
#   AssistantMessage.content[].type, .text, .name, .input
#   ResultMessage.result, .usage


@dataclass
class TextBlock:
    """Adapter for text content blocks."""
    type: str = "text"
    text: str = ""


@dataclass
class ToolUseBlock:
    """Adapter for tool_use content blocks (subagent delegation info)."""
    type: str = "tool_use"
    name: str = ""
    input: dict = field(default_factory=dict)


@dataclass
class AssistantMessage:
    """Adapter matching Claude SDK AssistantMessage interface."""
    content: list = field(default_factory=list)


@dataclass
class ResultMessage:
    """Adapter matching Claude SDK ResultMessage interface."""
    result: str = ""
    usage: dict = field(default_factory=dict)


# -- Model Selection -------------------------------------------------
# If EAGLE_BEDROCK_MODEL_ID is explicitly set, use it.
# Otherwise, default to Sonnet 4.6 on the NCI account (695681773636)
# and Haiku 4.5 on any other account (personal dev, CI, etc.).

_NCI_ACCOUNT = "695681773636"
_SONNET = "us.anthropic.claude-sonnet-4-6"
_HAIKU = "us.anthropic.claude-haiku-4-5-20251001-v1:0"


def _default_model() -> str:
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


# -- Shared Model (module-level) -------------------------------------
# Created once at import time. Reused across all requests.
# boto3 handles SSO/IAM natively — no credential bridging needed.

_bedrock_client_config = Config(
    connect_timeout=int(os.getenv("EAGLE_BEDROCK_CONNECT_TIMEOUT", "60")),
    read_timeout=int(os.getenv("EAGLE_BEDROCK_READ_TIMEOUT", "300")),
    retries={
        "max_attempts": int(os.getenv("EAGLE_BEDROCK_MAX_ATTEMPTS", "4")),
        "mode": os.getenv("EAGLE_BEDROCK_RETRY_MODE", "adaptive"),
    },
    tcp_keepalive=True,
)

# -- Model factory (lazy singleton) ------------------------------------------
# Built on first use so EAGLE_EXTENDED_THINKING / EAGLE_BEDROCK_MODEL_ID are
# read after .env is loaded (important for eval runner and local dev).
# Extended thinking requires temperature=1 (Bedrock requirement) and a model
# that supports it (Claude claude-haiku-4-5 / Sonnet 4.x+).

_model: "BedrockModel | None" = None


def _get_model() -> "BedrockModel":
    """Return the shared BedrockModel, building it on first call."""
    global _model
    if _model is not None:
        return _model

    model_id = os.getenv("EAGLE_BEDROCK_MODEL_ID") or MODEL
    extended = os.getenv("EAGLE_EXTENDED_THINKING", "0").lower() in ("1", "true", "yes")
    budget = int(os.getenv("EAGLE_THINKING_BUDGET_TOKENS", "8000"))

    kwargs: dict = dict(
        model_id=model_id,
        region_name=os.getenv("AWS_REGION", "us-east-1"),
        boto_client_config=_bedrock_client_config,
    )
    if extended:
        kwargs["additional_request_fields"] = {
            "thinking": {"type": "enabled", "budget_tokens": budget}
        }
        kwargs["temperature"] = 1.0
        logger.info("EAGLE extended thinking ENABLED (model=%s, budget=%d)", model_id, budget)
    else:
        logger.info("EAGLE model: %s (thinking off)", model_id)

    _model = BedrockModel(**kwargs)
    return _model

# Tier-gated tool access (preserved from sdk_agentic_service.py)
# Note: Strands subagents don't use CLI tools like Read/Glob/Grep.
# These are kept for compatibility; in Strands, tool access is managed
# via the @tool functions registered on the Agent.
TIER_TOOLS = {
    "basic": [],
    "advanced": ["Read", "Glob", "Grep", "workspace_memory", "web_search", "think"],
    "premium": ["Read", "Glob", "Grep", "Bash", "workspace_memory", "web_search", "browse_url", "code_execute", "think"],
}

TIER_BUDGETS = {
    "basic": 0.10,
    "advanced": 0.25,
    "premium": 0.75,
}

# Fast-path document generation for explicit "generate document" requests.
# This avoids long multi-tool loops for straightforward document creation asks.
_DOC_TYPE_HINTS: list[tuple[str, list[str]]] = [
    ("sow", ["statement of work", " sow"]),
    ("igce", ["igce", "independent government cost estimate", "cost estimate"]),
    ("market_research", ["market research"]),
    ("acquisition_plan", ["acquisition plan"]),
    ("justification", ["justification", "j&a", "j and a", "sole source"]),
    ("eval_criteria", ["evaluation criteria", "eval criteria"]),
    ("security_checklist", ["security checklist"]),
    ("section_508", ["section 508", "508 compliance"]),
    ("cor_certification", ["cor certification"]),
    ("contract_type_justification", ["contract type justification"]),
]
_DOC_TYPE_LABELS: dict[str, str] = {
    "sow": "Statement of Work",
    "igce": "Independent Government Cost Estimate",
    "market_research": "Market Research",
    "acquisition_plan": "Acquisition Plan",
    "justification": "Justification & Approval",
    "eval_criteria": "Evaluation Criteria",
    "security_checklist": "Security Checklist",
    "section_508": "Section 508 Compliance",
    "cor_certification": "COR Certification",
    "contract_type_justification": "Contract Type Justification",
}
_DIRECT_DOC_VERBS = ("generate", "draft", "create", "write", "produce")
_DOC_EDIT_VERBS = ("edit", "update", "revise", "modify", "fill", "rewrite", "adjust", "amend")
_SLOW_PATH_HINTS = ("research", "far", "dfars", "policy", "compare", "analyze")
_DOC_REQUEST_BLOCKERS = (
    "what is",
    "what's",
    "how do i",
    "how to",
    "explain",
    "difference between",
)

_PROMPT_SECTION_ALIASES = {
    "project description": "project_description",
    "technical requirements": "technical_requirements",
    "scope of work": "scope_of_work",
    "deliverables": "deliverables",
    "environment tiers": "environment_tiers",
    "security": "security",
}


def _normalize_prompt(prompt: str) -> str:
    return re.sub(r"\s+", " ", prompt.strip().lower())


def _extract_user_request_from_prompt(prompt: str) -> str:
    """Extract the [USER REQUEST] block from document-viewer prompts."""
    if not prompt:
        return ""
    marker = "[USER REQUEST]"
    if marker not in prompt:
        return ""

    tail = prompt.split(marker, 1)[1]
    for stop in ("\n[", "\nInstruction:"):
        idx = tail.find(stop)
        if idx >= 0:
            tail = tail[:idx]
            break
    return tail.strip()


def _extract_document_context_from_prompt(prompt: str) -> dict[str, str]:
    """Extract document viewer context blocks from wrapped prompts."""
    if not prompt:
        return {}

    out: dict[str, str] = {}

    title_match = re.search(r"(?im)^\s*Title:\s*(.+?)\s*$", prompt)
    if title_match:
        out["title"] = title_match.group(1).strip()

    type_match = re.search(r"(?im)^\s*Type:\s*([a-z0-9_ -]+)\s*$", prompt)
    if type_match:
        out["document_type"] = type_match.group(1).strip().lower().replace(" ", "_")

    excerpt_match = re.search(
        r"(?is)Current Content Excerpt:\s*(.+?)(?:\n\s*\[ORIGIN SESSION CONTEXT\]|\n\s*\[USER REQUEST\]|$)",
        prompt,
    )
    if excerpt_match:
        out["current_content"] = excerpt_match.group(1).strip()

    user_request = _extract_user_request_from_prompt(prompt)
    if user_request:
        out["user_request"] = user_request

    return out


def _infer_doc_type_from_prompt(prompt: str) -> str | None:
    lowered = f" {_normalize_prompt(prompt)} "
    for doc_type, hints in _DOC_TYPE_HINTS:
        if any(hint in lowered for hint in hints):
            return doc_type
    return None


def _is_document_generation_request(prompt: str) -> tuple[bool, str | None]:
    lowered = _normalize_prompt(prompt)
    doc_type = _infer_doc_type_from_prompt(prompt)
    if not doc_type:
        return False, None
    if any(lowered.startswith(blocker) for blocker in _DOC_REQUEST_BLOCKERS):
        return False, None
    if any(v in lowered for v in _DIRECT_DOC_VERBS):
        return True, doc_type

    # Document-viewer prompts include explicit wrappers; treat edit verbs in
    # [USER REQUEST] as document generation intent.
    if "[document context]" in lowered and "[user request]" in lowered:
        user_req = _extract_user_request_from_prompt(prompt).lower()
        if any(v in user_req for v in _DIRECT_DOC_VERBS) or any(v in user_req for v in _DOC_EDIT_VERBS):
            return True, doc_type

    phrase = _DOC_TYPE_LABELS.get(doc_type, doc_type.replace("_", " ")).lower()
    if lowered.startswith(phrase):
        return True, doc_type
    if re.search(rf"\b(need|want|please)\b.*\b{re.escape(phrase)}\b", lowered):
        return True, doc_type

    return False, None


def _should_use_fast_document_path(prompt: str) -> tuple[bool, str | None]:
    should_generate, doc_type = _is_document_generation_request(prompt)
    if not should_generate or not doc_type:
        return False, None

    lowered = _normalize_prompt(prompt)
    if "[document context]" in lowered:
        return False, None
    if any(h in lowered for h in _SLOW_PATH_HINTS):
        return False, None
    return True, doc_type


def _extract_prompt_sections(prompt: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: str | None = None

    for raw_line in (prompt or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        heading = line.rstrip(":").strip().lower()
        if heading in _PROMPT_SECTION_ALIASES:
            current = _PROMPT_SECTION_ALIASES[heading]
            sections.setdefault(current, [])
            continue

        if line.startswith("- ") or line.startswith("* "):
            item = line[2:].strip().strip('"')
            if not item:
                continue
            bucket = current or "general"
            sections.setdefault(bucket, []).append(item)

    return sections


def _extract_context_data_from_prompt(prompt: str, doc_type: str) -> dict[str, Any]:
    """Derive create_document data fields from the current user prompt."""
    if not prompt:
        return {}

    data: dict[str, Any] = {}
    doc_ctx = _extract_document_context_from_prompt(prompt)
    if doc_ctx.get("current_content"):
        data["current_content"] = doc_ctx["current_content"]
    if doc_ctx.get("user_request"):
        data["edit_request"] = doc_ctx["user_request"]

    sections = _extract_prompt_sections(prompt)

    project_description = " ".join(sections.get("project_description", [])).strip()
    if project_description:
        data["description"] = project_description[:500]
        data["requirement"] = project_description[:500]
    else:
        user_req = _extract_user_request_from_prompt(prompt)
        if user_req:
            data["description"] = user_req[:500]
            data["requirement"] = user_req[:500]

    scope_items = sections.get("scope_of_work", [])
    tech_items = sections.get("technical_requirements", [])
    if doc_type == "sow":
        tasks = (scope_items + tech_items)[:20]
        if tasks:
            data["tasks"] = tasks
        if sections.get("deliverables"):
            data["deliverables"] = sections["deliverables"][:15]
        if sections.get("security"):
            data["security_requirements"] = "; ".join(sections["security"])[:600]
        if sections.get("environment_tiers"):
            data["place_of_performance"] = "; ".join(sections["environment_tiers"])[:300]
        if scope_items:
            data["scope"] = " ".join(scope_items)[:500]

    # Common budget/timeline extraction (best effort)
    m_money = re.search(r"\$[0-9][0-9,]*(?:\.[0-9]+)?", prompt)
    if m_money:
        money = m_money.group(0)
        data.setdefault("estimated_cost", money)
        data.setdefault("estimated_value", money)
        data.setdefault("total_estimate", money)

    m_period = re.search(r"\b\d+\s*(?:month|months|year|years)\b(?:[^.,;\n]{0,40})", prompt, flags=re.IGNORECASE)
    if m_period:
        period = m_period.group(0).strip()
        data.setdefault("period_of_performance", period)
        data.setdefault("timeline", period)

    return data


def _fast_path_title(prompt: str, doc_type: str) -> str:
    return _DOC_TYPE_LABELS.get(doc_type, doc_type.replace("_", " ").title())


# -- Trivial greeting fast-path (no LLM call needed) --------------------

_TRIVIAL_RE = re.compile(
    r"^(?:h(?:i|ello|ey|owdy)|yo|sup|good\s*(?:morning|afternoon|evening)"
    r"|thanks?(?:\s*you)?|ok(?:ay)?|sure|bye|goodbye|see\s*ya"
    r"|how\s*are\s*you|what'?s?\s*up|hey\s*there)[\s!?.]*$",
    re.IGNORECASE,
)

_INTAKE_FORM_RE = re.compile(r'^\s*\{.*"form_type"\s*:\s*"baseline_intake".*\}\s*$', re.DOTALL)
_INTAKE_RESPONSE = "Thanks for your submission."

_GREETING_RESPONSES = [
    "Hey! What are you working on today?",
    "Hi there! What can I help you with?",
    "Hey! Got an acquisition question or need to start something?",
]


def _fast_trivial_response(prompt: str) -> dict | None:
    """Return a canned response for trivial greetings, skipping the LLM entirely."""
    if not _TRIVIAL_RE.match(prompt.strip()):
        return None
    import random
    return {
        "text": random.choice(_GREETING_RESPONSES),
        "usage": {"fast_path": True, "trivial": True},
    }


def _fast_intake_form_response(prompt: str) -> dict | None:
    """Return a canned response for baseline intake form submissions."""
    stripped = prompt.strip()
    if not _INTAKE_FORM_RE.match(stripped):
        return None
    # Parse and log the submission (session context storage is handled on next turn)
    try:
        payload = json.loads(stripped)
        logger.info("Intake form submitted: form_type=%s, questions=%d",
                     payload.get("form_type"), len(payload.get("answers", {})))
    except (json.JSONDecodeError, TypeError):
        pass
    return {
        "text": _INTAKE_RESPONSE,
        "usage": {"fast_path": True, "intake_form": True},
    }


def _build_scoped_session_id(
    tenant_id: str,
    user_id: str,
    session_id: str | None,
) -> str:
    if session_id and "#" in session_id:
        return session_id
    return f"{tenant_id}#advanced#{user_id}#{session_id or ''}"


async def _maybe_fast_path_document_generation(
    prompt: str,
    tenant_id: str,
    user_id: str,
    session_id: str | None,
    package_context: Any = None,
) -> dict | None:
    should_fast_path, doc_type = _should_use_fast_document_path(prompt)
    if not should_fast_path or not doc_type:
        return None

    from .tool_dispatch import _exec_create_document

    doc_ctx = _extract_document_context_from_prompt(prompt)
    params: dict[str, Any] = {
        "doc_type": doc_type,
        "title": doc_ctx.get("title") or _fast_path_title(prompt, doc_type),
    }
    contextual_data = _extract_context_data_from_prompt(prompt, doc_type)
    if contextual_data:
        params["data"] = contextual_data
    if (
        package_context is not None
        and getattr(package_context, "is_package_mode", False)
        and getattr(package_context, "package_id", None)
    ):
        params["package_id"] = package_context.package_id

    scoped_session_id = _build_scoped_session_id(tenant_id, user_id, session_id)
    result = await asyncio.to_thread(
        _exec_create_document,
        params,
        tenant_id,
        scoped_session_id,
    )
    return {
        "doc_type": doc_type,
        "result": result,
    }


async def _ensure_create_document_for_direct_request(
    prompt: str,
    tenant_id: str,
    user_id: str,
    session_id: str | None,
    package_context: Any,
    tools_called: list[str],
) -> dict | None:
    """Force a create_document call for direct doc requests that missed the tool.

    This reconciles cases where the model produced inline draft content without
    invoking create_document, which breaks document-card/editing UX.
    """
    should_generate, doc_type = _is_document_generation_request(prompt)
    if not should_generate or not doc_type or "create_document" in tools_called or "generate_document" in tools_called:
        return None

    from .tool_dispatch import _exec_create_document

    doc_ctx = _extract_document_context_from_prompt(prompt)
    params: dict[str, Any] = {
        "doc_type": doc_type,
        "title": doc_ctx.get("title") or _fast_path_title(prompt, doc_type),
    }
    contextual_data = _extract_context_data_from_prompt(prompt, doc_type)
    if contextual_data:
        params["data"] = contextual_data
    if (
        package_context is not None
        and getattr(package_context, "is_package_mode", False)
        and getattr(package_context, "package_id", None)
    ):
        params["package_id"] = package_context.package_id

    scoped_session_id = _build_scoped_session_id(tenant_id, user_id, session_id)
    result = await asyncio.to_thread(
        _exec_create_document,
        params,
        tenant_id,
        scoped_session_id,
    )
    if isinstance(result, dict) and result.get("error"):
        logger.warning(
            "Forced create_document failed for prompt='%s': %s",
            prompt[:160],
            result.get("error"),
        )
        return None

    return {
        "doc_type": doc_type,
        "result": result,
    }

# -- Tool Schemas (for health/status endpoints) -------------------------
# These are the Anthropic tool_use format schemas used by main.py and
# streaming_routes.py to report available tools. They do NOT drive the
# Strands agent (which uses @tool functions).
EAGLE_TOOLS = [
    {
        "name": "s3_document_ops",
        "description": (
            "Read, write, or list documents stored in S3. All documents are "
            "scoped per-tenant. Use this to manage acquisition documents, "
            "templates, and generated files."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["list", "read", "write"],
                    "description": "Operation to perform: list files, read a file, or write a file",
                },
                "bucket": {
                    "type": "string",
                    "description": "S3 bucket name (uses S3_BUCKET env var if not specified)",
                },
                "key": {
                    "type": "string",
                    "description": "S3 key/path for read or write operations",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write (for write operation)",
                },
            },
            "required": ["operation"],
        },
    },
    {
        "name": "dynamodb_intake",
        "description": (
            "Create, read, update, list, or query intake records in DynamoDB. "
            "All records are scoped per-tenant using PK/SK patterns. Use this "
            "to track acquisition intake packages."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["create", "read", "update", "list", "query"],
                    "description": "CRUD operation to perform",
                },
                "table": {
                    "type": "string",
                    "description": "DynamoDB table name (default: eagle)",
                },
                "item_id": {
                    "type": "string",
                    "description": "Unique item identifier for read/update",
                },
                "data": {
                    "type": "object",
                    "description": "Data fields for create/update operations",
                },
                "filter_expression": {
                    "type": "string",
                    "description": "Optional filter expression for queries",
                },
            },
            "required": ["operation"],
        },
    },
    {
        "name": "cloudwatch_logs",
        "description": (
            "Read CloudWatch logs filtered by user/session. Use this to inspect "
            "application logs, debug issues, or audit user activity. "
            "Pass user_id to scope results to a specific user."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["search", "recent", "get_stream"],
                    "description": "Log operation: search with filter, get recent events, or get a specific stream",
                },
                "log_group": {
                    "type": "string",
                    "description": "CloudWatch log group name (default: /eagle/app)",
                },
                "filter_pattern": {
                    "type": "string",
                    "description": "CloudWatch filter pattern for searching logs",
                },
                "user_id": {
                    "type": "string",
                    "description": "Filter logs to this specific user ID",
                },
                "start_time": {
                    "type": "string",
                    "description": "Start time for log search (ISO format or relative like '-1h')",
                },
                "end_time": {
                    "type": "string",
                    "description": "End time for log search (ISO format)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of log events to return (default: 50)",
                },
            },
            "required": ["operation"],
        },
    },
    # Progressive disclosure tools
    {
        "name": "list_skills",
        "description": (
            "List available skills, agents, and data files with descriptions and triggers. "
            "Use to discover capabilities before diving deeper."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["skills", "agents", "data", ""],
                    "description": "Filter: 'skills', 'agents', 'data', or '' for all",
                },
            },
        },
    },
    {
        "name": "load_skill",
        "description": (
            "Load full skill or agent instructions by name. Returns the complete "
            "SKILL.md or agent.md content for following workflows without spawning a subagent."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Skill or agent name (e.g. 'oa-intake', 'compliance')",
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "load_data",
        "description": (
            "Load reference data from the plugin data directory. Access thresholds, "
            "contract types, document requirements, approval chains, contract vehicles."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Data file name (e.g. 'matrix', 'thresholds', 'contract-vehicles')",
                },
                "section": {
                    "type": "string",
                    "description": "Optional section key (e.g. 'thresholds', 'doc_rules', 'approval_chains')",
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "search_far",
        "description": (
            "Search the Federal Acquisition Regulation (FAR) and Defense Federal "
            "Acquisition Regulation Supplement (DFARS) for relevant clauses, "
            "requirements, and guidance. Returns part numbers, sections, titles, "
            "full text summaries, and applicability notes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query — topic, clause number, or keyword",
                },
                "parts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific FAR part numbers to search (e.g. ['13', '15'])",
                },
            },
            "required": ["query"],
        },
    },
    KNOWLEDGE_SEARCH_TOOL,
    KNOWLEDGE_FETCH_TOOL,
    {
        "name": "generate_document",
        "description": (
            "Generate a complete acquisition document using AI-driven content. "
            "Pass only the document type — conversation context and templates are "
            "loaded automatically. The AI writes full prose using NCI templates as "
            "guidelines. Produces SOW, IGCE, Market Research, J&A, Acquisition Plan, "
            "Evaluation Criteria, Security Checklist, Section 508, COR Certification, "
            "or Contract Type Justification. Includes omission tracking and decision rationale."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "doc_type": {
                    "type": "string",
                    "enum": [
                        "sow", "igce", "market_research", "justification",
                        "acquisition_plan", "eval_criteria", "security_checklist",
                        "section_508", "cor_certification",
                        "contract_type_justification"
                    ],
                    "description": "Type of acquisition document to generate",
                },
                "special_instructions": {
                    "type": "string",
                    "description": "Optional user-specific guidance (e.g. 'emphasize security', 'use FFP contract type')",
                },
            },
            "required": ["doc_type"],
        },
    },
    {
        "name": "create_document",
        "description": (
            "Legacy document generator — use generate_document instead for AI-driven content. "
            "Kept for backward compatibility. Pass doc_type, title, and optional data fields."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "doc_type": {
                    "type": "string",
                    "enum": [
                        "sow", "igce", "market_research", "justification",
                        "acquisition_plan", "eval_criteria", "security_checklist",
                        "section_508", "cor_certification",
                        "contract_type_justification"
                    ],
                    "description": "Type of acquisition document to generate",
                },
                "title": {
                    "type": "string",
                    "description": "Title of the acquisition/document",
                },
                "data": {
                    "type": "object",
                    "description": "Document-specific fields (description, line_items, vendors, etc.)",
                },
            },
            "required": ["doc_type", "title"],
        },
    },
    {
        "name": "get_intake_status",
        "description": (
            "Get the current intake package status and completeness. Shows which "
            "documents exist, which are missing, and next actions needed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "intake_id": {
                    "type": "string",
                    "description": "Intake package ID (defaults to active intake if not provided)",
                },
            },
        },
    },
    {
        "name": "intake_workflow",
        "description": (
            "Manage the acquisition intake workflow. Use 'start' to begin a new intake, "
            "'advance' to move to the next stage, 'status' to see current stage and progress, "
            "or 'complete' to finish the intake. The workflow guides through: "
            "1) Requirements Gathering, 2) Compliance Check, 3) Document Generation, 4) Review & Submit."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["start", "advance", "status", "complete", "reset"],
                    "description": "Workflow action to perform",
                },
                "intake_id": {
                    "type": "string",
                    "description": "Intake ID (auto-generated on start, required for other actions)",
                },
                "data": {
                    "type": "object",
                    "description": "Stage-specific data to save (requirements, compliance results, etc.)",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "update_state",
        "description": (
            "Push a structured state update to the frontend UI via SSE. "
            "Used to send real-time checklist progress, phase changes, "
            "document-ready notifications, and compliance alerts."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "state_type": {
                    "type": "string",
                    "enum": ["checklist_update", "phase_change", "document_ready", "compliance_alert"],
                    "description": "Type of state update to push to the frontend",
                },
                "package_id": {
                    "type": "string",
                    "description": "Acquisition package ID — checklist is auto-fetched from DB",
                },
                "phase": {
                    "type": "string",
                    "description": "New phase name (for phase_change)",
                },
                "previous": {
                    "type": "string",
                    "description": "Previous phase name (for phase_change)",
                },
                "doc_type": {
                    "type": "string",
                    "description": "Document type (for document_ready)",
                },
                "version": {
                    "type": "integer",
                    "description": "Document version (for document_ready)",
                },
                "document_id": {
                    "type": "string",
                    "description": "Document ID (for document_ready)",
                },
                "severity": {
                    "type": "string",
                    "enum": ["info", "warning", "critical"],
                    "description": "Alert severity (for compliance_alert)",
                },
                "items": {
                    "type": "array",
                    "description": "Compliance finding items (for compliance_alert)",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "note": {"type": "string"},
                        },
                    },
                },
            },
            "required": ["state_type"],
        },
    },
    {
        "name": "get_package_checklist",
        "description": (
            "Fetch the current acquisition package checklist. Returns required, "
            "completed, and missing documents for the given package."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "package_id": {
                    "type": "string",
                    "description": "The acquisition package ID to fetch checklist for",
                },
            },
            "required": ["package_id"],
        },
    },
    {
        "name": "workspace_memory",
        "description": (
            "View and edit your persistent workspace files. Use to track ongoing "
            "work, key findings, and important context across sessions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "enum": ["view", "write", "append", "clear", "list", "search"],
                    "description": "Operation: view/write/append/clear a file, list all files, or search",
                },
                "path": {
                    "type": "string",
                    "description": "File path (e.g., _workspace.txt, _notes.txt)",
                },
                "content": {
                    "type": "string",
                    "description": "Content for write/append operations",
                },
            },
            "required": ["command", "path"],
        },
    },
    {
        "name": "web_search",
        "description": (
            "Search the web for current regulations, policy updates, news, "
            "and federal acquisition information."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query text",
                },
                "search_type": {
                    "type": "string",
                    "enum": ["web", "news", "gov"],
                    "description": "Type of search: web (general), news (recent), gov (federal documents)",
                },
                "count": {
                    "type": "integer",
                    "description": "Max results to return (default: 10, max: 20)",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "browse_url",
        "description": (
            "Fetch and analyze web pages, PDFs, or documents from URLs. "
            "Can process up to 10 URLs at once."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "urls": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 10,
                    "description": "URLs to fetch and extract content from",
                },
                "question": {
                    "type": "string",
                    "description": "Optional question to focus extraction on",
                },
            },
            "required": ["urls"],
        },
    },
    {
        "name": "code_execute",
        "description": (
            "Execute code in a managed sandbox for calculations, data analysis, "
            "IGCE cost modeling, and other computational tasks. "
            "Supports Python, JavaScript, and TypeScript."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Code to execute",
                },
                "language": {
                    "type": "string",
                    "enum": ["python", "javascript", "typescript"],
                    "description": "Programming language (default: python)",
                },
                "packages": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Packages to install before execution",
                },
            },
            "required": ["code"],
        },
    },
]

# Max prompt size per subagent to avoid context overflow
MAX_SKILL_PROMPT_CHARS = 4000


# -- Skill -> @tool Registry (built from plugin metadata) ------------

_PLUGIN_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "eagle-plugin"
)
_PLUGIN_JSON_PATH = os.path.join(_PLUGIN_DIR, "plugin.json")


def _load_plugin_config() -> dict:
    """Load plugin config, merging DynamoDB manifest with bundled plugin.json.

    The DynamoDB PLUGIN#manifest only stores version/agent_count/skill_count —
    it does NOT include the 'data' index needed by load_data(). Always load
    the bundled plugin.json as the base, then overlay any DynamoDB manifest
    fields on top.
    """
    # Always start from the bundled plugin.json (has 'data', 'capabilities', etc.)
    config: dict = {}
    try:
        with open(_PLUGIN_JSON_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    # Overlay DynamoDB manifest fields (version, agent_count, skill_count)
    try:
        from .plugin_store import get_plugin_manifest
        manifest = get_plugin_manifest()
        if manifest:
            config.update(manifest)
    except Exception:
        pass

    return config


def _build_registry() -> dict:
    """Build SKILL_AGENT_REGISTRY dynamically from AGENTS + SKILLS metadata.

    Uses plugin.json to determine which agents/skills are wired as subagents.
    The supervisor agent is excluded (it's the orchestrator, not a subagent).
    """
    config = _load_plugin_config()
    active_agents = set(config.get("agents", []))
    active_skills = set(config.get("skills", []))

    registry = {}

    for name, entry in AGENTS.items():
        if name == config.get("agent", "supervisor"):
            continue
        if active_agents and name not in active_agents:
            continue
        registry[name] = {
            "description": entry["description"],
            "skill_key": name,
            "tools": entry["tools"] if entry["tools"] else [],
            "model": entry["model"],
        }

    for name, entry in SKILLS.items():
        if active_skills and name not in active_skills:
            continue
        registry[name] = {
            "description": entry["description"],
            "skill_key": name,
            "tools": entry["tools"] if entry["tools"] else [],
            "model": entry["model"],
        }

    return registry


SKILL_AGENT_REGISTRY = _build_registry()


def _truncate_skill(content: str, max_chars: int = MAX_SKILL_PROMPT_CHARS) -> str:
    """Truncate skill content to fit within subagent context budget."""
    if len(content) <= max_chars:
        return content
    return content[:max_chars] + "\n\n[... truncated for context budget]"


# -- @tool Factory ---------------------------------------------------

def _make_subagent_tool(
    skill_name: str,
    description: str,
    prompt_body: str,
    result_queue: asyncio.Queue | None = None,
    loop: asyncio.AbstractEventLoop | None = None,
    tenant_id: str = "default",
    user_id: str = "anonymous",
    session_id: str | None = None,
    tier: str = "advanced",
    context_frame: dict | None = None,
):
    """Create a @tool-wrapped subagent from skill registry entry.

    Each invocation constructs a fresh Agent with the resolved prompt.
    The shared _model is reused (no per-request boto3 overhead).
    trace_attributes + session.id are forwarded so Langfuse groups
    the subagent span under the same session as the supervisor.

    context_frame is a shared mutable dict containing:
      - "state": the current eagle_state dict (populated after state load)
      - "completed": list of skill names that have already returned results
    At call time, a context header (~100 tokens) is prepended to the query
    so subagents know the acquisition phase, tier, and prior analyses.
    """
    safe_name = skill_name.replace("-", "_")
    _subagent_trace_attrs = {
        "eagle.tenant_id": tenant_id,
        "eagle.user_id": user_id,
        "eagle.tier": tier,
        "eagle.session_id": session_id or "",
        "eagle.subagent": safe_name,
        # Langfuse uses session.id to group all traces into one Session view
        "session.id": session_id or "",
    }

    @tool(name=safe_name)
    def subagent_tool(query: str) -> str:
        """Placeholder docstring replaced below."""
        # Build context header from shared frame (read at call time, not factory time)
        ctx = context_frame or {}
        state = ctx.get("state") or {}
        completed = ctx.get("completed") or []

        header_parts = [f"Tenant: {tenant_id} | User: {user_id} | Tier: {tier}"]
        if state.get("phase"):
            header_parts.append(f"Phase: {state['phase']}")
        if state.get("package_id"):
            header_parts.append(f"Package: {state['package_id']}")
        if state.get("required_documents"):
            header_parts.append(f"Required docs: {', '.join(state['required_documents'])}")
        if completed:
            header_parts.append(f"Prior analyses completed: {', '.join(completed)}")

        # Include prior specialist findings so document-generator sees actual research content
        summaries = state.get("specialist_summaries") or {}
        if summaries:
            header_parts.append("Specialist findings:")
            for _skill, _text in summaries.items():
                header_parts.append(f"  [{_skill}]: {str(_text)[:1500]}")

        context_header = "[ACQUISITION CONTEXT] " + " | ".join(header_parts)
        enriched_query = f"{context_header}\n\n{query}"

        agent = Agent(
            model=_get_model(),
            system_prompt=prompt_body,
            callback_handler=None,
            trace_attributes=_subagent_trace_attrs,
        )
        raw = str(agent(enriched_query))

        # Track this subagent as completed so subsequent subagents know what ran
        if context_frame is not None:
            context_frame.setdefault("completed", []).append(skill_name)
            # Store result in shared state so document-generator can use market findings
            # on same-turn AND cross-turn (persists via eagle_state to DynamoDB)
            context_frame["state"].setdefault("specialist_summaries", {})[skill_name] = raw[:3000]

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
        f"{description}\n\n"
        f"Args:\n"
        f"    query: The question or task for this specialist"
    )
    return subagent_tool



# -- Progressive Disclosure @tools ------------------------------------
# These give the supervisor on-demand access to skill metadata and
# plugin data WITHOUT spawning subagents or bloating the system prompt.
# Pattern: Layer 1 (system prompt hints) → Layer 2 (list_skills) →
#          Layer 3 (load_skill) → Layer 4 (load_data)
#
# Each is a factory function that closes over result_queue/loop so
# tool_result events reach the frontend for tool card observability.


def _emit_tool_result(
    tool_name: str,
    result_str: str,
    result_queue: asyncio.Queue | None,
    loop: asyncio.AbstractEventLoop | None,
):
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


def _make_list_skills_tool(
    result_queue: asyncio.Queue | None = None,
    loop: asyncio.AbstractEventLoop | None = None,
):
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
                skills_list.append({
                    "name": name,
                    "description": entry.get("description", ""),
                    "triggers": entry.get("triggers", []),
                })
            result["skills"] = skills_list

        if category in ("", "agents"):
            agents_list = []
            for name, entry in AGENTS.items():
                if name == "supervisor":
                    continue
                agents_list.append({
                    "name": name,
                    "description": entry.get("description", ""),
                    "triggers": entry.get("triggers", []),
                })
            result["agents"] = agents_list

        if category in ("", "data"):
            config = _load_plugin_config()
            data_index = config.get("data", {})
            data_list = []
            if isinstance(data_index, dict):
                for name, meta in data_index.items():
                    data_list.append({
                        "name": name,
                        "description": meta.get("description", ""),
                        "sections": meta.get("sections", []),
                    })
            result["data"] = data_list

        out = json.dumps(result, indent=2)
        _emit_tool_result("list_skills", out, result_queue, loop)
        return out

    return list_skills_tool


def _make_load_skill_tool(
    result_queue: asyncio.Queue | None = None,
    loop: asyncio.AbstractEventLoop | None = None,
):
    @tool(name="load_skill")
    def load_skill_tool(name: str) -> str:
        """Load full skill or agent instructions by name. Returns the complete SKILL.md or agent.md content so you can follow the workflow yourself without spawning a subagent. Use this when you need to understand a skill's detailed procedures, decision trees, or templates.

        Args:
            name: Skill or agent name (e.g. "oa-intake", "legal-counsel", "compliance")
        """
        entry = PLUGIN_CONTENTS.get(name)
        if not entry:
            available = sorted(PLUGIN_CONTENTS.keys())
            out = json.dumps({
                "error": f"No skill or agent named '{name}'",
                "available": available,
            })
        else:
            out = entry["body"]
        _emit_tool_result("load_skill", out, result_queue, loop)
        return out

    return load_skill_tool


def _make_load_data_tool(
    result_queue: asyncio.Queue | None = None,
    loop: asyncio.AbstractEventLoop | None = None,
):
    @tool(name="load_data")
    def load_data_tool(name: str, section: str = "") -> str:
        """Load reference data from the eagle-plugin data directory. Use this to access thresholds, contract types, document requirements, approval chains, contract vehicles, and other acquisition reference data on demand.

        Args:
            name: Data file name (e.g. "matrix", "thresholds", "contract-vehicles")
            section: Optional top-level key to extract (e.g. "thresholds", "doc_rules", "approval_chains", "contract_types"). Omit to get the full file.
        """
        config = _load_plugin_config()
        data_index = config.get("data", {})

        if isinstance(data_index, list):
            out = json.dumps({"error": "Data index not configured. Available files: " + str(data_index)})
            _emit_tool_result("load_data", out, result_queue, loop)
            return out

        meta = data_index.get(name)
        if not meta:
            out = json.dumps({
                "error": f"No data file named '{name}'",
                "available": sorted(data_index.keys()),
            })
            _emit_tool_result("load_data", out, result_queue, loop)
            return out

        file_rel = meta.get("file", f"data/{name}.json")
        file_path = os.path.join(_PLUGIN_DIR, file_rel)

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
                out = json.dumps({
                    "error": f"Section '{section}' not found in '{name}'",
                    "available_sections": list(data.keys()),
                })
                _emit_tool_result("load_data", out, result_queue, loop)
                return out
            out = json.dumps({section: value}, indent=2, default=str)
            _emit_tool_result("load_data", out, result_queue, loop)
            return out

        out = json.dumps(data, indent=2, default=str)
        _emit_tool_result("load_data", out, result_queue, loop)
        return out

    return load_data_tool


# -- State Push @tools (update_state + get_package_checklist) ----------
# These enable real-time frontend UI updates via SSE METADATA events.

def _make_update_state_tool(
    tenant_id: str,
    result_queue: asyncio.Queue | None = None,
    loop: asyncio.AbstractEventLoop | None = None,
):
    """Create a tool that pushes structured state to the frontend via SSE METADATA events
    and writes the updated state back into the supervisor's agent_state.

    State types:
      - checklist_update: package checklist progress (required/completed/missing)
      - phase_change: acquisition workflow phase transition
      - document_ready: notification that a document was created/updated
      - compliance_alert: compliance findings that need attention
    """
    from strands import ToolContext  # noqa: F401 (runtime type only)

    @tool(name="update_state")
    def update_state_tool(params: str, tool_context: Any = None) -> str:
        """Push a structured state update to the frontend UI. The frontend renders this immediately as a live checklist, progress bar, or alert.

        Args:
            params: JSON string with keys: state_type (required: checklist_update|phase_change|document_ready|compliance_alert), package_id (optional), and state-type-specific fields. For checklist_update: reads current package state from DB automatically — just pass package_id. For phase_change: pass phase, previous. For document_ready: pass doc_type, version, document_id. For compliance_alert: pass severity (info|warning|critical), items (array of {name, note}).
        """
        parsed = json.loads(params) if isinstance(params, str) else params
        state_type = parsed.get("state_type", "")

        if not state_type:
            return json.dumps({"error": "state_type is required"})

        payload: dict = {"state_type": state_type}

        if state_type == "checklist_update":
            # Auto-fetch current checklist from DynamoDB
            pkg_id = parsed.get("package_id", "")
            if pkg_id:
                from .stores.package_store import get_package_checklist
                checklist = get_package_checklist(tenant_id, pkg_id)
                payload["package_id"] = pkg_id
                payload["checklist"] = checklist
                total = len(checklist.get("required", []))
                done = len(checklist.get("completed", []))
                payload["progress_pct"] = round((done / total * 100) if total > 0 else 0)
            else:
                payload["checklist"] = parsed.get("checklist", {})
                payload["progress_pct"] = parsed.get("progress_pct", 0)

        elif state_type == "phase_change":
            payload["phase"] = parsed.get("phase", "")
            payload["previous"] = parsed.get("previous", "")
            # Also fetch checklist if package_id is available
            pkg_id = parsed.get("package_id", "")
            if pkg_id:
                from .stores.package_store import get_package_checklist
                payload["package_id"] = pkg_id
                payload["checklist"] = get_package_checklist(tenant_id, pkg_id)

        elif state_type == "document_ready":
            payload["doc_type"] = parsed.get("doc_type", "")
            payload["version"] = parsed.get("version", 1)
            payload["document_id"] = parsed.get("document_id", "")
            # Auto-refresh checklist
            pkg_id = parsed.get("package_id", "")
            if pkg_id:
                from .stores.package_store import get_package_checklist
                payload["package_id"] = pkg_id
                payload["checklist"] = get_package_checklist(tenant_id, pkg_id)

        elif state_type == "compliance_alert":
            payload["severity"] = parsed.get("severity", "info")
            payload["items"] = parsed.get("items", [])

        else:
            return json.dumps({"error": f"Unknown state_type: {state_type}"})

        # Apply the state change into the supervisor's live agent_state so it
        # survives the turn and is visible to AfterInvocationEvent.
        try:
            if tool_context is not None:
                agent = getattr(tool_context, "agent", None)
                if agent is not None:
                    current_state = getattr(agent, "state", None)
                    if isinstance(current_state, dict):
                        new_state = apply_event(current_state, state_type, parsed)
                        current_state.update(new_state)
        except Exception as _state_exc:
            logger.debug("update_state: agent_state merge failed (non-fatal): %s", _state_exc)

        # Push to frontend via SSE METADATA event
        if result_queue and loop:
            loop.call_soon_threadsafe(
                result_queue.put_nowait,
                {"type": "metadata", "content": payload},
            )

        return json.dumps({"ok": True, "state_type": state_type, "pushed": True})

    return update_state_tool


def _make_get_checklist_tool(
    tenant_id: str,
    result_queue: asyncio.Queue | None = None,
    loop: asyncio.AbstractEventLoop | None = None,
):
    @tool(name="get_package_checklist")
    def get_checklist_tool(params: str) -> str:
        """Fetch the current acquisition package checklist showing required, completed, and missing documents. Returns {required, completed, missing, complete} for the given package_id.

        Args:
            params: JSON string with key: package_id (required)
        """
        parsed = json.loads(params) if isinstance(params, str) else params
        pkg_id = parsed.get("package_id", "")
        if not pkg_id:
            return json.dumps({"error": "package_id is required"})

        from .stores.package_store import get_package_checklist
        checklist = get_package_checklist(tenant_id, pkg_id)
        out = json.dumps(checklist, default=str)
        _emit_tool_result("get_package_checklist", out, result_queue, loop)
        return out

    return get_checklist_tool


# -- Compliance Matrix @tool (available to all agents) ----------------

def _make_compliance_matrix_tool(
    result_queue: asyncio.Queue | None = None,
    loop: asyncio.AbstractEventLoop | None = None,
):
    @tool(name="query_compliance_matrix")
    def compliance_matrix_tool(params: str) -> str:
        """Query NCI/NIH contract requirements decision tree. Pass a JSON string with keys: operation (required), contract_value, acquisition_method, contract_type, is_it, is_small_business, is_rd, is_human_subjects, is_services, keyword. Operations: query, list_methods, list_types, list_thresholds, search_far, suggest_vehicle.

        Args:
            params: JSON string, e.g. {"operation":"query","contract_value":85000,"acquisition_method":"sap","contract_type":"ffp","is_services":true}
        """
        from .compliance_matrix import execute_operation

        parsed = json.loads(params) if isinstance(params, str) else params
        result = execute_operation(parsed)
        out = json.dumps(result, indent=2, default=str)
        _emit_tool_result("query_compliance_matrix", out, result_queue, loop)
        return out

    return compliance_matrix_tool


# -- Native @tool factories (typed params, Strands auto-generates schema) ---
# Each factory closes over tenant_id/user_id/session_id/result_queue/loop
# so the model never sees those context params — only the typed business params.


def _emit_tool_result(
    tool_name: str,
    result: Any,
    result_queue: asyncio.Queue | None,
    loop: asyncio.AbstractEventLoop | None,
    *,
    truncate: bool = True,
):
    """Push a tool_result SSE event so the frontend can render tool cards."""
    if not result_queue or not loop:
        return
    emit_result = result
    if truncate and isinstance(result, dict):
        text_val = result.get("content") or result.get("text") or result.get("result")
        if isinstance(text_val, str) and len(text_val) > 2000:
            emit_result = {**result}
            key = "content" if "content" in result else "text" if "text" in result else "result"
            emit_result[key] = text_val[:2000] + "..."
    loop.call_soon_threadsafe(
        result_queue.put_nowait,
        {"type": "tool_result", "name": tool_name, "result": emit_result},
    )


def _scoped_session(tenant_id: str, user_id: str, session_id: str | None) -> str:
    """Build composite session id for per-user S3/DDB scoping."""
    if session_id and "#" in session_id:
        return session_id
    return f"{tenant_id}#advanced#{user_id}#{session_id or ''}"


# ── Phase 1: High-Impact Tools ──────────────────────────────────────


def _make_search_far_tool(tenant_id, result_queue=None, loop=None):
    from .tool_dispatch import _exec_search_far

    @tool(name="search_far")
    def search_far(query: str, parts: str = "") -> str:
        """Search the FAR and DFARS for clauses, requirements, and guidance.

        Args:
            query: Search topic, clause number, or keyword (e.g. "sole source", "6.302")
            parts: Comma-separated FAR part numbers to filter (e.g. "6,13,15")
        """
        parts_list = [p.strip() for p in parts.split(",") if p.strip()] or None
        result = _exec_search_far({"query": query, "parts": parts_list}, tenant_id)
        _emit_tool_result("search_far", result, result_queue, loop)
        return json.dumps(result, default=str)

    return search_far


def _make_knowledge_search_tool(tenant_id, result_queue=None, loop=None):
    from .tool_dispatch import exec_knowledge_search

    @tool(name="knowledge_search")
    def knowledge_search(
        query: str = "",
        topic: str = "",
        document_type: str = "",
        primary_agent: str = "",
        authority_level: str = "",
        limit: int = 10,
    ) -> str:
        """Search the acquisition knowledge base metadata in DynamoDB.

        Args:
            query: Free-text query for case numbers (e.g. 'B-302358'), citations, or specific terms
            topic: Filter by topic: funding, acquisition_packages, contract_types, compliance, legal, etc.
            document_type: Filter by type: regulation, guidance, policy, template, memo, checklist, reference
            primary_agent: Filter by agent: supervisor-core, financial-advisor, legal-counselor, etc.
            authority_level: Filter by authority: statute, regulation, policy, guidance, internal
            limit: Max results to return (default 10, max 50)
        """
        params: dict[str, Any] = {}
        if query:
            params["query"] = query
        if topic:
            params["topic"] = topic
        if document_type:
            params["document_type"] = document_type
        if primary_agent:
            params["agent"] = primary_agent
        if authority_level:
            params["authority_level"] = authority_level
        params["limit"] = min(limit, 50)
        result = exec_knowledge_search(params, tenant_id)
        _emit_tool_result("knowledge_search", result, result_queue, loop)
        return json.dumps(result, default=str)

    return knowledge_search


def _make_web_search_tool(tenant_id, result_queue=None, loop=None):
    from .tool_dispatch import _exec_web_search

    @tool(name="web_search")
    def web_search(query: str, search_type: str = "web", count: int = 10) -> str:
        """Search the web for current regulations, policy updates, and federal acquisition info.

        Args:
            query: Search query string
            search_type: Type of search — web, news, or gov
            count: Number of results to return (default 10)
        """
        result = _exec_web_search({"query": query, "search_type": search_type, "count": count}, tenant_id)
        _emit_tool_result("web_search", result, result_queue, loop)
        return json.dumps(result, default=str)

    return web_search


# ── Phase 2: Medium-Impact Tools ────────────────────────────────────


def _make_browse_url_tool(tenant_id, result_queue=None, loop=None):
    from .tool_dispatch import _exec_browse_url

    @tool(name="browse_url")
    def browse_url(url: str, question: str = "") -> str:
        """Fetch and analyze web pages, PDFs, or documents from a URL.

        Args:
            url: URL to fetch and analyze
            question: Optional question to focus the analysis
        """
        params: dict[str, Any] = {"urls": [url]}
        if question:
            params["question"] = question
        result = _exec_browse_url(params, tenant_id)
        _emit_tool_result("browse_url", result, result_queue, loop)
        return json.dumps(result, default=str)

    return browse_url


def _make_knowledge_fetch_tool(tenant_id, result_queue=None, loop=None):
    from .tool_dispatch import exec_knowledge_fetch

    @tool(name="knowledge_fetch")
    def knowledge_fetch(s3_key: str = "", document_id: str = "") -> str:
        """Fetch full knowledge document content from S3.

        REQUIRES an s3_key from a prior knowledge_search result — do NOT call without one.

        Args:
            s3_key: S3 key from knowledge_search results
            document_id: Alternative — document_id from search results (same as s3_key)
        """
        params: dict[str, str] = {}
        if s3_key:
            params["s3_key"] = s3_key
        if document_id:
            params["document_id"] = document_id
        result = exec_knowledge_fetch(params, tenant_id)
        _emit_tool_result("knowledge_fetch", result, result_queue, loop)
        return json.dumps(result, default=str)

    return knowledge_fetch


def _make_get_intake_status_tool(tenant_id, user_id, session_id, result_queue=None, loop=None):
    from .tool_dispatch import _exec_get_intake_status

    scoped = _scoped_session(tenant_id, user_id, session_id)

    @tool(name="get_intake_status")
    def get_intake_status(intake_id: str = "") -> str:
        """Get the current intake package status and completeness.

        Shows which documents exist, which are missing, and next actions.

        Args:
            intake_id: Optional intake package ID to check
        """
        result = _exec_get_intake_status({"intake_id": intake_id}, tenant_id, scoped)
        _emit_tool_result("get_intake_status", result, result_queue, loop)
        return json.dumps(result, default=str)

    return get_intake_status


def _make_intake_workflow_tool(tenant_id, result_queue=None, loop=None):
    from .tool_dispatch import _exec_intake_workflow

    @tool(name="intake_workflow")
    def intake_workflow(action: str = "status", intake_id: str = "", data: str = "") -> str:
        """Manage the acquisition intake workflow: start, advance, status, complete, reset.

        Args:
            action: Workflow action — start, advance, status, complete, reset
            intake_id: Intake workflow ID (required for advance/complete/reset)
            data: JSON string of additional data for the action
        """
        params: dict[str, Any] = {"action": action}
        if intake_id:
            params["intake_id"] = intake_id
        if data:
            try:
                params["data"] = json.loads(data)
            except (json.JSONDecodeError, TypeError):
                params["data"] = {"note": data}
        result = _exec_intake_workflow(params, tenant_id)
        _emit_tool_result("intake_workflow", result, result_queue, loop)
        return json.dumps(result, default=str)

    return intake_workflow


def _make_code_execute_tool(tenant_id, result_queue=None, loop=None):
    from .tool_dispatch import _exec_code_execute

    @tool(name="code_execute")
    def code_execute(code: str, language: str = "python") -> str:
        """Execute code in a managed sandbox for calculations, data analysis, and cost modeling.

        Args:
            code: Code to execute
            language: Programming language — python, javascript, or typescript
        """
        result = _exec_code_execute({"code": code, "language": language}, tenant_id)
        _emit_tool_result("code_execute", result, result_queue, loop)
        return json.dumps(result, default=str)

    return code_execute


# ── Phase 3: Complex Tools ──────────────────────────────────────────


def _make_s3_document_ops_tool(tenant_id, user_id, session_id, result_queue=None, loop=None):
    from .tool_dispatch import _exec_s3_document_ops

    scoped = _scoped_session(tenant_id, user_id, session_id)

    @tool(name="s3_document_ops")
    def s3_document_ops(operation: str = "list", key: str = "", content: str = "") -> str:
        """Read, write, or list documents in S3 scoped per-tenant.

        Args:
            operation: S3 operation — list, read, or write
            key: Document key/path for read or write operations
            content: Document content for write operations
        """
        params: dict[str, str] = {"operation": operation}
        if key:
            params["key"] = key
        if content:
            params["content"] = content
        result = _exec_s3_document_ops(params, tenant_id, scoped)
        _emit_tool_result("s3_document_ops", result, result_queue, loop)
        return json.dumps(result, default=str)

    return s3_document_ops


def _make_dynamodb_intake_tool(tenant_id, result_queue=None, loop=None):
    from .tool_dispatch import _exec_dynamodb_intake

    @tool(name="dynamodb_intake")
    def dynamodb_intake(operation: str = "list", item_id: str = "", data: str = "") -> str:
        """Create, read, update, list, or query intake records in DynamoDB.

        Args:
            operation: DynamoDB operation — create, read, update, list, or query
            item_id: Intake record ID (required for read/update)
            data: JSON string of record data for create/update
        """
        params: dict[str, Any] = {"operation": operation}
        if item_id:
            params["item_id"] = item_id
        if data:
            try:
                params["data"] = json.loads(data)
            except (json.JSONDecodeError, TypeError):
                params["data"] = {"note": data}
        result = _exec_dynamodb_intake(params, tenant_id)
        _emit_tool_result("dynamodb_intake", result, result_queue, loop)
        return json.dumps(result, default=str)

    return dynamodb_intake


def _make_create_document_tool(
    tenant_id, user_id, session_id,
    package_context=None, result_queue=None, loop=None,
    prompt_context=None,
):
    from .tool_dispatch import _exec_create_document

    scoped = _scoped_session(tenant_id, user_id, session_id)

    @tool(name="create_document")
    def create_document(doc_type: str, title: str = "", data: str = "") -> str:
        """Generate acquisition documents (SOW, IGCE, Market Research, J&A, Acquisition Plan, etc.).

        Documents are saved to S3.

        Args:
            doc_type: Document type — sow, igce, market_research, justification, acquisition_plan,
                      eval_criteria, security_checklist, section_508, cor_certification,
                      contract_type_justification
            title: Document title (auto-inferred if omitted)
            data: JSON string of additional data fields for the document
        """
        # Build params dict from typed args
        parsed: dict[str, Any] = {"doc_type": doc_type.strip().lower()}

        # Infer title from prompt context if not provided
        if title.strip():
            parsed["title"] = title.strip()
        else:
            prompt_doc_ctx = _extract_document_context_from_prompt(prompt_context or "")
            inferred_title = (
                prompt_doc_ctx.get("title")
                or _DOC_TYPE_LABELS.get(parsed["doc_type"], "")
                or "Untitled Acquisition"
            )
            parsed["title"] = inferred_title

        # Parse data JSON
        existing_data: dict[str, Any] = {}
        if data:
            try:
                existing_data = json.loads(data)
                if not isinstance(existing_data, dict):
                    existing_data = {}
            except (json.JSONDecodeError, TypeError):
                existing_data = {}

        # Enrich from prompt context
        prompt_doc_ctx = _extract_document_context_from_prompt(prompt_context or "")
        prompt_data = _extract_context_data_from_prompt(prompt_context or "", parsed["doc_type"])
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

        # Package mode
        if (
            package_context is not None
            and getattr(package_context, "is_package_mode", False)
            and getattr(package_context, "package_id", None)
        ):
            parsed.setdefault("package_id", package_context.package_id)

        result = _exec_create_document(parsed, tenant_id, scoped)

        # Emit tool_result (no truncation for document results)
        _emit_tool_result("create_document", result, result_queue, loop, truncate=False)

        # Auto-push document_ready metadata in package mode
        if (
            result_queue and loop
            and isinstance(result, dict)
            and not result.get("error")
            and result.get("package_id")
        ):
            pkg_id = result["package_id"]
            doc_ready_payload = {
                "state_type": "document_ready",
                "package_id": pkg_id,
                "doc_type": result.get("doc_type", parsed.get("doc_type", "")),
                "version": result.get("version", 1),
                "document_id": result.get("document_id", ""),
            }
            try:
                from .stores.package_store import get_package_checklist
                checklist = get_package_checklist(tenant_id, pkg_id)
                doc_ready_payload["checklist"] = checklist
                total = len(checklist.get("required", []))
                done = len(checklist.get("completed", []))
                doc_ready_payload["progress_pct"] = round((done / total * 100) if total > 0 else 0)
            except Exception:
                pass
            loop.call_soon_threadsafe(
                result_queue.put_nowait,
                {"type": "metadata", "content": doc_ready_payload},
            )

        return json.dumps(result, indent=2, default=str)

    return create_document


def _make_manage_skills_tool(tenant_id, result_queue=None, loop=None):
    from .tool_dispatch import _exec_manage_skills

    @tool(name="manage_skills")
    def manage_skills(
        action: str = "list",
        skill_id: str = "",
        name: str = "",
        display_name: str = "",
        description: str = "",
        prompt_body: str = "",
        visibility: str = "private",
    ) -> str:
        """Create, list, update, delete, or publish custom skills.

        Args:
            action: Skill action — list, get, create, update, delete, submit, publish, disable
            skill_id: Skill ID (required for get/update/delete/submit/publish/disable)
            name: Skill name (required for create)
            display_name: Display name (required for create)
            description: Skill description (required for create)
            prompt_body: Skill prompt body (required for create)
            visibility: Visibility — private or shared
        """
        params: dict[str, Any] = {"action": action}
        if skill_id:
            params["skill_id"] = skill_id
        if name:
            params["name"] = name
        if display_name:
            params["display_name"] = display_name
        if description:
            params["description"] = description
        if prompt_body:
            params["prompt_body"] = prompt_body
        if visibility != "private":
            params["visibility"] = visibility
        result = _exec_manage_skills(params, tenant_id)
        _emit_tool_result("manage_skills", result, result_queue, loop)
        return json.dumps(result, default=str)

    return manage_skills


def _make_manage_prompts_tool(tenant_id, result_queue=None, loop=None):
    from .tool_dispatch import _exec_manage_prompts

    @tool(name="manage_prompts")
    def manage_prompts(
        action: str = "list",
        agent_name: str = "",
        prompt_body: str = "",
        is_append: bool = False,
    ) -> str:
        """List, view, set, or delete agent prompt overrides.

        Args:
            action: Prompt action — list, get, set, delete, resolve
            agent_name: Agent name (required for get/set/delete/resolve)
            prompt_body: Prompt body text (required for set)
            is_append: If true, append to existing prompt instead of replacing
        """
        params: dict[str, Any] = {"action": action}
        if agent_name:
            params["agent_name"] = agent_name
        if prompt_body:
            params["prompt_body"] = prompt_body
        if is_append:
            params["is_append"] = is_append
        result = _exec_manage_prompts(params, tenant_id)
        _emit_tool_result("manage_prompts", result, result_queue, loop)
        return json.dumps(result, default=str)

    return manage_prompts


def _make_manage_templates_tool(tenant_id, result_queue=None, loop=None):
    from .tool_dispatch import _exec_manage_templates

    @tool(name="manage_templates")
    def manage_templates(
        action: str = "list",
        doc_type: str = "",
        template_body: str = "",
        display_name: str = "",
        user_id: str = "",
    ) -> str:
        """List, view, set, or delete document templates.

        Args:
            action: Template action — list, get, set, delete, resolve
            doc_type: Document type (required for get/set/delete/resolve)
            template_body: Template body text (required for set)
            display_name: Display name for the template
            user_id: User ID scope (defaults to 'shared')
        """
        params: dict[str, Any] = {"action": action}
        if doc_type:
            params["doc_type"] = doc_type
        if template_body:
            params["template_body"] = template_body
        if display_name:
            params["display_name"] = display_name
        if user_id:
            params["user_id"] = user_id
        result = _exec_manage_templates(params, tenant_id)
        _emit_tool_result("manage_templates", result, result_queue, loop)
        return json.dumps(result, default=str)

    return manage_templates


def _make_workspace_memory_tool(tenant_id, user_id, session_id, result_queue=None, loop=None):
    from .tool_dispatch import _exec_workspace_memory

    scoped = _scoped_session(tenant_id, user_id, session_id)

    @tool(name="workspace_memory")
    def workspace_memory(
        command: str = "view",
        path: str = "_workspace.txt",
        content: str = "",
    ) -> str:
        """View and edit persistent workspace files for tracking work and context across sessions.

        Args:
            command: Memory command — view, write, append, clear, list, search
            path: File path within workspace (default: _workspace.txt)
            content: Content to write or append (required for write/append)
        """
        params = {"command": command, "path": path, "content": content}
        result = _exec_workspace_memory(params, tenant_id, scoped)
        _emit_tool_result("workspace_memory", result, result_queue, loop)
        return json.dumps(result, default=str)

    return workspace_memory


def _make_think_tool(tenant_id, user_id, session_id, result_queue=None, loop=None):
    """Factory: create the think @tool for extended reasoning.

    Saves thought to _thoughts.txt in workspace memory so the model can
    do structured multi-step analysis before generating a response.
    """
    from .tool_dispatch import _exec_workspace_memory

    scoped = _scoped_session(tenant_id, user_id, session_id)

    @tool(name="think")
    def think(
        thought: str = "",
    ) -> str:
        """Extended reasoning space for complex analysis. Use for multi-threshold
        analysis, competing FAR requirements, risk assessment, strategy comparison,
        or synthesizing research from multiple sources before responding.

        Include the COMPLETE information that needs processing — full KB content,
        search results, FAR text, and all relevant context. This is for substantial
        reasoning work that needs careful analysis.

        Args:
            thought: The full analysis text including all context and reasoning
        """
        params = {"command": "append", "path": "_thoughts.txt", "content": thought}
        _exec_workspace_memory(params, tenant_id, scoped)
        _emit_tool_result("think", {"status": "thinking_complete"}, result_queue, loop)
        return "Thinking complete."

    return think


def _make_generate_document_tool(
    tenant_id: str,
    user_id: str,
    session_id: str | None,
    package_context: Any = None,
    result_queue: asyncio.Queue | None = None,
    loop: asyncio.AbstractEventLoop | None = None,
):
    """Factory: create the generate_document @tool that uses document_agent."""

    scoped_session_id = session_id
    if not scoped_session_id or "#" not in (scoped_session_id or ""):
        scoped_session_id = f"{tenant_id}#advanced#{user_id}#{session_id or ''}"

    @tool(name="generate_document")
    def generate_document_tool(doc_type: str, special_instructions: str = "") -> str:
        """Generate a complete acquisition document using AI-driven content."""
        from app.document_agent import generate_document as _gen
        from app.document_service import create_package_document_version

        result = _gen(
            doc_type=doc_type,
            session_id=scoped_session_id,
            tenant_id=tenant_id,
            user_id=user_id,
            special_instructions=special_instructions,
        )

        if not result.success:
            return json.dumps({"error": result.error})

        response: dict = {
            "doc_type": result.doc_type,
            "title": result.title,
            "content": result.content,
            "word_count": result.word_count,
            "missing_required": result.missing_required,
            "omission_count": len(result.omissions),
            "justification_count": len(result.justifications),
            "source": "document_agent",
        }

        # Save via canonical document service in package mode
        pkg_id = (
            getattr(package_context, "package_id", None)
            if package_context and getattr(package_context, "is_package_mode", False)
            else None
        )

        if pkg_id:
            try:
                canonical = create_package_document_version(
                    tenant_id=tenant_id,
                    package_id=pkg_id,
                    doc_type=doc_type,
                    content=result.content,
                    title=result.title,
                    file_type="md",
                    created_by_user_id=user_id,
                    session_id=scoped_session_id,
                    change_source="agent_tool",
                )
                if canonical.success:
                    response["mode"] = "package"
                    response["package_id"] = pkg_id
                    response["document_id"] = canonical.document_id
                    response["version"] = canonical.version
                    response["status"] = canonical.status or "draft"
                    response["s3_key"] = canonical.s3_key
                else:
                    response["save_error"] = canonical.error
            except Exception as exc:
                logger.warning("Package save failed for generate_document: %s", exc)
                response["save_error"] = str(exc)
        else:
            # Non-package mode: save to user-scoped S3 path
            try:
                bucket = os.getenv("S3_BUCKET", "eagle-documents-695681773636-dev")
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                s3_key = f"eagle/{tenant_id}/{user_id}/documents/{doc_type}_{timestamp}.md"
                s3 = boto3.client("s3")
                s3.put_object(
                    Bucket=bucket,
                    Key=s3_key,
                    Body=result.content.encode("utf-8"),
                )
                response["s3_key"] = s3_key
                response["s3_location"] = f"s3://{bucket}/{s3_key}"
            except Exception as exc:
                logger.warning("S3 save failed for generate_document: %s", exc)
                response["save_error"] = str(exc)

        # Emit SSE events for frontend
        if result_queue and loop:
            loop.call_soon_threadsafe(
                result_queue.put_nowait,
                {"type": "tool_result", "name": "generate_document", "result": response},
            )
            # Emit document_ready metadata
            if pkg_id and response.get("version"):
                loop.call_soon_threadsafe(
                    result_queue.put_nowait,
                    {
                        "type": "metadata",
                        "data": {
                            "type": "document_ready",
                            "package_id": pkg_id,
                            "doc_type": doc_type,
                            "version": response.get("version"),
                            "title": result.title,
                            "word_count": result.word_count,
                            "source": "document_agent",
                        },
                    },
                )

        return json.dumps(response)

    return generate_document_tool


def _build_service_tools(
    tenant_id: str,
    user_id: str,
    session_id: str | None,
    prompt_context: str | None = None,
    package_context: Any = None,
    result_queue: asyncio.Queue | None = None,
    loop: asyncio.AbstractEventLoop | None = None,
) -> list:
    """Build native @tool wrappers for AWS service tools, scoped to the current tenant/user/session.

    Each tool uses typed parameters so the model sees exact param names and types
    instead of a generic ``params: str`` JSON blob.
    """
    rq, lp = result_queue, loop  # shorthand

    tools = [
        # Phase 1: High-impact tools (typed params fix model input errors)
        _make_search_far_tool(tenant_id, rq, lp),
        _make_knowledge_search_tool(tenant_id, rq, lp),
        _make_web_search_tool(tenant_id, rq, lp),
        # Phase 2: Medium-impact tools
        _make_browse_url_tool(tenant_id, rq, lp),
        _make_knowledge_fetch_tool(tenant_id, rq, lp),
        _make_get_intake_status_tool(tenant_id, user_id, session_id, rq, lp),
        _make_intake_workflow_tool(tenant_id, rq, lp),
        _make_code_execute_tool(tenant_id, rq, lp),
        # Phase 3: Complex tools
        _make_s3_document_ops_tool(tenant_id, user_id, session_id, rq, lp),
        _make_dynamodb_intake_tool(tenant_id, rq, lp),
        _make_create_document_tool(
            tenant_id, user_id, session_id,
            package_context=package_context,
            result_queue=rq, loop=lp,
            prompt_context=prompt_context,
        ),
        _make_manage_skills_tool(tenant_id, rq, lp),
        _make_manage_prompts_tool(tenant_id, rq, lp),
        _make_manage_templates_tool(tenant_id, rq, lp),
        _make_workspace_memory_tool(tenant_id, user_id, session_id, rq, lp),
        _make_think_tool(tenant_id, user_id, session_id, rq, lp),
    ]

    # AI-driven document generation (Agent-as-Tool)
    tools.append(
        _make_generate_document_tool(
            tenant_id, user_id, session_id,
            package_context=package_context,
            result_queue=rq,
            loop=lp,
        )
    )
    # Compliance matrix and progressive disclosure tools
    tools.append(_make_compliance_matrix_tool(rq, lp))
    tools.append(_make_list_skills_tool(rq, lp))
    tools.append(_make_load_skill_tool(rq, lp))
    tools.append(_make_load_data_tool(rq, lp))
    # State push tools — enable real-time frontend UI updates via SSE METADATA
    tools.append(_make_update_state_tool(tenant_id, rq, lp))
    tools.append(_make_get_checklist_tool(tenant_id, rq, lp))
    # Contract requirements matrix — deterministic FAR-grounded scoring
    tools.append(query_contract_matrix)
    return tools


# -- build_skill_tools() ---------------------------------------------

def build_skill_tools(
    tier: str = "advanced",
    skill_names: list[str] | None = None,
    tenant_id: str = "demo-tenant",
    user_id: str = "demo-user",
    session_id: str | None = None,
    workspace_id: str | None = None,
    result_queue: asyncio.Queue | None = None,
    loop: asyncio.AbstractEventLoop | None = None,
    context_frame: dict | None = None,
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
                from .stores.workspace_config_store import resolve_skill
                prompt_body, _source = resolve_skill(tenant_id, user_id, workspace_id, name)
            except Exception as exc:
                logger.warning("wspc_store.resolve_skill failed for %s: %s -- using bundled", name, exc)
                prompt_body = ""

        # Fall back to bundled PLUGIN_CONTENTS
        if not prompt_body:
            entry = PLUGIN_CONTENTS.get(meta["skill_key"])
            if not entry:
                logger.warning("Plugin content not found for %s (key=%s)", name, meta["skill_key"])
                continue
            prompt_body = entry["body"]

        tools.append(_make_subagent_tool(
            skill_name=name,
            description=meta["description"],
            prompt_body=_truncate_skill(prompt_body),
            result_queue=result_queue,
            loop=loop,
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            tier=tier,
            context_frame=context_frame,
        ))

    # Merge active user-created SKILL# items
    try:
        from .stores.skill_store import list_active_skills
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
            tools.append(_make_subagent_tool(
                skill_name=name,
                description=skill.get("description", f"{name} specialist"),
                prompt_body=_truncate_skill(skill_prompt),
                result_queue=result_queue,
                loop=loop,
                tenant_id=tenant_id,
                user_id=user_id,
                session_id=session_id,
                tier=tier,
                context_frame=context_frame,
            ))
    except Exception as exc:
        logger.warning("skill_store.list_active_skills failed for %s: %s -- skipping user skills", tenant_id, exc)

    return tools


# -- Supervisor Prompt -----------------------------------------------

def build_supervisor_prompt(
    tenant_id: str = "demo-tenant",
    user_id: str = "demo-user",
    tier: str = "advanced",
    agent_names: list[str] | None = None,
    workspace_id: str | None = None,
) -> str:
    """Build the supervisor system prompt with available subagent descriptions.

    Loads the base supervisor prompt from the 4-layer resolution chain when
    workspace_id is provided; otherwise falls back to AGENTS bundled content.
    """
    names = agent_names or list(SKILL_AGENT_REGISTRY.keys())
    agent_list = "\n".join(
        f"- {name}: {SKILL_AGENT_REGISTRY[name]['description']}"
        for name in names
        if name in SKILL_AGENT_REGISTRY
    )

    # Resolve supervisor prompt via workspace chain
    base_prompt = ""
    if workspace_id:
        try:
            from .stores.workspace_config_store import resolve_agent
            base_prompt, _source = resolve_agent(tenant_id, user_id, workspace_id, "supervisor")
        except Exception as exc:
            logger.warning("wspc_store.resolve_agent failed for supervisor: %s -- using bundled", exc)

    if not base_prompt:
        supervisor_entry = AGENTS.get("supervisor")
        base_prompt = supervisor_entry["body"].strip() if supervisor_entry else "You are the EAGLE Supervisor Agent for NCI Office of Acquisitions."

    return (
        f"Tenant: {tenant_id} | User: {user_id} | Tier: {tier}\n\n"
        f"{base_prompt}\n\n"
        f"--- ACTIVE SPECIALISTS ---\n"
        f"Available specialists for delegation:\n{agent_list}\n\n"
        "Progressive Disclosure (how to find information):\n"
        "  You have layered access to skills and data. Use the lightest layer that answers the question:\n"
        "  Layer 1 — System prompt hints (you already have short descriptions above).\n"
        "  Layer 2 — list_skills(): Discover available skills, agents, and data files with descriptions.\n"
        "  Layer 3 — load_skill(name): Read full skill instructions/workflows to follow them yourself.\n"
        "  Layer 4 — load_data(name, section?): Fetch reference data (thresholds, vehicles, doc rules).\n"
        "  Only spawn a specialist subagent when you need expert reasoning, not for simple lookups.\n\n"
        "KB Retrieval Rules:\n"
        "1) For policy/regulation/procedure/template questions, call knowledge_search first.\n"
        "2) If search returns results, call knowledge_fetch on the top 1-3 relevant docs.\n"
        "3) In final answer, include a Sources section with title + s3_key.\n"
        "4) If no results, explicitly say no KB match and ask a refinement question.\n"
        "5) Prefer knowledge_search/knowledge_fetch over search_far when KB can answer.\n"
        "6) Use search_far only as fallback reference.\n\n"
        "Document Output Rules:\n"
        "1) If the user asks to generate/draft/create a document, you MUST call create_document.\n"
        "2) Do not paste full document bodies in chat unless the user explicitly asks for inline text.\n"
        "3) After create_document, respond briefly and direct the user to open/edit the document card.\n"
        "4) After create_document succeeds, call update_state with state_type='document_ready'.\n\n"
        "State Push Rules (update_state tool) — MANDATORY:\n"
        "The frontend has a live checklist panel driven by eagle_state. You MUST call update_state:\n"
        "  - After create_document → update_state(state_type='document_ready', package_id, doc_type, version, document_id)\n"
        "  - After query_compliance_matrix reveals requirements → update_state(state_type='checklist_update', package_id)\n"
        "  - On phase transitions → update_state(state_type='phase_change', package_id, phase, previous)\n"
        "  - On compliance findings → update_state(state_type='compliance_alert', severity, items)\n"
        "  Just pass package_id for checklist_update — the tool auto-fetches current state from DB.\n"
        "  Call get_package_checklist before generating docs to see what's done and what's missing.\n"
        "CRITICAL: After completing ALL requested analyses and BEFORE writing your final synthesis\n"
        "  response, call update_state with state_type='phase_change' to record the transition.\n"
        "  Example: update_state(state_type='phase_change', phase='analysis_complete', previous='intake')\n"
        "  This MUST happen before the synthesis text. The frontend checklist depends on it.\n\n"
        "Response Length Rules — IMPORTANT:\n"
        "  DEFAULT: Short and direct. 2-4 sentences for simple questions, 3-5 bullets for lists.\n"
        "    Match response length to what was actually asked — don't over-explain.\n"
        "  AFTER multi-skill analysis (when 2+ specialists have run), give a CONSULTATIVE BRIEF:\n"
        "    1) KEY INSIGHT — one sentence: the single most important finding.\n"
        "    2) WHY — one short paragraph: the main driver (regulatory/market/risk reason).\n"
        "    3) SCENARIOS — 2-3 options: 'If X, then Y' — concrete, actionable alternatives.\n"
        "    4) NEXT STEP — one clear action or question.\n"
        "    Do NOT paste full specialist reports. Distill. The user wants to make a decision, not read a novel.\n"
        "  DEEP RESEARCH (for complex regulatory, legal, protest, case law, or policy analysis):\n"
        "    Produce a comprehensive, structured response with H2/H3 headers, comparison tables,\n"
        "    case citations with holdings, risk flags, NIH-specific guidance, and a References section.\n"
        "    Use think() to synthesize before writing. Include day-by-day timelines where applicable.\n"
        "  FULL REPORT only when user explicitly asks: 'full analysis', 'complete report', 'all details'.\n\n"
        "Citation & Source Requirements:\n"
        "  When using search or browse tools, include markdown inline citations [(Author, Year)](url).\n"
        "  Conclude researched responses with a References section.\n"
        "  Cite specific FAR sections: 'Per FAR 15.306(c)...'\n"
        "  Cite specific GAO decisions: '*Equitus Corp.*, B-419701 (May 12, 2021)'\n"
        "  When KB has the answer, cite the source document.\n"
        "  NEVER fabricate FAR citations, threshold values, GAO case holdings, or regulatory guidance.\n"
        "  Use search_far, query_compliance_matrix, and knowledge_search for authoritative data.\n"
        "  If unable to verify, state limitations rather than guessing.\n\n"
        "Think Tool Usage:\n"
        "  Use think() for complex regulatory analysis BEFORE writing the final response.\n"
        "  Include COMPLETE information: full KB content, search results, FAR text, all context.\n"
        "  Use for: multi-threshold analysis, competing requirements, risk assessment,\n"
        "    strategy comparison, synthesizing research from multiple sources.\n\n"
        f"FAST vs DEEP routing:\n"
        f"  FAST (seconds):\n"
        f"    - load_data('matrix', 'thresholds') for threshold lookups.\n"
        f"    - load_data('contract-vehicles', 'nitaac') for vehicle details.\n"
        f"    - query_compliance_matrix for computed compliance decisions.\n"
        f"    - search_far for specific FAR/DFARS clause lookups.\n"
        f"    - knowledge_search → knowledge_fetch for KB documents.\n"
        f"    - load_skill(name) to read a workflow and follow it yourself.\n"
        f"  DEEP (specialist): Delegate to specialist subagents only for complex analysis,\n"
        f"    multi-factor evaluation, or expert reasoning — not simple factual lookups.\n"
        f"  ALWAYS prefer FAST tools first. Only delegate to a specialist when FAST tools don't suffice.\n\n"
        f"IMPORTANT: Use the available tool functions to delegate to specialists. "
        f"Include relevant context in the query you pass to each specialist. "
        f"Do not try to answer specialized questions yourself -- delegate to the expert."
    )


# -- SDK Query Wrappers (same signatures as sdk_agentic_service.py) --

def _to_strands_messages(anthropic_messages: list[dict]) -> list[dict]:
    """Convert Anthropic-format messages to Strands Message format.

    Anthropic: [{"role": "user", "content": "text"}, ...]
    Strands:   [{"role": "user", "content": [{"text": "text"}]}, ...]
    """
    strands_msgs = []
    for msg in anthropic_messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if isinstance(content, str):
            strands_msgs.append({"role": role, "content": [{"text": content}]})
        elif isinstance(content, list):
            # Already in block format — pass through
            strands_msgs.append({"role": role, "content": content})
    return strands_msgs


async def sdk_query(
    prompt: str,
    tenant_id: str = "demo-tenant",
    user_id: str = "demo-user",
    tier: str = "advanced",
    model: str = None,
    skill_names: list[str] | None = None,
    session_id: str | None = None,
    workspace_id: str | None = None,
    package_context: Any = None,
    max_turns: int = 15,
    messages: list[dict] | None = None,
) -> AsyncGenerator[Any, None]:
    """Run a supervisor query with skill subagents (Strands implementation).

    Same signature as sdk_agentic_service.sdk_query(). Yields adapter objects
    that match the AssistantMessage/ResultMessage interface expected by callers.

    Args:
        prompt: User's query/request
        tenant_id: Tenant identifier for multi-tenant isolation
        user_id: User identifier
        tier: Subscription tier (basic/advanced/premium)
        model: Model override (unused in Strands -- model is shared)
        skill_names: Subset of skills to make available
        session_id: Session ID for session persistence
        workspace_id: Active workspace for per-user prompt resolution
        max_turns: Max tool-use iterations (reserved for future use)
        messages: Conversation history in Anthropic format (excludes current prompt)

    Yields:
        AssistantMessage and ResultMessage adapter objects
    """
    # Trivial greeting fast-path — no LLM call needed
    trivial = _fast_trivial_response(prompt)
    if trivial is not None:
        yield AssistantMessage(content=[TextBlock(text=trivial["text"])])
        yield ResultMessage(result=trivial["text"], usage=trivial["usage"])
        return

    # Intake form fast-path — canned ack, no LLM call
    intake = _fast_intake_form_response(prompt)
    if intake is not None:
        yield AssistantMessage(content=[TextBlock(text=intake["text"])])
        yield ResultMessage(result=intake["text"], usage=intake["usage"])
        return

    fast_path = await _maybe_fast_path_document_generation(
        prompt=prompt,
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id,
        package_context=package_context,
    )
    if fast_path is not None:
        result = fast_path["result"]
        if "error" in result:
            yield AssistantMessage(content=[TextBlock(text=f"Document generation failed: {result['error']}")])
            yield ResultMessage(result=f"Document generation failed: {result['error']}", usage={})
            return

        text = (
            f"Generated a draft {fast_path['doc_type'].replace('_', ' ')} document. "
            "You can open it from the document card."
        )
        yield AssistantMessage(
            content=[
                TextBlock(text=text),
                ToolUseBlock(name="create_document"),
            ]
        )
        yield ResultMessage(
            result=text,
            usage={"tools_called": 1, "tools": ["create_document"], "fast_path": True},
        )
        return

    # Resolve active workspace when none provided
    resolved_workspace_id = workspace_id
    if not resolved_workspace_id:
        try:
            from .stores.workspace_store import get_or_create_default
            ws = get_or_create_default(tenant_id, user_id)
            resolved_workspace_id = ws.get("workspace_id")
        except Exception as exc:
            logger.warning("workspace_store.get_or_create_default failed: %s -- using bundled prompts", exc)

    # context_frame is shared across all subagent tools for this request.
    # "state" is populated after state load (tools read it at call time, not factory time).
    # "completed" accumulates skill names as subagents return, giving later subagents
    # awareness of what prior analyses have already run.
    context_frame: dict = {"state": {}, "completed": []}

    skill_tools = build_skill_tools(
        tier=tier,
        skill_names=skill_names,
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id,
        workspace_id=resolved_workspace_id,
        context_frame=context_frame,
    )

    # Build service tools (S3, DynamoDB, create_document, search_far, etc.)
    service_tools = _build_service_tools(
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id,
        prompt_context=prompt,
        package_context=package_context,
    )

    system_prompt = build_supervisor_prompt(
        tenant_id=tenant_id,
        user_id=user_id,
        tier=tier,
        agent_names=[t.__name__ for t in skill_tools],
        workspace_id=resolved_workspace_id,
    )

    # Convert conversation history to Strands format (excludes current prompt)
    strands_history = _to_strands_messages(messages) if messages else None

    # Load persisted agent state and normalize (fills any missing keys from defaults)
    _leaf_session = session_id.split("#")[-1] if session_id and "#" in session_id else session_id
    try:
        from .stores.session_store import load_agent_state
        _loaded_state = normalize(
            load_agent_state(_leaf_session, tenant_id, user_id) if _leaf_session else None
        )
    except Exception as _e:
        logger.warning("load_agent_state failed (non-fatal): %s", _e)
        _loaded_state = normalize(None)
    _loaded_state["session_id"] = _leaf_session

    # Populate context_frame state now that eagle_state is loaded.
    # Subagent tools read this at call time so they always see the current state.
    context_frame["state"] = _loaded_state

    sse_hook = EagleSSEHookProvider(
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=_leaf_session,
    )

    # Summarizing conversation manager: on context overflow, summarize the oldest
    # 30% of messages (SDK default/recommended) while preserving the 10 most recent.
    _conversation_manager = SummarizingConversationManager(
        summary_ratio=0.3,
        preserve_recent_messages=10,
    )

    # Ensure Langfuse OTEL exporter is attached before Agent() caches its tracer
    _ensure_langfuse_exporter()

    supervisor = Agent(
        model=_get_model(),
        system_prompt=system_prompt,
        tools=skill_tools + service_tools,
        callback_handler=None,
        messages=strands_history,
        hooks=[sse_hook],
        state=_loaded_state,
        conversation_manager=_conversation_manager,
        trace_attributes=to_trace_attrs(
            _loaded_state,
            tenant_id=tenant_id,
            user_id=user_id,
            tier=tier,
            session_id=session_id or "",
        ),
    )

    # Synchronous call -- Strands handles the agentic loop internally
    result = supervisor(prompt)
    result_text = str(result)

    # Flush final state to DynamoDB (non-streaming path; streaming path uses hook)
    try:
        from .stores.session_store import save_agent_state
        final_state = stamp(getattr(result, "state", None) or _loaded_state)
        final_state["turn_count"] = final_state.get("turn_count", 0) + 1
        if _leaf_session:
            save_agent_state(_leaf_session, final_state, tenant_id, user_id)
    except Exception as _e:
        logger.warning("State flush (sdk_query) failed (non-fatal): %s", _e)

    # Extract tool names called during execution from metrics.tool_metrics
    tools_called = []
    try:
        metrics = getattr(result, "metrics", None)
        if metrics and hasattr(metrics, "tool_metrics"):
            tools_called = list(metrics.tool_metrics.keys())
    except Exception:
        pass

    forced_doc = await _ensure_create_document_for_direct_request(
        prompt=prompt,
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id,
        package_context=package_context,
        tools_called=tools_called,
    )
    if forced_doc is not None:
        tools_called.append("create_document")
        result_text = (
            f"Generated a draft {forced_doc['doc_type'].replace('_', ' ')} document. "
            "Open the document card to review or edit it."
        )

    # Build content blocks for AssistantMessage
    content_blocks = [TextBlock(text=result_text)]
    for tool_name in tools_called:
        content_blocks.append(ToolUseBlock(name=tool_name))

    # Yield adapter messages matching Claude SDK interface
    yield AssistantMessage(content=content_blocks)

    # Extract usage if available
    usage = {}
    try:
        metrics = getattr(result, "metrics", None)
        if metrics:
            acc = getattr(metrics, "accumulated_usage", None)
            if acc and isinstance(acc, dict):
                usage = acc
            else:
                # Fallback: report cycle count and tool call count
                usage = {
                    "cycle_count": getattr(metrics, "cycle_count", 0),
                    "tools_called": len(tools_called),
                }
    except Exception:
        pass

    yield ResultMessage(result=result_text, usage=usage)


def _sanitize_event(event: dict) -> dict:
    """Make a raw Strands stream event JSON-serializable.

    Round-trips through json.dumps/loads so the returned dict contains
    only JSON-native types (str, int, float, bool, None, list, dict).
    This prevents downstream json.dumps (without default=str) from failing.
    """
    try:
        return json.loads(json.dumps(event, default=str))
    except (TypeError, ValueError, RecursionError):
        return {"raw": str(event)}


async def sdk_query_streaming(
    prompt: str,
    tenant_id: str = "demo-tenant",
    user_id: str = "demo-user",
    tier: str = "advanced",
    skill_names: list[str] | None = None,
    session_id: str | None = None,
    workspace_id: str | None = None,
    package_context: Any = None,
    max_turns: int = 15,
    messages: list[dict] | None = None,
) -> AsyncGenerator[dict, None]:
    """Stream text deltas from the Strands supervisor agent.

    Unlike sdk_query() which waits for the full response, this yields
    {"type": "text", "data": "..."} chunks as they arrive from Bedrock
    ConverseStream, plus a final {"type": "complete", ...} event.

    Uses Agent.stream_async() which handles the sync→async bridge
    internally. Factory tools push results via an asyncio.Queue that
    is drained between stream events.
    """
    # Trivial greeting fast-path — no LLM call needed
    trivial = _fast_trivial_response(prompt)
    if trivial is not None:
        _fp_state = normalize(None)
        yield {"type": "text", "data": trivial["text"]}
        yield {
            "type": "complete",
            "text": trivial["text"],
            "tools_called": [],
            "usage": trivial["usage"],
            "agent_state": _fp_state,
        }
        return

    # Intake form fast-path — canned ack, no LLM call
    intake = _fast_intake_form_response(prompt)
    if intake is not None:
        _fp_state = normalize(None)
        yield {"type": "text", "data": intake["text"]}
        yield {
            "type": "complete",
            "text": intake["text"],
            "tools_called": [],
            "usage": intake["usage"],
            "agent_state": _fp_state,
        }
        return

    fast_path = await _maybe_fast_path_document_generation(
        prompt=prompt,
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id,
        package_context=package_context,
    )
    if fast_path is not None:
        result = fast_path["result"]
        if "error" in result:
            yield {"type": "error", "error": result["error"]}
            return
        yield {"type": "tool_use", "name": "create_document"}
        yield {"type": "tool_result", "name": "create_document", "result": result}
        text = (
            f"Generated a draft {fast_path['doc_type'].replace('_', ' ')} document. "
            "Open the document card to review or edit it."
        )
        yield {"type": "text", "data": text}
        # Load state for fast-path doc (before the session-scoped load below)
        _fp_leaf = session_id.split("#")[-1] if session_id and "#" in session_id else session_id
        try:
            from .stores.session_store import load_agent_state
            _fp_state = normalize(
                load_agent_state(_fp_leaf, tenant_id, user_id) if _fp_leaf else None
            )
        except Exception:
            _fp_state = normalize(None)
        yield {
            "type": "complete",
            "text": text,
            "tools_called": ["create_document"],
            "usage": {"tools_called": 1, "tools": ["create_document"], "fast_path": True},
            "agent_state": _fp_state,
        }
        return

    # Resolve workspace
    resolved_workspace_id = workspace_id
    if not resolved_workspace_id:
        try:
            from .stores.workspace_store import get_or_create_default
            ws = get_or_create_default(tenant_id, user_id)
            resolved_workspace_id = ws.get("workspace_id")
        except Exception as exc:
            logger.warning("workspace_store.get_or_create_default failed: %s", exc)

    # --- stream_async() approach: SDK handles sync→async bridge ---
    # result_queue is still used by factory tools to push tool_result events.
    # These are drained between stream events in the main async for loop.

    result_queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    # Shared context frame — populated after state load, read at subagent call time
    context_frame_stream: dict = {"state": {}, "completed": []}

    skill_tools = build_skill_tools(
        tier=tier,
        skill_names=skill_names,
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id,
        workspace_id=resolved_workspace_id,
        result_queue=result_queue,
        loop=loop,
        context_frame=context_frame_stream,
    )

    # Build service tools (S3, DynamoDB, create_document, search_far, etc.)
    service_tools = _build_service_tools(
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id,
        prompt_context=prompt,
        package_context=package_context,
        result_queue=result_queue,
        loop=loop,
    )

    system_prompt = build_supervisor_prompt(
        tenant_id=tenant_id,
        user_id=user_id,
        tier=tier,
        agent_names=[t.__name__ for t in skill_tools],
        workspace_id=resolved_workspace_id,
    )

    strands_history = _to_strands_messages(messages) if messages else None

    # Load persisted agent state and normalize (fills any missing keys from defaults)
    _leaf_session = session_id.split("#")[-1] if session_id and "#" in session_id else session_id
    try:
        from .stores.session_store import load_agent_state
        _loaded_state = normalize(
            load_agent_state(_leaf_session, tenant_id, user_id) if _leaf_session else None
        )
    except Exception as _e:
        logger.warning("load_agent_state (streaming) failed (non-fatal): %s", _e)
        _loaded_state = normalize(None)
    _loaded_state["session_id"] = _leaf_session

    # Populate streaming context_frame now that eagle_state is loaded
    context_frame_stream["state"] = _loaded_state

    sse_hook = EagleSSEHookProvider(
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=_leaf_session,
    )

    # Summarizing conversation manager: on context overflow, summarize the oldest
    # 30% of messages (SDK default/recommended) while preserving the 10 most recent.
    _conversation_manager = SummarizingConversationManager(
        summary_ratio=0.3,
        preserve_recent_messages=10,
    )

    # Ensure Langfuse OTEL exporter is attached before Agent() caches its tracer
    _ensure_langfuse_exporter()

    supervisor = Agent(
        model=_get_model(),
        system_prompt=system_prompt,
        tools=skill_tools + service_tools,
        callback_handler=None,  # stream_async yields events directly
        messages=strands_history,
        hooks=[sse_hook],
        state=_loaded_state,
        conversation_manager=_conversation_manager,
        trace_attributes=to_trace_attrs(
            _loaded_state,
            tenant_id=tenant_id,
            user_id=user_id,
            tier=tier,
            session_id=session_id or "",
        ),
    )

    # Enrich user prompt with research reminders (like arti's <reminders> injection)
    _enriched_prompt = (
        f"{prompt}\n\n"
        "<reminders>"
        "Search and browse for current information if needed. "
        "If necessary, interleave tool calls with the think tool to perform complex analysis. "
        "Only update the workspace when necessary. "
        "Always include APA-style source citations with full URLs when sources are used."
        "</reminders>"
    )

    # Yield chunks via stream_async — SDK bridges sync→async internally
    full_text_parts: list[str] = []
    tools_called: list[str] = []
    _current_tool_id: str | None = None
    error_holder: list[Exception] = []
    agent_result = None

    def _drain_tool_results() -> list[dict]:
        """Drain tool results that were pushed by factory tools via result_queue."""
        drained: list[dict] = []
        while True:
            try:
                item = result_queue.get_nowait()
                name = item.get("name")
                if not name:
                    continue
                tools_called.append(name)
                drained.append(item)
            except asyncio.QueueEmpty:
                break
        return drained

    try:
        async for event in supervisor.stream_async(_enriched_prompt):
            # Drain tool results that may have been pushed by factory tools
            for tool_result_chunk in _drain_tool_results():
                yield tool_result_chunk

            # --- Text streaming (no bedrock_trace — too noisy per-token) ---
            data = event.get("data")
            if data and isinstance(data, str):
                full_text_parts.append(data)
                yield {"type": "text", "data": data}
                continue

            # --- Tool use start (ToolUseStreamEvent) ---
            current_tool = event.get("current_tool_use")
            if current_tool and isinstance(current_tool, dict):
                tool_id = current_tool.get("toolUseId", "")
                if tool_id and tool_id != _current_tool_id:
                    _current_tool_id = tool_id
                    tool_name = current_tool.get("name", "")
                    tools_called.append(tool_name)
                    yield {
                        "type": "tool_use",
                        "name": tool_name,
                        "input": current_tool.get("input", ""),
                        "tool_use_id": tool_id,
                    }
                    yield {"type": "bedrock_trace", "event": _sanitize_event(event)}
                continue

            # --- Bedrock contentBlockStart fallback ---
            raw_event = event.get("event", {})
            if isinstance(raw_event, dict):
                cbs = raw_event.get("contentBlockStart", {}).get("start", {}).get("toolUse")
                if cbs:
                    tool_id = cbs.get("toolUseId", "")
                    if tool_id != _current_tool_id:
                        _current_tool_id = tool_id
                        tool_name = cbs.get("name", "")
                        tools_called.append(tool_name)
                        yield {
                            "type": "tool_use",
                            "name": tool_name,
                            "tool_use_id": tool_id,
                        }
                        yield {"type": "bedrock_trace", "event": _sanitize_event(event)}
                    continue

                # --- Structural Bedrock events (messageStop, usage) ---
                if "messageStop" in raw_event:
                    yield {"type": "bedrock_trace", "event": _sanitize_event(event)}
                    continue
                if "metadata" in raw_event:
                    meta = raw_event.get("metadata", {})
                    if isinstance(meta, dict) and "usage" in meta:
                        yield {"type": "bedrock_trace", "event": _sanitize_event(event)}
                    continue

            # --- Agent result (final event) ---
            if "result" in event and hasattr(event.get("result"), "metrics"):
                agent_result = event["result"]

    except Exception as exc:
        error_holder.append(exc)
        logger.error("stream_async error: %s", exc)

    # Final drain of any remaining tool results
    for tool_result_chunk in _drain_tool_results():
        yield tool_result_chunk

    # Extract usage from result
    usage = {}
    if agent_result is not None:
        if not full_text_parts:
            try:
                final_text = str(agent_result)
                if final_text:
                    full_text_parts.append(final_text)
                    yield {"type": "text", "data": final_text}
            except Exception:
                pass
        try:
            metrics = getattr(agent_result, "metrics", None)
            if metrics:
                acc = getattr(metrics, "accumulated_usage", None)
                if acc and isinstance(acc, dict):
                    usage = acc
                else:
                    usage = {
                        "cycle_count": getattr(metrics, "cycle_count", 0),
                        "tools_called": len(tools_called),
                    }
                # Always inject cycle_count if available
                if "cycle_count" not in usage:
                    usage["cycle_count"] = getattr(metrics, "cycle_count", 0)
                # Extract per-tool metrics for token breakdown
                if hasattr(metrics, "tool_metrics") and metrics.tool_metrics:
                    tools_called = list(metrics.tool_metrics.keys())
                    try:
                        tm = {}
                        for tname, tdata in metrics.tool_metrics.items():
                            if hasattr(tdata, "__dict__"):
                                tm[tname] = {k: v for k, v in tdata.__dict__.items()
                                              if not k.startswith("_")}
                            elif isinstance(tdata, dict):
                                tm[tname] = tdata
                            else:
                                tm[tname] = str(tdata)
                        usage["tool_metrics"] = tm
                    except Exception:
                        pass
        except Exception:
            pass

    forced_doc = None
    if not error_holder:
        forced_doc = await _ensure_create_document_for_direct_request(
            prompt=prompt,
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            package_context=package_context,
            tools_called=tools_called,
        )
        if forced_doc is not None:
            tools_called.append("create_document")
            yield {"type": "tool_use", "name": "create_document"}
            yield {"type": "tool_result", "name": "create_document", "result": forced_doc["result"]}
            if not full_text_parts:
                summary = (
                    f"Generated a draft {forced_doc['doc_type'].replace('_', ' ')} document. "
                    "Open the document card to review or edit it."
                )
                full_text_parts.append(summary)
                yield {"type": "text", "data": summary}

    if error_holder:
        yield {"type": "error", "error": str(error_holder[0])}
    else:
        final_text = "".join(full_text_parts)
        if not final_text.strip():
            called = ", ".join(tools_called[:3]) if tools_called else "none"
            final_text = (
                "I completed the tool steps but did not receive a final answer text. "
                f"Tools called: {called}. Please retry your request."
            )
        yield {
            "type": "complete",
            "text": final_text,
            "tools_called": tools_called,
            "usage": usage,
            "agent_state": (
                agent_result.state
                if agent_result is not None and hasattr(agent_result, "state") and isinstance(getattr(agent_result, "state", None), dict)
                else _loaded_state
            ),
        }


async def sdk_query_single_skill(
    prompt: str,
    skill_name: str,
    tenant_id: str = "demo-tenant",
    user_id: str = "demo-user",
    tier: str = "advanced",
    model: str = None,
    max_turns: int = 5,
) -> AsyncGenerator[Any, None]:
    """Run a query directly against a single skill (no supervisor).

    Same signature as sdk_agentic_service.sdk_query_single_skill().
    Direct Agent call with skill content as system_prompt.

    Args:
        prompt: User's query
        skill_name: Skill key from SKILL_CONSTANTS
        tenant_id: Tenant identifier
        user_id: User identifier
        tier: Subscription tier
        model: Model override (unused -- shared model)
        max_turns: Max tool-use iterations (reserved)

    Yields:
        AssistantMessage and ResultMessage adapter objects
    """
    skill_key = SKILL_AGENT_REGISTRY.get(skill_name, {}).get("skill_key", skill_name)
    entry = PLUGIN_CONTENTS.get(skill_key)
    if not entry:
        raise ValueError(f"Skill not found: {skill_name} (key={skill_key})")
    skill_content = entry["body"]

    tenant_context = (
        f"Tenant: {tenant_id} | User: {user_id} | Tier: {tier}\n"
        f"You are operating as the {skill_name} specialist for this tenant.\n\n"
    )

    agent = Agent(
        model=_get_model(),
        system_prompt=tenant_context + skill_content,
        callback_handler=None,
    )

    result = agent(prompt)
    result_text = str(result)

    yield AssistantMessage(content=[TextBlock(text=result_text)])

    usage = {}
    try:
        metrics = getattr(result, "metrics", None)
        if metrics:
            acc = getattr(metrics, "accumulated_usage", None)
            if acc and isinstance(acc, dict):
                usage = acc
            else:
                usage = {"cycle_count": getattr(metrics, "cycle_count", 0)}
    except Exception:
        pass

    yield ResultMessage(result=result_text, usage=usage)
