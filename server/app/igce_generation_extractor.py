"""IGCE structured data extraction for workbook-aware generation.

This module extracts structured IGCE data from conversation context and
user prompts. The extracted data is used to populate IGCE XLSX workbooks
with meaningful first-pass values.

Extraction approach:
1. Deterministic parsing first (money, dates, contract types, line items)
2. Narrow LLM extraction only when deterministic parsing is insufficient

The output schema aligns with what IGCEPositionPopulator expects:
- line_items: list of labor categories with hours/rates
- goods_items: list of goods with quantities/prices
- contract_type, period_of_performance, period_months, etc.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ══════════════════════════════════════════════════════════════════════
#  Labor Category Recognition
# ══════════════════════════════════════════════════════════════════════

# Common labor categories and their aliases
LABOR_CATEGORIES = {
    "project manager": ["pm", "project lead", "program manager"],
    "senior software engineer": ["senior developer", "senior dev", "sr engineer", "sr developer"],
    "software engineer": ["developer", "dev", "engineer", "programmer"],
    "junior software engineer": ["junior developer", "junior dev", "jr engineer", "jr developer"],
    "cloud architect": ["solutions architect", "aws architect", "azure architect"],
    "data scientist": ["data analyst", "ml engineer", "machine learning engineer"],
    "devops engineer": ["site reliability engineer", "sre", "platform engineer"],
    "security engineer": ["cybersecurity engineer", "infosec engineer", "security analyst"],
    "qa engineer": ["test engineer", "quality assurance", "tester"],
    "technical writer": ["documentation specialist", "tech writer"],
    "business analyst": ["ba", "requirements analyst"],
    "system administrator": ["sysadmin", "sys admin", "it administrator"],
    "database administrator": ["dba", "database engineer"],
    "network engineer": ["network administrator", "network admin"],
    "help desk": ["support specialist", "it support", "technical support"],
}

# Build reverse lookup: alias -> canonical name
_LABOR_ALIAS_MAP: Dict[str, str] = {}
for canonical, aliases in LABOR_CATEGORIES.items():
    _LABOR_ALIAS_MAP[canonical.lower()] = canonical
    for alias in aliases:
        _LABOR_ALIAS_MAP[alias.lower()] = canonical


def _normalize_labor_category(name: str) -> str:
    """Normalize a labor category name to a canonical form."""
    key = name.lower().strip()
    return _LABOR_ALIAS_MAP.get(key, name.title())


# ══════════════════════════════════════════════════════════════════════
#  Extraction Patterns
# ══════════════════════════════════════════════════════════════════════

# Money pattern: $100, $1,000, $100K, $1.5M, $100,000.00
_MONEY_RE = re.compile(
    r"\$\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*([KkMmBb])?",
    re.IGNORECASE,
)

# Hourly rate pattern: $150/hour, $150/hr, $150 per hour, $150 hourly
_HOURLY_RATE_RE = re.compile(
    r"\$\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*(?:/\s*(?:hour|hr)|per\s+hour|hourly)",
    re.IGNORECASE,
)

# Hours pattern: 1000 hours, 1,000 hrs, 500 hours/year
_HOURS_RE = re.compile(
    r"([0-9][0-9,]*)\s*(?:hours?|hrs?)(?:\s*(?:/\s*(?:year|yr|month|mo))?)",
    re.IGNORECASE,
)

# Period pattern: 12 months, 2 years, 24-month, 3-year
_PERIOD_RE = re.compile(
    r"(\d+)\s*[-\s]?\s*(months?|years?|yrs?|mos?)\b",
    re.IGNORECASE,
)

# Contract type patterns
_CONTRACT_TYPE_PATTERNS = [
    (re.compile(r"\b(FFP|firm.fixed.price)\b", re.IGNORECASE), "FFP"),
    (re.compile(r"\b(T&M|time.and.materials?)\b", re.IGNORECASE), "T&M"),
    (re.compile(r"\b(CPFF|cost.plus.fixed.fee)\b", re.IGNORECASE), "CPFF"),
    (re.compile(r"\b(CPAF|cost.plus.award.fee)\b", re.IGNORECASE), "CPAF"),
    (re.compile(r"\b(CPIF|cost.plus.incentive.fee)\b", re.IGNORECASE), "CPIF"),
    (re.compile(r"\b(IDIQ)\b", re.IGNORECASE), "IDIQ"),
    (re.compile(r"\b(BPA|blanket.purchase.agreement)\b", re.IGNORECASE), "BPA"),
]

# Line item bullet pattern: "- Item name: $X/hour, Y hours" or numbered
_LINE_ITEM_RE = re.compile(
    r"^[\s]*[-*•]?\s*(?:\d+[.)]\s*)?"  # Optional bullet or number
    r"([A-Za-z][A-Za-z\s]+?)"  # Category name (starts with letter)
    r"(?::\s*|\s+-\s+|\s+@\s+|\s+at\s+)"  # Separator
    r"(.+)$",  # Rest of line with rate/hours info
    re.MULTILINE,
)

# Quantity pattern for goods: "5 licenses", "10 units", "3 servers"
_QUANTITY_RE = re.compile(
    r"(\d+)\s*(licenses?|units?|seats?|devices?|servers?|laptops?|monitors?|items?)",
    re.IGNORECASE,
)

# ISO date pattern for delivery dates / POP ranges
_ISO_DATE_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")

# Explicit delivery date pattern
_DELIVERY_DATE_RE = re.compile(
    r"(?:delivery date|deliver(?:ed|y)? by|due date)(?:\s+is|\s+to|\s*:)?\s+(20\d{2}-\d{2}-\d{2})",
    re.IGNORECASE,
)

# Period-of-performance range pattern
_POP_RANGE_RE = re.compile(
    r"(?:period of performance|performance period|pop)?"
    r".{0,40}?\bfrom\s+(20\d{2}-\d{2}-\d{2})\s+(?:through|to|-)\s+(20\d{2}-\d{2}-\d{2})",
    re.IGNORECASE | re.DOTALL,
)

# Prose labor pattern: "3 developers at $150/hr for 1000 hours each"
_LABOR_PROSE_RE = re.compile(
    r"(?:(\d+)\s+)?([A-Za-z][A-Za-z\s/&-]{2,}?)s?"
    r"\s+(?:at|@)\s+\$\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*"
    r"(?:/\s*(?:hour|hr)|per\s+hour|hourly)"
    r"(?:\s*(?:for|x)\s*([0-9][0-9,]*)\s*(?:hours?|hrs?))?"
    r"(?:\s+each)?",
    re.IGNORECASE,
)

# Goods line pattern: "AWS Licensing, 12 MO at $15,000/month"
_GOODS_LINE_RE = re.compile(
    r"^[\s]*[-*•]?\s*(?:\d+[.)]\s*)?"
    r"([A-Za-z][A-Za-z0-9\s/&().-]+?)"
    r"(?:\s*,|\s+-|\s+)\s*"
    r"(\d+)\s*(?:months?|mos?|mo|licenses?|units?|seats?|devices?|servers?|laptops?|monitors?|items?)"
    r"\s*(?:at|@)\s*\$\s*([0-9][0-9,]*(?:\.[0-9]+)?)"
    r"(?:\s*/\s*(?:month|mo|unit|license|seat|device))?",
    re.IGNORECASE | re.MULTILINE,
)


# ══════════════════════════════════════════════════════════════════════
#  Extraction Functions
# ══════════════════════════════════════════════════════════════════════

def _parse_money(text: str) -> float | None:
    """Parse a money value from text, handling K/M/B suffixes."""
    match = _MONEY_RE.search(text)
    if not match:
        return None
    amount = float(match.group(1).replace(",", ""))
    suffix = (match.group(2) or "").upper()
    multipliers = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}
    return amount * multipliers.get(suffix, 1)


def _parse_hourly_rate(text: str) -> float | None:
    """Extract hourly rate from text."""
    match = _HOURLY_RATE_RE.search(text)
    if match:
        return float(match.group(1).replace(",", ""))
    return None


def _parse_hours(text: str) -> int | None:
    """Extract hours from text."""
    match = _HOURS_RE.search(text)
    if match:
        return int(match.group(1).replace(",", ""))
    return None


def _parse_period_months(text: str) -> int | None:
    """Extract period of performance in months."""
    match = _PERIOD_RE.search(text)
    if not match:
        return None
    value = int(match.group(1))
    unit = match.group(2).lower()
    if unit.startswith("y"):
        return value * 12
    return value


def _parse_contract_type(text: str) -> str | None:
    """Extract contract type from text."""
    for pattern, contract_type in _CONTRACT_TYPE_PATTERNS:
        if pattern.search(text):
            return contract_type
    return None


def _parse_delivery_date(text: str) -> str | None:
    """Extract an explicit delivery date from text."""
    match = _DELIVERY_DATE_RE.search(text)
    if match:
        return match.group(1)
    return None


def _parse_period_of_performance(text: str) -> Dict[str, str] | None:
    """Extract a period-of-performance date range from text."""
    match = _POP_RANGE_RE.search(text)
    if not match:
        return None
    return {"from": match.group(1), "to": match.group(2)}


def _extract_line_items_from_text(text: str) -> List[Dict[str, Any]]:
    """Extract labor line items from bullet/numbered lists in text."""
    items: List[Dict[str, Any]] = []

    # Skip patterns - these are not labor categories
    skip_patterns = [
        r"^equipment", r"^contract", r"^total", r"^budget", r"^cost",
        r"^period", r"^timeline", r"^duration", r"^license", r"^server",
        r"^hardware", r"^software", r"^material", r"^supply", r"^travel",
    ]
    skip_re = re.compile("|".join(skip_patterns), re.IGNORECASE)

    for match in _LINE_ITEM_RE.finditer(text):
        name_part = match.group(1).strip()
        details_part = match.group(2).strip()

        # Skip non-labor items
        if skip_re.match(name_part):
            continue

        # Skip if name doesn't look like a labor category
        normalized_name = _normalize_labor_category(name_part)
        if len(normalized_name) < 3:
            continue

        # Extract rate and hours from details
        rate = _parse_hourly_rate(details_part)
        hours = _parse_hours(details_part)

        # Skip if no rate or hours found (not a valid labor line item)
        if rate is None and hours is None:
            # Try plain money value as rate
            money = _parse_money(details_part)
            if money and money < 1000:  # Likely an hourly rate if under $1000
                rate = money
            else:
                continue  # Skip items without rate/hours info

        item: Dict[str, Any] = {"description": normalized_name}
        if rate is not None:
            item["rate"] = rate
        if hours is not None:
            item["hours"] = hours

        items.append(item)

    return items


def _extract_labor_items_from_prose(text: str) -> List[Dict[str, Any]]:
    """Extract labor items from prose sentences, not just bullets."""
    items: List[Dict[str, Any]] = []
    seen: set[tuple[str, float | None, int | None]] = set()

    segments = [segment.strip() for segment in re.split(r"[\n.;]+", text) if segment.strip()]
    for segment in segments:
        if segment.startswith(("-", "*", "•")):
            continue
        match = _LABOR_PROSE_RE.search(segment)
        if not match:
            continue
        count = int(match.group(1)) if match.group(1) else 1
        raw_name = match.group(2).strip()
        normalized_name = _normalize_labor_category(raw_name)
        rate = float(match.group(3).replace(",", ""))
        hours = int(match.group(4).replace(",", "")) if match.group(4) else None

        item_hours = hours * count if hours is not None else None
        dedupe_key = (normalized_name, rate, item_hours)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        item: Dict[str, Any] = {"description": normalized_name, "rate": rate}
        if item_hours is not None:
            item["hours"] = item_hours
        items.append(item)

    return items


def _extract_goods_items_from_text(text: str) -> List[Dict[str, Any]]:
    """Extract goods/equipment items from text."""
    items: List[Dict[str, Any]] = []
    seen_names: set[str] = set()

    for match in _GOODS_LINE_RE.finditer(text):
        product_name = match.group(1).strip()
        quantity = int(match.group(2))
        unit_price = float(match.group(3).replace(",", ""))
        key = product_name.lower()
        if key in seen_names:
            continue
        items.append(
            {
                "product_name": product_name,
                "quantity": quantity,
                "unit_price": unit_price,
            }
        )
        seen_names.add(key)

    # Pattern for "N items at $X each" or "N items @ $X"
    goods_price_re = re.compile(
        r"(\d+)\s*(licenses?|units?|seats?|devices?|servers?|laptops?|monitors?|items?)"
        r"\s*(?:at|@)\s*\$\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*(?:each)?",
        re.IGNORECASE,
    )

    # First pass: look for explicit "N items at $X" patterns
    for match in goods_price_re.finditer(text):
        quantity = int(match.group(1))
        item_type = match.group(2).rstrip("s")  # Singularize
        unit_price = float(match.group(3).replace(",", ""))

        items.append({
            "product_name": item_type.title(),
            "quantity": quantity,
            "unit_price": unit_price,
        })

    # Second pass: look for quantity patterns without explicit prices
    seen_types = {item["product_name"].lower() for item in items}
    for match in _QUANTITY_RE.finditer(text):
        quantity = int(match.group(1))
        item_type = match.group(2).rstrip("s")

        # Skip if we already have this item type
        if item_type.lower() in seen_types:
            continue

        items.append({
            "product_name": item_type.title(),
            "quantity": quantity,
        })
        seen_types.add(item_type.lower())

    return items


@dataclass
class IGCEExtractionResult:
    """Result of IGCE data extraction."""
    line_items: List[Dict[str, Any]] = field(default_factory=list)
    goods_items: List[Dict[str, Any]] = field(default_factory=list)
    contract_type: Optional[str] = None
    period_months: Optional[int] = None
    period_of_performance: Optional[Dict[str, str]] = None
    delivery_date: Optional[str] = None
    estimated_value: Optional[float] = None
    description: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for merging with document data."""
        result: Dict[str, Any] = {}
        if self.line_items:
            result["line_items"] = self.line_items
        if self.goods_items:
            result["goods_items"] = self.goods_items
        if self.contract_type:
            result["contract_type"] = self.contract_type
        if self.period_months:
            result["period_months"] = self.period_months
        if self.period_of_performance:
            result["period_of_performance"] = self.period_of_performance
        if self.delivery_date:
            result["delivery_date"] = self.delivery_date
        if self.estimated_value:
            result["estimated_value"] = self.estimated_value
        if self.description:
            result["description"] = self.description
        return result


