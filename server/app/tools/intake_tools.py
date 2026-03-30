"""Active intake status and workflow handlers."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime

from botocore.exceptions import BotoCoreError, ClientError

from ..db_client import get_dynamodb, get_s3
from ..session_scope import extract_user_id


WORKFLOW_STAGES = [
    {
        "id": "requirements",
        "name": "Requirements Gathering",
        "description": "Collect acquisition details: what, why, when, how much",
        "fields": [
            "title",
            "description",
            "estimated_value",
            "period_of_performance",
            "urgency",
        ],
        "next_actions": [
            "Describe the acquisition need",
            "Provide estimated value",
            "Specify timeline",
        ],
    },
    {
        "id": "compliance",
        "name": "Compliance Check",
        "description": "Verify FAR/DFAR requirements and acquisition thresholds",
        "fields": [
            "acquisition_type",
            "threshold",
            "competition_required",
            "far_citations",
            "small_business",
        ],
        "next_actions": [
            "Search FAR for applicable regulations",
            "Determine acquisition type",
            "Check competition requirements",
        ],
    },
    {
        "id": "documents",
        "name": "Document Generation",
        "description": "Generate required acquisition documents",
        "fields": [
            "sow_generated",
            "igce_generated",
            "market_research_generated",
            "justification_generated",
        ],
        "next_actions": [
            "Generate Statement of Work",
            "Generate IGCE",
            "Generate Market Research",
        ],
    },
    {
        "id": "review",
        "name": "Review & Submit",
        "description": "Final review and package submission",
        "fields": ["reviewed_by", "review_notes", "submitted_at", "approval_status"],
        "next_actions": [
            "Review all documents",
            "Add any notes",
            "Submit for approval",
        ],
    },
]


def exec_get_intake_status(
    params: dict, tenant_id: str, session_id: str | None = None
) -> dict:
    """Check intake status — queries DynamoDB and S3 for completeness."""
    intake_id = params.get("intake_id", "")
    user_id = extract_user_id(session_id)

    existing_docs = []
    doc_types_found = set()
    try:
        s3 = get_s3()
        resp = s3.list_objects_v2(
            Bucket=os.getenv("S3_BUCKET", "eagle-documents-695681773636-dev"),
            Prefix=f"eagle/{tenant_id}/{user_id}/documents/",
            MaxKeys=50,
        )
        for obj in resp.get("Contents", []):
            key = obj["Key"]
            name = key.split("/")[-1]
            existing_docs.append(
                {
                    "key": key,
                    "name": name,
                    "size": obj["Size"],
                    "last_modified": obj["LastModified"].isoformat(),
                }
            )
            for doc_type in (
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
            ):
                if doc_type in name.lower():
                    doc_types_found.add(doc_type)
    except (ClientError, BotoCoreError):
        pass

    intake_records = []
    try:
        from boto3.dynamodb.conditions import Key as DDBKey

        table = get_dynamodb().Table("eagle")
        resp = table.query(
            KeyConditionExpression=DDBKey("PK").eq(f"INTAKE#{tenant_id}")
        )
        intake_records = [_serialize_ddb_item(item) for item in resp.get("Items", [])]
    except (ClientError, BotoCoreError):
        pass

    required_docs = {
        "sow": "Statement of Work",
        "igce": "Independent Government Cost Estimate",
        "market_research": "Market Research Report",
        "justification": "Justification & Approval (if sole source)",
        "acquisition_plan": "Acquisition Plan",
        "eval_criteria": "Evaluation Criteria",
        "security_checklist": "IT Security Checklist",
        "section_508": "Section 508 Compliance Statement",
        "cor_certification": "COR Certification",
        "contract_type_justification": "Contract Type Justification",
    }
    conditional_docs = {
        "justification",
        "eval_criteria",
        "security_checklist",
        "section_508",
        "contract_type_justification",
    }

    completed = []
    pending = []
    for doc_key, doc_name in required_docs.items():
        if doc_key in doc_types_found:
            completed.append(
                {"document": doc_name, "type": doc_key, "status": "✅ Complete"}
            )
        elif doc_key in conditional_docs:
            pending.append(
                {
                    "document": doc_name,
                    "type": doc_key,
                    "status": "🔲 Conditional",
                    "priority": "Conditional",
                }
            )
        else:
            pending.append(
                {
                    "document": doc_name,
                    "type": doc_key,
                    "status": "🔲 Not Started",
                    "priority": "High",
                }
            )

    total = len(required_docs) - len(conditional_docs)
    done = len([item for item in completed if item["type"] not in conditional_docs])
    pct = int((done / total) * 100) if total > 0 else 0

    return {
        "intake_id": intake_id or f"EAGLE-{tenant_id}-{int(time.time()) % 100000:05d}",
        "tenant_id": tenant_id,
        "completion_pct": f"{pct}%",
        "documents_completed": completed,
        "documents_pending": pending,
        "existing_files": existing_docs,
        "intake_records": intake_records[:10],
        "next_action": pending[0]["document"]
        if pending
        else "All required documents complete!",
        "estimated_completion": "Depends on remaining document generation",
    }


def exec_intake_workflow(params: dict, tenant_id: str) -> dict:
    """Manage the acquisition intake workflow with stage-based progression."""
    action = params.get("action", "status")
    intake_id = params.get("intake_id")
    data = params.get("data", {})
    workflows = _load_workflow(tenant_id)

    if action == "start":
        new_id = f"EAGLE-{tenant_id[:8]}-{int(time.time()) % 100000:05d}"
        workflows[new_id] = {
            "intake_id": new_id,
            "tenant_id": tenant_id,
            "created_at": datetime.utcnow().isoformat(),
            "current_stage": 0,
            "stage_name": WORKFLOW_STAGES[0]["name"],
            "status": "in_progress",
            "stages_completed": [],
            "data": data,
        }
        _save_workflow(tenant_id, workflows)
        stage = WORKFLOW_STAGES[0]
        return {
            "action": "started",
            "intake_id": new_id,
            "message": f"🚀 New intake workflow started: {new_id}",
            "current_stage": {
                "number": 1,
                "name": stage["name"],
                "description": stage["description"],
            },
            "next_actions": stage["next_actions"],
            "fields_to_collect": stage["fields"],
            "tip": "Provide the acquisition details, and I'll guide you through each step.",
        }

    if action == "status":
        if not intake_id:
            if not workflows:
                return {
                    "message": "No active intake workflows. Use action='start' to begin a new intake.",
                    "hint": "Try: 'Start a new intake for cloud services'",
                }
            intake_id = list(workflows.keys())[-1]
        workflow = workflows.get(intake_id)
        if not workflow:
            return {"error": f"Intake {intake_id} not found"}
        current_idx = workflow.get("current_stage", 0)
        stage = (
            WORKFLOW_STAGES[current_idx] if current_idx < len(WORKFLOW_STAGES) else None
        )
        progress_bar = "".join(
            ["✅" if i < current_idx else "🔲" for i in range(len(WORKFLOW_STAGES))]
        )
        return {
            "intake_id": intake_id,
            "status": workflow.get("status", "in_progress"),
            "progress": f"{current_idx}/{len(WORKFLOW_STAGES)} stages",
            "progress_bar": progress_bar,
            "current_stage": {
                "number": current_idx + 1,
                "name": stage["name"] if stage else "Complete",
                "description": stage["description"] if stage else "All stages complete",
            }
            if stage
            else {"name": "Complete", "description": "Workflow finished"},
            "stages_completed": workflow.get("stages_completed", []),
            "next_actions": stage["next_actions"]
            if stage
            else ["Submit for final approval"],
            "data_collected": workflow.get("data", {}),
            "created_at": workflow.get("created_at"),
        }

    if action == "advance":
        if not intake_id:
            if not workflows:
                return {
                    "error": "No active workflow. Start one first with action='start'"
                }
            intake_id = list(workflows.keys())[-1]
        workflow = workflows.get(intake_id)
        if not workflow:
            return {"error": f"Intake {intake_id} not found"}
        current_idx = workflow.get("current_stage", 0)
        if data:
            workflow.setdefault("data", {}).update(data)
        completed_stage = WORKFLOW_STAGES[current_idx]["name"]
        workflow.setdefault("stages_completed", []).append(
            {"stage": completed_stage, "completed_at": datetime.utcnow().isoformat()}
        )
        next_idx = current_idx + 1
        if next_idx >= len(WORKFLOW_STAGES):
            workflow["current_stage"] = next_idx
            workflow["status"] = "ready_for_review"
            workflow["stage_name"] = "Complete"
            _save_workflow(tenant_id, workflows)
            return {
                "action": "workflow_complete",
                "intake_id": intake_id,
                "message": "🎉 All stages complete! Intake package ready for review.",
                "stages_completed": workflow["stages_completed"],
                "data_collected": workflow["data"],
                "next_steps": [
                    "Review all generated documents",
                    "Use get_intake_status to see document checklist",
                    "Submit for supervisor approval",
                ],
            }
        workflow["current_stage"] = next_idx
        workflow["stage_name"] = WORKFLOW_STAGES[next_idx]["name"]
        _save_workflow(tenant_id, workflows)
        next_stage = WORKFLOW_STAGES[next_idx]
        progress_bar = "".join(
            ["✅" if i <= current_idx else "🔲" for i in range(len(WORKFLOW_STAGES))]
        )
        return {
            "action": "advanced",
            "intake_id": intake_id,
            "message": f"✅ Completed: {completed_stage}",
            "progress": f"{next_idx}/{len(WORKFLOW_STAGES)} stages",
            "progress_bar": progress_bar,
            "current_stage": {
                "number": next_idx + 1,
                "name": next_stage["name"],
                "description": next_stage["description"],
            },
            "next_actions": next_stage["next_actions"],
            "fields_to_collect": next_stage["fields"],
        }

    if action == "complete":
        if not intake_id:
            if not workflows:
                return {"error": "No active workflow"}
            intake_id = list(workflows.keys())[-1]
        workflow = workflows.get(intake_id)
        if not workflow:
            return {"error": f"Intake {intake_id} not found"}
        workflow["status"] = "submitted"
        workflow["submitted_at"] = datetime.utcnow().isoformat()
        if data:
            workflow.setdefault("data", {}).update(data)
        _save_workflow(tenant_id, workflows)
        return {
            "action": "submitted",
            "intake_id": intake_id,
            "message": "📤 Intake package submitted for approval!",
            "submitted_at": workflow["submitted_at"],
            "status": "submitted",
            "summary": {
                "stages_completed": len(workflow.get("stages_completed", [])),
                "data_fields": len(workflow.get("data", {})),
            },
            "next_steps": [
                "Supervisor will review the package",
                "You'll be notified of approval status",
                "Estimated review time: 2-3 business days",
            ],
        }

    if action == "reset":
        if intake_id and intake_id in workflows:
            del workflows[intake_id]
            _save_workflow(tenant_id, workflows)
            return {
                "action": "reset",
                "message": f"Workflow {intake_id} has been reset",
            }
        workflows.clear()
        _save_workflow(tenant_id, workflows)
        return {"action": "reset", "message": "All workflows cleared"}

    return {
        "error": f"Unknown action: {action}",
        "valid_actions": ["start", "advance", "status", "complete", "reset"],
    }


def _workflow_file(tenant_id: str) -> str:
    return f"/tmp/eagle_workflow_{tenant_id}.json"


def _load_workflow(tenant_id: str) -> dict:
    try:
        with open(_workflow_file(tenant_id), "r") as handle:
            return json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_workflow(tenant_id: str, state: dict) -> None:
    with open(_workflow_file(tenant_id), "w") as handle:
        json.dump(state, handle, indent=2, default=str)


def _serialize_ddb_item(item: dict) -> dict:
    from decimal import Decimal

    result = {}
    for key, value in item.items():
        if isinstance(value, Decimal):
            result[key] = float(value) if value % 1 else int(value)
        else:
            result[key] = value
    return result
