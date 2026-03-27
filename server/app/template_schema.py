"""Template Schema — Parse, guide, and validate document template sections.

Extracts structured section metadata from both:
  - Legacy markdown schema templates (eagle-plugin/data/templates/*.md)
  - Extracted JSON metadata (eagle-plugin/data/template-metadata/*.json)

Provides:
  - parse_template_schema(): Parse markdown into TemplateSchema
  - load_from_json(): Load schema from extracted JSON metadata
  - load_template_schemas(): Auto-discover all schemas
  - build_section_guidance(): Build concise AI prompt text
  - validate_completeness(): Check generated content against schema
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("eagle.template_schema")

# ── Paths ──
_PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent / "eagle-plugin"
TEMPLATES_DIR = _PLUGIN_ROOT / "data" / "templates"
METADATA_DIR = _PLUGIN_ROOT / "data" / "template-metadata"
CLAUSE_REFS_DIR = _PLUGIN_ROOT / "data" / "template-clause-references"

# Markdown template filename → doc_type mapping
_MD_FILENAME_TO_DOCTYPE = {
    "sow-template.md": "sow",
    "igce-template.md": "igce",
    "acquisition-plan-template.md": "acquisition_plan",
    "market-research-template.md": "market_research",
    "justification-template.md": "justification",
}


# ── Data Models ──


@dataclass
class SectionField:
    """A placeholder field within a template section."""

    name: str
    required: bool = True
    field_type: str = "text"  # "text" | "list" | "table" | "checkbox"


@dataclass
class ClauseReference:
    """A FAR/DFARS/HHSAR clause citation on a template or section."""

    clause_number: str  # "FAR 52.219-9" or "FAR 19.702"
    title: str  # "Small Business Subcontracting Plan"
    applicability: str = "required"  # "required" | "conditional" | "recommended"
    condition: Optional[str] = None  # When conditional: "contract_value > 750000"
    note: Optional[str] = None


@dataclass
class TemplateSection:
    """A section within a document template."""

    number: str  # "1", "1.1", "PART 1"
    title: str  # "BACKGROUND AND PURPOSE"
    description: str = ""  # First paragraph after heading (auto-extracted)
    fields: list[SectionField] = field(default_factory=list)
    subsections: list[TemplateSection] = field(default_factory=list)
    has_table: bool = False
    clause_references: list[ClauseReference] = field(default_factory=list)


@dataclass
class TemplateSchema:
    """Complete schema for a document template."""

    doc_type: str
    title: str
    sections: list[TemplateSection] = field(default_factory=list)
    total_fields: int = 0
    required_fields: int = 0
    template_level_clauses: list[ClauseReference] = field(default_factory=list)
    total_clause_references: int = 0


@dataclass
class CompletenessReport:
    """Result of validating document content against its schema."""

    doc_type: str
    total_sections: int
    filled_sections: int
    missing_sections: list[str] = field(default_factory=list)
    completeness_pct: float = 0.0
    is_complete: bool = False


@dataclass
class ClauseCoverageReport:
    """Result of analyzing clause coverage for a template."""

    doc_type: str
    total_clauses_referenced: int
    far_parts_covered: list[str]
    sections_with_clauses: int
    sections_without_clauses: int
    clause_list: list[dict] = field(default_factory=list)


# ── Markdown Parser ──

# Patterns for section headings
_HEADING_RE = re.compile(r"^(#{2,3})\s+(.+)$", re.MULTILINE)
_PART_RE = re.compile(
    r"^(#{2,3})\s+(?:PART\s+)?(\d+(?:\.\d+)*)[:\s.\-)]+\s*(.+)$", re.MULTILINE
)
_NUMBERED_RE = re.compile(
    r"^(#{2,3})\s+(\d+(?:\.\d+)*)[.:\s)\-]+\s*(.+)$", re.MULTILINE
)
_TASK_RE = re.compile(r"^(#{2,3})\s+Task\s+(\d+)[:\s]+\s*(.+)$", re.MULTILINE)
_PLACEHOLDER_RE = re.compile(r"\{\{(\w+)\}\}")
_TABLE_RE = re.compile(r"^\|.+\|.+\|", re.MULTILINE)


def parse_template_schema(markdown: str, doc_type: str) -> TemplateSchema:
    """Parse a markdown template into a TemplateSchema.

    Splits on ## headings, extracts {{PLACEHOLDER}} names per section,
    detects tables (|) and checkboxes.
    """
    # Extract title from first # heading
    title_match = re.match(r"^#\s+(.+)$", markdown, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else doc_type.upper()

    # Split into sections by ## headings
    sections: list[TemplateSection] = []
    all_fields: list[SectionField] = []

    # Find all ## and ### headings with positions
    headings: list[tuple[int, int, str, str]] = []  # (pos, level, number, title)
    for m in _HEADING_RE.finditer(markdown):
        level = len(m.group(1))  # 2 for ##, 3 for ###
        raw_title = m.group(2).strip()

        # Try to extract section number
        num_match = re.match(r"(?:PART\s+)?(\d+(?:\.\d+)*)[.:\s)\-]+\s*(.+)", raw_title)
        task_match = re.match(r"Task\s+(\d+)[:\s]+\s*(.+)", raw_title)

        if num_match:
            number = num_match.group(1)
            section_title = num_match.group(2).strip()
        elif task_match:
            number = f"T{task_match.group(1)}"
            section_title = task_match.group(2).strip()
        else:
            number = ""
            section_title = raw_title

        # Skip pure placeholder titles like "{{TITLE}}" and meta headings
        if re.match(r"^\{\{[A-Z_]+\}\}$", section_title):
            continue
        # Skip NCI/NIH org subtitles
        if section_title.startswith("National") and "Institute" in section_title:
            continue

        headings.append((m.start(), level, number, section_title))

    # Process each heading and its body text
    for i, (pos, level, number, section_title) in enumerate(headings):
        # Get body text until next heading
        next_pos = headings[i + 1][0] if i + 1 < len(headings) else len(markdown)
        body = markdown[pos:next_pos]

        # Remove the heading line itself
        body_lines = body.split("\n", 1)
        body_text = body_lines[1] if len(body_lines) > 1 else ""

        # Extract description (first non-empty, non-placeholder paragraph)
        description = ""
        for line in body_text.split("\n"):
            stripped = line.strip()
            if (
                stripped
                and not stripped.startswith("|")
                and not stripped.startswith("---")
            ):
                if not _PLACEHOLDER_RE.search(stripped) or len(stripped) > 60:
                    description = stripped[:200]
                    break

        # Extract placeholders
        placeholders = list(dict.fromkeys(_PLACEHOLDER_RE.findall(body_text)))
        fields = [SectionField(name=p) for p in placeholders]
        all_fields.extend(fields)

        # Detect tables and checkboxes
        has_table = bool(_TABLE_RE.search(body_text))
        has_checkbox = "☐" in body_text or "checkbox" in body_text.lower()
        for f in fields:
            if has_table:
                f.field_type = "table"
            elif has_checkbox:
                f.field_type = "checkbox"

        section = TemplateSection(
            number=number,
            title=section_title,
            description=description,
            fields=fields,
            has_table=has_table,
        )

        # Nest subsections (### under ##)
        if level == 3 and sections:
            # This is a subsection — attach to the last ## section
            parent = sections[-1]
            parent.subsections.append(section)
        else:
            sections.append(section)

    return TemplateSchema(
        doc_type=doc_type,
        title=title,
        sections=sections,
        total_fields=len(all_fields),
        required_fields=len([f for f in all_fields if f.required]),
    )


def load_from_json(json_path: str) -> Optional[TemplateSchema]:
    """Load a TemplateSchema from a Step 0 extracted JSON metadata file."""
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning("Could not load template metadata from %s: %s", json_path, e)
        return None

    if data.get("parse_error"):
        logger.debug("Skipping %s: %s", json_path, data["parse_error"])
        return None

    doc_type = data.get("category", "unknown")
    variant = data.get("variant", "")
    if variant:
        doc_type = f"{doc_type}_{variant}"

    sections = []
    all_field_count = 0
    for s in data.get("sections", []):
        fields = [SectionField(name=p) for p in s.get("placeholders", [])]
        all_field_count += len(fields)
        section = TemplateSection(
            number=s.get("number", ""),
            title=s.get("title", ""),
            fields=fields,
            has_table=s.get("has_table", False),
        )
        sections.append(section)

    return TemplateSchema(
        doc_type=doc_type,
        title=data.get("filename", doc_type),
        sections=sections,
        total_fields=data.get("total_placeholders", all_field_count),
        required_fields=all_field_count,
    )


def load_template_schemas() -> dict[str, TemplateSchema]:
    """Auto-discover and load all template schemas.

    Sources:
      1. eagle-plugin/data/templates/*-template.md (legacy markdown schema inputs)
      2. eagle-plugin/data/template-metadata/*.json (extracted S3 metadata)

    Returns dict keyed by doc_type.
    """
    schemas: dict[str, TemplateSchema] = {}

    # 1. Legacy markdown schema templates (higher priority — richer structure)
    if TEMPLATES_DIR.exists():
        for md_file in sorted(TEMPLATES_DIR.glob("*-template.md")):
            doc_type = _MD_FILENAME_TO_DOCTYPE.get(md_file.name)
            if not doc_type:
                # Infer from filename: "sow-template.md" → "sow"
                doc_type = md_file.stem.replace("-template", "").replace("-", "_")

            try:
                content = md_file.read_text(encoding="utf-8")
                schema = parse_template_schema(content, doc_type)
                schemas[doc_type] = schema
                logger.debug(
                    "Loaded markdown schema for %s: %d sections, %d fields",
                    doc_type,
                    len(schema.sections),
                    schema.total_fields,
                )
            except Exception as e:
                logger.warning(
                    "Failed to parse markdown template %s: %s", md_file.name, e
                )

    # 2. Extracted JSON metadata (lower priority — don't override markdown)
    if METADATA_DIR.exists():
        for json_file in sorted(METADATA_DIR.glob("*.json")):
            if json_file.name.startswith("_"):
                continue  # Skip _index.json
            schema = load_from_json(str(json_file))
            if schema and schema.doc_type not in schemas:
                schemas[schema.doc_type] = schema
                logger.debug(
                    "Loaded JSON schema for %s: %d sections",
                    schema.doc_type,
                    len(schema.sections),
                )

    logger.info("Loaded %d template schemas", len(schemas))
    return schemas


# ── Module-Level Schema Cache ──
TEMPLATE_SCHEMAS: dict[str, TemplateSchema] = {}


def _ensure_schemas_loaded() -> None:
    """Lazy-load schemas on first access."""
    if not TEMPLATE_SCHEMAS:
        TEMPLATE_SCHEMAS.update(load_template_schemas())


# ── Section Guidance Builder ──


def build_section_guidance(doc_type: str) -> str:
    """Build concise AI prompt text listing sections and key fields.

    Returns one line per section: "Section N: TITLE — key fields: FIELD_A, FIELD_B"
    """
    _ensure_schemas_loaded()
    schema = TEMPLATE_SCHEMAS.get(doc_type)
    if not schema:
        return ""

    lines = [f"Template sections for {doc_type.upper()}:"]
    for section in schema.sections:
        num_prefix = f"{section.number}. " if section.number else ""
        field_names = [f.name for f in section.fields[:6]]  # Cap at 6 for brevity
        field_hint = f" — fields: {', '.join(field_names)}" if field_names else ""
        table_hint = " [TABLE]" if section.has_table else ""
        lines.append(f"  {num_prefix}{section.title}{field_hint}{table_hint}")

        # Include subsections
        for sub in section.subsections:
            sub_num = f"{sub.number}. " if sub.number else "  "
            sub_fields = [f.name for f in sub.fields[:4]]
            sub_hint = f" — {', '.join(sub_fields)}" if sub_fields else ""
            lines.append(f"    {sub_num}{sub.title}{sub_hint}")

    return "\n".join(lines)


def get_all_section_guidance() -> dict[str, str]:
    """Build section guidance for all known doc types."""
    _ensure_schemas_loaded()
    return {dt: build_section_guidance(dt) for dt in TEMPLATE_SCHEMAS}


# ── Completeness Validator ──


def validate_completeness(
    doc_type: str,
    content: str,
    threshold: float = 0.7,
) -> CompletenessReport:
    """Check each schema section against generated content.

    For each section, checks if the section title appears in the content
    and if at least one field from that section has been filled (i.e., the
    placeholder name no longer appears as {{NAME}}).

    Args:
        doc_type: Document type to validate against
        content: Generated document content (markdown)
        threshold: Minimum completeness ratio to consider "complete"

    Returns:
        CompletenessReport with section-level fill status
    """
    _ensure_schemas_loaded()
    schema = TEMPLATE_SCHEMAS.get(doc_type)
    if not schema:
        return CompletenessReport(
            doc_type=doc_type,
            total_sections=0,
            filled_sections=0,
            completeness_pct=0.0,
            is_complete=False,
        )

    content_lower = content.lower()
    total = 0
    filled = 0
    missing: list[str] = []

    for section in schema.sections:
        total += 1
        section_filled = _is_section_filled(section, content, content_lower)

        if section_filled:
            filled += 1
        else:
            label = (
                f"{section.number}. {section.title}"
                if section.number
                else section.title
            )
            missing.append(label)

    pct = (filled / total * 100) if total > 0 else 0.0
    return CompletenessReport(
        doc_type=doc_type,
        total_sections=total,
        filled_sections=filled,
        missing_sections=missing,
        completeness_pct=round(pct, 1),
        is_complete=pct >= threshold * 100,
    )


def _is_section_filled(
    section: TemplateSection, content: str, content_lower: str
) -> bool:
    """Check if a section appears to be filled in the content."""
    # Check 1: Section title should appear in content
    title_words = [w for w in section.title.lower().split() if len(w) > 3]
    title_present = (
        any(w in content_lower for w in title_words) if title_words else True
    )

    if not title_present:
        return False

    # Check 2: Placeholders should NOT still be present as {{NAME}}
    if section.fields:
        unfilled_count = sum(
            1 for f in section.fields if "{{" + f.name + "}}" in content
        )
        # If ANY field is still a raw placeholder, section is not fully filled
        if unfilled_count > 0:
            return False

    return True


# ── Clause Reference Loading ──────────────────────────────────────────

# In-memory cache for clause reference data
_clause_refs_cache: dict[str, dict] = {}
_clause_refs_loaded = False


def _ensure_clause_refs_loaded() -> None:
    """Load all clause reference sidecar files from disk on first access."""
    global _clause_refs_loaded
    if _clause_refs_loaded:
        return

    if not CLAUSE_REFS_DIR.exists():
        logger.debug("Clause references dir not found: %s", CLAUSE_REFS_DIR)
        _clause_refs_loaded = True
        return

    for path in CLAUSE_REFS_DIR.glob("*.json"):
        if path.name == "_index.json":
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            _clause_refs_cache[path.stem] = data
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load clause refs from %s: %s", path.name, e)

    _clause_refs_loaded = True
    logger.info("Loaded %d clause reference files", len(_clause_refs_cache))


def load_clause_references(template_filename: str) -> dict:
    """Load clause references for a specific template by its metadata filename.

    Args:
        template_filename: The metadata filename stem (without .json extension)

    Returns:
        Clause reference dict or empty dict if not found
    """
    _ensure_clause_refs_loaded()
    # Strip .json extension if present
    stem = template_filename.replace(".json", "")
    return _clause_refs_cache.get(stem, {})


def load_clause_references_by_category(category: str) -> list[dict]:
    """Load all clause reference sidecars for a given category.

    Args:
        category: Template category (e.g., "sow", "acquisition_plan", "igce")

    Returns:
        List of clause reference dicts for all templates in that category
    """
    _ensure_clause_refs_loaded()
    results = []
    # Normalize hyphens to underscores for matching
    category_normalized = category.replace("-", "_")
    for _stem, ref_data in _clause_refs_cache.items():
        ref_cat = ref_data.get("category", "").replace("-", "_")
        if ref_cat == category_normalized:
            results.append(ref_data)
    return results


def load_all_clause_references() -> dict[str, dict]:
    """Load all 36 clause reference sidecar files.

    Returns:
        Dict keyed by filename stem, values are clause reference dicts
    """
    _ensure_clause_refs_loaded()
    return dict(_clause_refs_cache)


def get_clause_coverage(template_filename: str) -> ClauseCoverageReport:
    """Compute clause coverage for a single template.

    Args:
        template_filename: The metadata filename stem

    Returns:
        ClauseCoverageReport with coverage statistics
    """
    ref_data = load_clause_references(template_filename)
    if not ref_data:
        doc_type = template_filename.replace(".json", "")
        return ClauseCoverageReport(
            doc_type=doc_type,
            total_clauses_referenced=0,
            far_parts_covered=[],
            sections_with_clauses=0,
            sections_without_clauses=0,
        )

    clause_list = []
    far_parts = set()
    sections_with = 0
    sections_without = 0

    for sec_num, sec_data in ref_data.get("section_clause_map", {}).items():
        clauses = sec_data.get("clauses", [])
        if clauses:
            sections_with += 1
            for c in clauses:
                clause_list.append(
                    {
                        "clause_number": c.get("clause_number", ""),
                        "title": c.get("title", ""),
                        "section_number": sec_num,
                        "applicability": c.get("applicability", "required"),
                    }
                )
                # Extract FAR part number
                part = _extract_far_part(c.get("clause_number", ""))
                if part:
                    far_parts.add(part)
        else:
            sections_without += 1

    for c in ref_data.get("template_level_clauses", []):
        clause_list.append(
            {
                "clause_number": c.get("clause_number", ""),
                "title": c.get("title", ""),
                "section_number": "template_level",
                "applicability": c.get("applicability", "required"),
            }
        )
        part = _extract_far_part(c.get("clause_number", ""))
        if part:
            far_parts.add(part)

    return ClauseCoverageReport(
        doc_type=ref_data.get("category", ""),
        total_clauses_referenced=len(clause_list),
        far_parts_covered=sorted(far_parts),
        sections_with_clauses=sections_with,
        sections_without_clauses=sections_without,
        clause_list=clause_list,
    )


def get_category_clause_coverage(category: str) -> ClauseCoverageReport:
    """Aggregated clause coverage across all template variants in a category."""
    refs = load_clause_references_by_category(category)
    all_clauses = {}
    far_parts = set()
    total_sections_with = 0
    total_sections_without = 0

    for ref_data in refs:
        for sec_num, sec_data in ref_data.get("section_clause_map", {}).items():
            clauses = sec_data.get("clauses", [])
            if clauses:
                total_sections_with += 1
                for c in clauses:
                    cn = c.get("clause_number", "")
                    if cn and cn not in all_clauses:
                        all_clauses[cn] = {
                            "clause_number": cn,
                            "title": c.get("title", ""),
                            "section_number": sec_num,
                            "applicability": c.get("applicability", "required"),
                        }
                        part = _extract_far_part(cn)
                        if part:
                            far_parts.add(part)
            else:
                total_sections_without += 1

        for c in ref_data.get("template_level_clauses", []):
            cn = c.get("clause_number", "")
            if cn and cn not in all_clauses:
                all_clauses[cn] = {
                    "clause_number": cn,
                    "title": c.get("title", ""),
                    "section_number": "template_level",
                    "applicability": c.get("applicability", "required"),
                }
                part = _extract_far_part(cn)
                if part:
                    far_parts.add(part)

    return ClauseCoverageReport(
        doc_type=category,
        total_clauses_referenced=len(all_clauses),
        far_parts_covered=sorted(far_parts),
        sections_with_clauses=total_sections_with,
        sections_without_clauses=total_sections_without,
        clause_list=list(all_clauses.values()),
    )


_FAR_PART_RE = re.compile(r"(?:FAR|DFARS|HHSAR)\s+(\d+)")


def _extract_far_part(clause_number: str) -> str:
    """Extract the FAR part number from a clause number string."""
    match = _FAR_PART_RE.search(clause_number)
    return match.group(1) if match else ""
