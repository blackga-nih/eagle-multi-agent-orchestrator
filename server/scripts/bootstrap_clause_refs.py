"""
bootstrap_clause_refs.py

Reads each JSON file in eagle-plugin/data/template-metadata/ (skipping _index.json),
extracts FAR citations from section titles via regex, cross-references the
far-database.json for titles, adds category-level template_level_clauses from
known FAR part mappings, and writes sidecar JSON files to
eagle-plugin/data/template-clause-references/.

Usage:
    python server/scripts/bootstrap_clause_refs.py
"""

import json
import os
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Paths (resolved relative to this script's location so the script can be
# run from any working directory as long as the repo layout is intact)
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent  # server/scripts -> server -> repo root
METADATA_DIR = REPO_ROOT / "eagle-plugin" / "data" / "template-metadata"
FAR_DB_PATH = REPO_ROOT / "eagle-plugin" / "data" / "far-database.json"
OUTPUT_DIR = REPO_ROOT / "eagle-plugin" / "data" / "template-clause-references"

# ---------------------------------------------------------------------------
# Category → template-level clauses mapping
# Entries without clauses are represented as empty lists.
# HHSAR references use the same dict shape as FAR clauses.
# ---------------------------------------------------------------------------
CATEGORY_TEMPLATE_LEVEL_CLAUSES: dict[str, list[dict]] = {
    "acquisition_plan": [
        {"clause_number": "FAR 7.103", "title": "Agency-Head Responsibilities", "applicability": "required"},
        {"clause_number": "FAR 7.104", "title": "General Procedures", "applicability": "required"},
        {"clause_number": "FAR 7.105", "title": "Contents of Written Acquisition Plans", "applicability": "required"},
    ],
    "sow": [
        {"clause_number": "FAR 37.6", "title": "Performance-Based Acquisition", "applicability": "required"},
    ],
    "igce": [
        {"clause_number": "FAR 36.203", "title": "Government Estimate of Construction Costs", "applicability": "required"},
        {"clause_number": "FAR 15.404", "title": "Proposal Analysis", "applicability": "required"},
    ],
    "justification": [
        {"clause_number": "FAR 6.302", "title": "Circumstances Permitting Other Than Full and Open Competition", "applicability": "required"},
        {"clause_number": "FAR 6.303", "title": "Justifications (J&A)", "applicability": "required"},
        {"clause_number": "FAR 6.304", "title": "Approval of Justifications", "applicability": "required"},
    ],
    "market_research": [
        {"clause_number": "FAR 10.001", "title": "Policy — Market Research", "applicability": "required"},
        {"clause_number": "FAR 10.002", "title": "Procedures for Market Research", "applicability": "required"},
    ],
    "son_products": [
        {"clause_number": "FAR 11.002", "title": "Policy for Describing Agency Needs", "applicability": "required"},
    ],
    "son_services": [
        {"clause_number": "FAR 11.002", "title": "Policy for Describing Agency Needs", "applicability": "required"},
    ],
    "buy_american": [
        {"clause_number": "FAR 25.103", "title": "Exceptions — Buy American", "applicability": "required"},
    ],
    "subk_plan": [
        {"clause_number": "FAR 19.702", "title": "Statutory Requirements for Subcontracting Plans", "applicability": "required"},
    ],
    "cor_certification": [
        {"clause_number": "FAR 1.602-2", "title": "Responsibilities of Contracting Officers", "applicability": "required"},
        {"clause_number": "FAR 42.202", "title": "Assignment of Contract Administration", "applicability": "required"},
    ],
    "conference_request": [
        {"clause_number": "HHSAR 370.101", "title": "Conference Approval Requirements", "applicability": "required"},
    ],
    "conference_waiver": [
        {"clause_number": "HHSAR 370.102", "title": "Conference Waiver Requirements", "applicability": "required"},
    ],
    "mandatory_use_waiver": [
        {"clause_number": "FAR 8.002", "title": "Priorities for Use of Mandatory Sources", "applicability": "required"},
        {"clause_number": "FAR 8.004", "title": "Use of Other Sources", "applicability": "required"},
    ],
    "gfp_form": [
        {"clause_number": "FAR 45.102", "title": "Policy for Government Property", "applicability": "required"},
    ],
    "bpa_call_order": [
        {"clause_number": "FAR 8.405", "title": "Ordering Procedures for Federal Supply Schedules", "applicability": "required"},
    ],
    "quotation_abstract": [
        {"clause_number": "FAR 13.106", "title": "Soliciting Competition, Evaluation of Quotations or Offers", "applicability": "required"},
    ],
    "receiving_report": [
        {"clause_number": "FAR 46.501", "title": "General — Acceptance", "applicability": "required"},
    ],
    "srb_request": [
        {"clause_number": "HHSAR 307.104", "title": "Systems Review Board Requirements", "applicability": "required"},
    ],
    "technical_questionnaire": [
        {"clause_number": "FAR 7.104", "title": "General Procedures", "applicability": "required"},
    ],
    "subk_review": [
        {"clause_number": "FAR 19.705", "title": "Responsibilities of the Contracting Officer", "applicability": "required"},
    ],
    "exemption_determination": [
        {"clause_number": "FAR 5.202", "title": "Exceptions — Synopsizing Contract Actions", "applicability": "required"},
    ],
    "promotional_item": [],
    "reference_guide": [],
}

# ---------------------------------------------------------------------------
# FAR citation regex
# Matches patterns like:
#   FAR 7.105(a)(2)   FAR7.105(a)(2)   FAR 7.105   FAR 36.203
# The regex handles optional space between "FAR" and the citation number,
# plus optional suffix characters for sub-paragraphs and hyphens.
# ---------------------------------------------------------------------------
FAR_PATTERN = re.compile(
    r"(?:FAR\s?)(\d+\.\d+[\w\-().,]*)",
    re.IGNORECASE,
)

# Also capture the full token including "FAR " prefix for display
FAR_FULL_PATTERN = re.compile(
    r"(FAR\s?\d+\.\d+[\w\-().,]*)",
    re.IGNORECASE,
)


def load_far_database(path: Path) -> dict[str, str]:
    """Return a dict mapping section string -> title, e.g. '7.105' -> 'Contents of Written Acquisition Plans'."""
    with open(path, encoding="utf-8") as f:
        entries = json.load(f)
    return {entry["section"]: entry["title"] for entry in entries}


def normalise_citation(raw: str) -> str:
    """
    Normalise a raw FAR citation to canonical form.

    Examples:
        'FAR7.105(a)(2)' -> 'FAR 7.105(a)(2)'
        'far 7.105(a)(2),' -> 'FAR 7.105(a)(2)'
    """
    # Strip trailing punctuation
    raw = raw.rstrip(".,;")
    # Ensure exactly one space after FAR
    normalised = re.sub(r"(?i)FAR\s*", "FAR ", raw, count=1)
    return normalised


def resolve_title(citation: str, far_db: dict[str, str]) -> str:
    """
    Given a full citation like 'FAR 7.105(a)(2)', extract the base section
    (e.g. '7.105') and look it up in the FAR database.  Return the DB title
    if found, otherwise return an empty string so callers can decide a default.
    """
    m = FAR_PATTERN.search(citation)
    if not m:
        return ""
    raw_section = m.group(1)
    # Base section is everything up to the first '(' or end
    base = re.split(r"[(\-]", raw_section)[0]
    # Try exact match, then base match
    return far_db.get(raw_section, far_db.get(base, ""))


def extract_clauses_from_title(section_title: str, far_db: dict[str, str]) -> list[dict]:
    """
    Find all FAR citations embedded in a section title and return a list of
    clause dicts suitable for the sidecar section_clause_map entry.
    """
    matches = FAR_FULL_PATTERN.findall(section_title)
    clauses = []
    seen = set()
    for raw_match in matches:
        citation = normalise_citation(raw_match)
        if citation in seen:
            continue
        seen.add(citation)
        title = resolve_title(citation, far_db)
        clauses.append({
            "clause_number": citation,
            "title": title,
            "applicability": "required",
        })
    return clauses


def extract_far_parts(clauses: list[dict]) -> list[str]:
    """Collect unique FAR part numbers (e.g. '7', '36') from a list of clause dicts."""
    parts = set()
    for clause in clauses:
        cn = clause.get("clause_number", "")
        m = re.search(r"FAR\s+(\d+)\.", cn, re.IGNORECASE)
        if m:
            parts.add(m.group(1))
    return sorted(parts, key=lambda x: int(x))


def build_sidecar(metadata: dict, far_db: dict[str, str]) -> dict:
    """Build the full sidecar JSON structure for one template metadata file."""
    template_filename = metadata["filename"]
    category = metadata.get("category", "")
    variant = metadata.get("variant", "")
    sections = metadata.get("sections", [])

    # Build section_clause_map: section number -> {section_title, clauses}
    section_clause_map: dict[str, dict] = {}
    all_section_clauses: list[dict] = []

    for section in sections:
        section_num = str(section.get("number", ""))
        section_title = section.get("title", "")
        clauses = extract_clauses_from_title(section_title, far_db)
        section_clause_map[section_num] = {
            "section_title": section_title,
            "clauses": clauses,
        }
        all_section_clauses.extend(clauses)

    # Template-level clauses from category mapping
    template_level_clauses = CATEGORY_TEMPLATE_LEVEL_CLAUSES.get(category, [])

    # Total clause count = section clauses + template-level clauses (deduplicated by citation)
    all_clauses = all_section_clauses + template_level_clauses
    seen_citations: set[str] = set()
    unique_clauses: list[dict] = []
    for c in all_clauses:
        cn = c["clause_number"]
        if cn not in seen_citations:
            seen_citations.add(cn)
            unique_clauses.append(c)

    total_clauses = len(unique_clauses)
    far_parts_covered = extract_far_parts(unique_clauses)

    return {
        "template_filename": template_filename,
        "category": category,
        "variant": variant,
        "section_clause_map": section_clause_map,
        "template_level_clauses": template_level_clauses,
        "total_clauses": total_clauses,
        "far_parts_covered": far_parts_covered,
    }


def run() -> None:
    print(f"Loading FAR database from: {FAR_DB_PATH}")
    far_db = load_far_database(FAR_DB_PATH)
    print(f"  Loaded {len(far_db)} FAR sections.")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {OUTPUT_DIR}\n")

    metadata_files = sorted(METADATA_DIR.glob("*.json"))
    processed = 0
    skipped = 0

    for meta_path in metadata_files:
        if meta_path.name == "_index.json":
            print(f"  [skip] {meta_path.name}")
            skipped += 1
            continue

        with open(meta_path, encoding="utf-8") as f:
            try:
                metadata = json.load(f)
            except json.JSONDecodeError as exc:
                print(f"  [ERROR] Could not parse {meta_path.name}: {exc}", file=sys.stderr)
                skipped += 1
                continue

        sidecar = build_sidecar(metadata, far_db)

        # Sidecar filename mirrors the metadata filename exactly
        out_path = OUTPUT_DIR / meta_path.name
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(sidecar, f, indent=2, ensure_ascii=False)

        clause_summary = (
            f"{sidecar['total_clauses']} clauses, "
            f"parts: {sidecar['far_parts_covered'] if sidecar['far_parts_covered'] else 'none'}"
        )
        print(f"  [ok] {meta_path.name} -> {out_path.name}  ({clause_summary})")
        processed += 1

    print(f"\nDone. Processed: {processed}, Skipped: {skipped}")
    print(f"Sidecar files written to: {OUTPUT_DIR}")


if __name__ == "__main__":
    run()