def extract_igce_data_from_text(text: str) -> IGCEExtractionResult:
    """Extract IGCE-relevant structured data from text.

    This is the deterministic extraction path. It parses:
    - Labor line items from bullets/lists
    - Goods items from quantity patterns
    - Contract type keywords
    - Period of performance
    - Total estimated value

    Args:
        text: Combined user prompt and session context text

    Returns:
        IGCEExtractionResult with extracted fields
    """
    result = IGCEExtractionResult()

    # Extract line items (labor)
    line_items = _extract_line_items_from_text(text)
    for prose_item in _extract_labor_items_from_prose(text):
        if not any(
            existing.get("description") == prose_item.get("description")
            and existing.get("rate") == prose_item.get("rate")
            and existing.get("hours") == prose_item.get("hours")
            for existing in line_items
        ):
            line_items.append(prose_item)
    result.line_items = line_items

    # Extract goods items
    result.goods_items = _extract_goods_items_from_text(text)

    # Extract contract type
    result.contract_type = _parse_contract_type(text)

    # Extract period
    result.period_months = _parse_period_months(text)
    result.period_of_performance = _parse_period_of_performance(text)
    result.delivery_date = _parse_delivery_date(text)

    # Extract total estimated value (largest money value that's not a rate)
    money_values = []
    for match in _MONEY_RE.finditer(text):
        value = _parse_money(match.group(0))
        if value and value > 10000:  # Filter out rates
            money_values.append(value)
    if money_values:
        result.estimated_value = max(money_values)

    return result


