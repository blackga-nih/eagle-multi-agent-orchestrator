"""
EAGLE Strands Agent Components

Modular components for the Strands-based agentic service.
"""

# Core modules that don't require strands SDK
from .messages import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock
from .package_state import build_end_of_turn_state, build_state_updates, emit_package_state
from .prompt_utils import (
    DOC_TYPE_HINTS,
    DOC_TYPE_LABELS,
    build_scoped_session_id,
    extract_context_data_from_prompt,
    extract_document_context_from_prompt,
    extract_user_request_from_prompt,
    fast_path_title,
    infer_doc_type_from_prompt,
    is_document_generation_request,
    normalize_prompt,
    should_use_fast_document_path,
)
from .registry import (
    PLUGIN_DIR,
    SKILL_AGENT_REGISTRY,
    build_registry,
    load_plugin_config,
    truncate_skill,
)
from .supervisor import build_supervisor_prompt
from .telemetry import build_trace_attrs, ensure_langfuse_exporter
from .tool_schemas import EAGLE_TOOLS

# Lazy imports for modules that require strands SDK
# These will fail at import time if strands is not installed,
# but allow other modules to be imported successfully.
try:
    from .fast_path import (
        ensure_create_document_for_direct_request,
        maybe_fast_path_document_generation,
    )
    from .model import MODEL, TIER_BUDGETS, TIER_TOOLS, shared_model
    from .service_tools import (
        build_all_service_tools,
        build_kb_service_tools,
        build_service_tools,
        build_skill_tools,
        build_subagent_kb_tools,
        make_list_skills_tool,
        make_load_data_tool,
        make_load_skill_tool,
        make_subagent_tool,
    )

    _STRANDS_AVAILABLE = True
except ImportError:
    _STRANDS_AVAILABLE = False
    # Provide None placeholders for unavailable imports
    MODEL = None
    TIER_BUDGETS = None
    TIER_TOOLS = None
    shared_model = None
    ensure_create_document_for_direct_request = None
    maybe_fast_path_document_generation = None
    build_all_service_tools = None
    build_kb_service_tools = None
    build_service_tools = None
    build_skill_tools = None
    build_subagent_kb_tools = None
    make_list_skills_tool = None
    make_load_data_tool = None
    make_load_skill_tool = None
    make_subagent_tool = None


__all__ = [
    # Messages
    "AssistantMessage",
    "ResultMessage",
    "TextBlock",
    "ToolUseBlock",
    # Telemetry
    "build_trace_attrs",
    "ensure_langfuse_exporter",
    # Model (requires strands)
    "MODEL",
    "TIER_BUDGETS",
    "TIER_TOOLS",
    "shared_model",
    # Registry
    "PLUGIN_DIR",
    "SKILL_AGENT_REGISTRY",
    "build_registry",
    "load_plugin_config",
    "truncate_skill",
    # Prompt utils
    "DOC_TYPE_HINTS",
    "DOC_TYPE_LABELS",
    "build_scoped_session_id",
    "extract_context_data_from_prompt",
    "extract_document_context_from_prompt",
    "extract_user_request_from_prompt",
    "fast_path_title",
    "infer_doc_type_from_prompt",
    "is_document_generation_request",
    "normalize_prompt",
    "should_use_fast_document_path",
    # Package state
    "build_end_of_turn_state",
    "build_state_updates",
    "emit_package_state",
    # Fast path (requires strands)
    "ensure_create_document_for_direct_request",
    "maybe_fast_path_document_generation",
    # Service tools (requires strands)
    "build_all_service_tools",
    "build_kb_service_tools",
    "build_service_tools",
    "build_skill_tools",
    "build_subagent_kb_tools",
    "make_list_skills_tool",
    "make_load_data_tool",
    "make_load_skill_tool",
    "make_subagent_tool",
    # Supervisor
    "build_supervisor_prompt",
    # Tool schemas
    "EAGLE_TOOLS",
    # Availability flag
    "_STRANDS_AVAILABLE",
]
