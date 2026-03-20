"""
EAGLE Strands Tool Schemas

Anthropic tool_use format schemas for health/status endpoints.
These do NOT drive the Strands agent (which uses @tool functions).
"""

from ..tools.knowledge_tools import KNOWLEDGE_FETCH_TOOL, KNOWLEDGE_SEARCH_TOOL

EAGLE_TOOLS: list[dict] = [
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
            "summaries, and s3_keys for full document retrieval. After receiving "
            "results, call knowledge_fetch on s3_keys to read the full document."
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
        "name": "create_document",
        "description": (
            "Generate acquisition documents including SOW, IGCE, Market Research, "
            "J&A, Acquisition Plan, Evaluation Criteria, Security Checklist, "
            "Section 508 Statement, COR Certification, Contract Type "
            "Justification, Statement of Need, Buy American DF, Subcontracting Plan, "
            "and Conference Request. Documents are saved to S3. "
            "Each doc_type has a defined section structure — fill EVERY section."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "doc_type": {
                    "type": "string",
                    "enum": [
                        "sow",
                        "igce",
                        "market_research",
                        "justification",
                        "acquisition_plan",
                        "eval_criteria",
                        "security_checklist",
                        "section_508",
                        "cor_certification",
                        "contract_type_justification",
                        "son_products",
                        "son_services",
                        "buy_american",
                        "subk_plan",
                        "conference_request",
                    ],
                    "description": "Type of acquisition document to generate",
                },
                "title": {
                    "type": "string",
                    "description": "Descriptive document title including the program or acquisition name (e.g. 'SOW - Cloud Computing Services for NCI Research Portal' or 'IGCE - IT Support Services FY2026'). Never use a generic type label alone.",
                },
                "content": {
                    "type": "string",
                    "description": (
                        "Full document content as markdown. Write complete, "
                        "section-by-section content using the conversation context "
                        "before calling this tool. This becomes the saved document body. "
                        "Cover ALL sections defined in the template schema."
                    ),
                },
                "data": {
                    "type": "object",
                    "description": "Document-specific fields (description, estimated_value, period_of_performance, competition, contract_type, etc.) for template population.",
                },
            },
            "required": ["doc_type", "title"],
        },
    },
    {
        "name": "edit_docx_document",
        "description": (
            "Apply targeted edits to an existing DOCX document in S3 using "
            "python-docx. Use this to preserve Word formatting while replacing "
            "specific existing text in the document."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "document_key": {
                    "type": "string",
                    "description": "Full S3 key for the target .docx document",
                },
                "edits": {
                    "type": "array",
                    "description": "Exact text replacements to apply",
                    "items": {
                        "type": "object",
                        "properties": {
                            "search_text": {
                                "type": "string",
                                "description": "Exact current text to find in the DOCX preview",
                            },
                            "replacement_text": {
                                "type": "string",
                                "description": "Replacement text to apply while preserving formatting",
                            },
                        },
                        "required": ["search_text", "replacement_text"],
                    },
                },
                "checkbox_edits": {
                    "type": "array",
                    "description": "Optional checkbox toggles using visible checkbox label text from the DOCX preview",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label_text": {
                                "type": "string",
                                "description": "Visible checkbox label text from the preview",
                            },
                            "checked": {
                                "type": "boolean",
                                "description": "Whether the checkbox should be checked",
                            },
                        },
                        "required": ["label_text", "checked"],
                    },
                },
            },
            "required": ["document_key"],
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
]