def extract_igce_generation_data(
    existing_data: Dict[str, Any],
    session_id: str | None = None,
    context_messages: List[str] | None = None,
) -> Dict[str, Any]:
    """Extract and merge IGCE-specific structured data for workbook generation.

    This function augments the existing document data with IGCE-specific
    structured extraction. It's called for doc_type=igce and output_format=xlsx.

    Args:
        existing_data: Current document data dict (from agent/augmentation)
        session_id: Session ID for loading context (if context_messages not provided)
        context_messages: Optional pre-loaded context messages

    Returns:
        Merged data dict with IGCE-specific fields populated
    """
    merged = dict(existing_data)

    # Build text corpus from existing data and context
    text_parts: List[str] = []

    # Add description/requirement from existing data
    for key in ("description", "requirement", "objective", "scope"):
        if key in merged and merged[key]:
            text_parts.append(str(merged[key]))

    # Add context messages if provided
    if context_messages:
        text_parts.extend(context_messages)
    elif session_id:
        # Load from session (lazy import to avoid circular deps)
        try:
            from app.tools.create_document_support import _load_recent_user_context
            loaded = _load_recent_user_context(session_id)
            if loaded:
                text_parts.extend(loaded)
        except Exception:
            pass

    if not text_parts:
        return merged

    # Combine text and extract
    combined_text = "\n".join(text_parts)
    extraction = extract_igce_data_from_text(combined_text)

    # Merge extracted data (don't overwrite existing values)
    extracted = extraction.to_dict()
    for key, value in extracted.items():
        if key not in merged or not merged[key]:
            merged[key] = value
        elif key == "line_items" and isinstance(value, list) and not merged.get(key):
            merged[key] = value
        elif key == "goods_items" and isinstance(value, list) and not merged.get(key):
            merged[key] = value

    return merged
