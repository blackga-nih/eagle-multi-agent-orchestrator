"""Generate example output from document_agent for all 10 doc types.

Uses a shared mock conversation context (cloud migration acquisition)
and calls Bedrock for each doc type, saving outputs to test-reports/.

Usage: python server/tests/generate_doc_examples.py
"""
import json
import os
import sys
import time
from pathlib import Path

# Add server/ to path
_server_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)

from app.document_agent import (
    _load_template,
    _load_required_fields,
    _build_prompt,
    _parse_appendices,
    _parse_omission_table,
    _parse_justification_entries,
    _validate_required_fields,
    _extract_title,
    _SYSTEM_PROMPT,
)

# Shared mock context — a realistic cloud migration acquisition
MOCK_CONTEXT = """[USER]: We need to migrate 15 legacy on-premises applications to AWS GovCloud for the National Cancer Institute. This includes our clinical trial management system (CTMS), genomics data pipeline, and several internal collaboration tools.

[ASSISTANT]: I can help you plan this acquisition. What's your estimated budget and timeline?

[USER]: Budget is approximately $2.3 million over a 2-year period. We need FedRAMP Moderate authorization for all cloud services. The CTMS handles PHI/PII data so HIPAA compliance is mandatory. We've identified 3 potential vendors from our market research: Booz Allen Hamilton, Deloitte, and SAIC. All three hold CIO-SP3 contracts.

[ASSISTANT]: That's a well-defined requirement. Let me gather some details — what contract type are you considering, and is this full and open competition or are you using an existing vehicle?

[USER]: We're planning to use NITAAC CIO-SP3 as the contract vehicle. Contract type should be Time and Materials for the migration phase (uncertain scope) and Firm-Fixed-Price for ongoing managed services. We want a total small business set-aside since all three vendors qualify. The COR will be Dr. Sarah Chen from the Center for Biomedical Informatics.

[ASSISTANT]: I have enough context to generate the acquisition documents. Let me prepare them now.
"""

MOCK_STATE = """(no structured state — agent will infer from conversation)"""

OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "test-reports" / "doc-agent-examples"


def generate_example(doc_type: str, model) -> dict:
    """Generate one document example and return structured result."""
    template = _load_template(doc_type)
    req_fields = _load_required_fields(doc_type)

    prompt = _build_prompt(
        doc_type=doc_type,
        template_content=template,
        conversation_context=MOCK_CONTEXT,
        state_snapshot=MOCK_STATE,
        required_fields=req_fields,
        special_instructions="",
    )

    # Call Bedrock
    start = time.monotonic()
    messages = [{"role": "user", "content": [{"text": prompt}]}]
    try:
        response = model.converse(
            modelId=os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-20250514"),
            messages=messages,
            system=[{"text": _SYSTEM_PROMPT}],
            inferenceConfig={
                "maxTokens": 8192,
                "temperature": 0.3,
            },
        )
        output = response.get("output", {})
        message = output.get("message", {})
        content_blocks = message.get("content", [])
        text_parts = [b["text"] for b in content_blocks if "text" in b]
        content = "\n".join(text_parts)
    except Exception as exc:
        content = f"ERROR: {exc}"
    elapsed = time.monotonic() - start

    # Parse
    main_body, omissions_md, reasoning_md = _parse_appendices(content)
    omissions = _parse_omission_table(omissions_md)
    justifications = _parse_justification_entries(reasoning_md)
    required_sections = req_fields.get("required_sections", [])
    missing = _validate_required_fields(main_body, required_sections)
    title = _extract_title(content, doc_type)
    word_count = len(content.split())

    return {
        "doc_type": doc_type,
        "display_name": req_fields.get("display_name", doc_type),
        "title": title,
        "word_count": word_count,
        "elapsed_s": round(elapsed, 1),
        "content": content,
        "main_body_preview": main_body[:500] + "..." if len(main_body) > 500 else main_body,
        "omissions": omissions,
        "justifications": justifications,
        "missing_required": missing,
        "required_sections": required_sections,
        "appendix_a_raw": omissions_md,
        "appendix_b_raw": reasoning_md,
    }


def main():
    import boto3

    model = boto3.client("bedrock-runtime", region_name=os.getenv("AWS_REGION", "us-east-1"))

    doc_types = [
        "sow", "igce", "acquisition_plan", "justification", "market_research",
        "eval_criteria", "security_checklist", "section_508",
        "cor_certification", "contract_type_justification",
    ]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    results = []
    for i, dt in enumerate(doc_types, 1):
        print(f"\n[{i}/{len(doc_types)}] Generating {dt}...", flush=True)
        result = generate_example(dt, model)
        results.append(result)

        # Save individual file
        out_path = OUTPUT_DIR / f"{dt}_example.md"
        out_path.write_text(result["content"], encoding="utf-8")
        print(f"  -> {result['word_count']} words, {result['elapsed_s']}s, "
              f"{len(result['omissions'])} omissions, {len(result['justifications'])} justifications, "
              f"missing: {result['missing_required'] or 'none'}")

    # Print summary report
    print("\n" + "=" * 80)
    print("DOCUMENT AGENT EXAMPLE OUTPUT REPORT")
    print("=" * 80)

    for r in results:
        print(f"\n{'─' * 60}")
        print(f"  {r['display_name']} ({r['doc_type']})")
        print(f"  Title: {r['title']}")
        print(f"  Words: {r['word_count']}  |  Time: {r['elapsed_s']}s  |  Missing required: {r['missing_required'] or 'none'}")

        if r["omissions"]:
            print(f"\n  APPENDIX A — Omissions ({len(r['omissions'])} entries):")
            for o in r["omissions"]:
                print(f"    [{o['status']:>8}] {o['section']}: {o['reason']}")
                if o.get("info_needed"):
                    print(f"             -> Need: {o['info_needed']}")

        if r["justifications"]:
            print(f"\n  APPENDIX B — Justifications ({len(r['justifications'])} entries):")
            for j in r["justifications"]:
                reasoning_preview = j["reasoning"][:120] + "..." if len(j["reasoning"]) > 120 else j["reasoning"]
                print(f"    {j['decision']}")
                print(f"      {reasoning_preview}")

    # Save full JSON report
    report_path = OUTPUT_DIR / "full_report.json"
    # Strip full content from JSON to keep it manageable
    report_data = []
    for r in results:
        entry = {k: v for k, v in r.items() if k not in ("content", "main_body_preview", "appendix_a_raw", "appendix_b_raw")}
        report_data.append(entry)
    report_path.write_text(json.dumps(report_data, indent=2), encoding="utf-8")

    print(f"\n\nFull documents saved to: {OUTPUT_DIR}/")
    print(f"JSON report: {report_path}")

    total_words = sum(r["word_count"] for r in results)
    total_time = sum(r["elapsed_s"] for r in results)
    total_omissions = sum(len(r["omissions"]) for r in results)
    total_justifications = sum(len(r["justifications"]) for r in results)
    print(f"\nTotals: {total_words} words, {total_time:.0f}s, "
          f"{total_omissions} omissions, {total_justifications} justifications")


if __name__ == "__main__":
    main()
