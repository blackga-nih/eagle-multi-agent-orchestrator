"""Commercial IGCE workbook schema — single source of truth for cell mappings.

This module defines the structure of the NCI Commercial IGCE Excel template
(01.D_IGCE_for_Commercial_Organizations.xlsx). Both generation (IGCEPositionPopulator)
and editing (igce_xlsx_edit_resolver) consume these mappings.

Template structure:
- IGCE sheet: Summary with labor rows, ODC rows, rates, and grand total
- IT Services sheet: Multi-year labor detail with hours and rates
- IT Goods sheet: Goods/equipment detail with quantities and unit prices
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple


# ══════════════════════════════════════════════════════════════════════
#  Sheet Names
# ══════════════════════════════════════════════════════════════════════

SHEET_IGCE_SUMMARY = "IGCE"
SHEET_IT_SERVICES = "IT Services"
SHEET_IT_GOODS = "IT Goods"


# ══════════════════════════════════════════════════════════════════════
#  IGCE Summary Sheet — Labor Groups
# ══════════════════════════════════════════════════════════════════════

@dataclass
class LaborGroup:
    """A group of labor row slots in the IGCE summary sheet."""
    name: str
    start_row: int
    num_slots: int

    @property
    def rows(self) -> List[int]:
        return [self.start_row + i for i in range(self.num_slots)]


IGCE_LABOR_GROUPS: List[LaborGroup] = [
    LaborGroup("Professional", 7, 3),           # Rows 7-9
    LaborGroup("Professional Support", 11, 3),  # Rows 11-13
    LaborGroup("Administrative Support", 16, 3),  # Rows 16-18
    LaborGroup("Other Support", 21, 3),         # Rows 21-23
]

# Flattened list of all labor rows in IGCE summary sheet
IGCE_LABOR_ROWS: List[int] = []
for group in IGCE_LABOR_GROUPS:
    IGCE_LABOR_ROWS.extend(group.rows)

# IGCE summary labor columns
IGCE_LABOR_COL_NAME = "A"
IGCE_LABOR_COL_HOURS = "C"
IGCE_LABOR_COL_RATE = "E"
IGCE_LABOR_COL_TOTAL = "G"  # Formula: =C*E


# ══════════════════════════════════════════════════════════════════════
#  IGCE Summary Sheet — ODC/Goods Rows
# ══════════════════════════════════════════════════════════════════════

@dataclass
class OdcRow:
    """An ODC (Other Direct Cost) row in the IGCE summary sheet."""
    label: str
    row: int
    aliases: List[str] = field(default_factory=list)


IGCE_ODC_ROWS: List[OdcRow] = [
    OdcRow("computer", 30, ["computers", "hardware"]),
    OdcRow("equipment", 31, ["equip"]),
    OdcRow("materials", 32, ["supplies", "material"]),
    OdcRow("consultants", 33, ["consultant", "consulting"]),
    OdcRow("travel", 34, ["trips"]),
    OdcRow("subcontracts", 35, ["subcontract", "subs"]),
    OdcRow("animal", 36, ["animals"]),
    OdcRow("other", 37, ["misc", "miscellaneous"]),
]

# Lookup dict: label/alias -> row number
IGCE_ODC_ROW_MAP: Dict[str, int] = {}
for odc in IGCE_ODC_ROWS:
    IGCE_ODC_ROW_MAP[odc.label] = odc.row
    for alias in odc.aliases:
        IGCE_ODC_ROW_MAP[alias] = odc.row

IGCE_GOODS_SUMMARY_ROWS: List[int] = [odc.row for odc in IGCE_ODC_ROWS]

# ODC values go in column E
IGCE_ODC_COL_VALUE = "E"


# ══════════════════════════════════════════════════════════════════════
#  IGCE Summary Sheet — Metadata Cells
# ══════════════════════════════════════════════════════════════════════

@dataclass
class MetadataCell:
    """A metadata cell in the workbook."""
    name: str
    sheet: str
    cell_ref: str
    editable: bool = True


IGCE_METADATA_CELLS: List[MetadataCell] = [
    MetadataCell("period_months", SHEET_IGCE_SUMMARY, "C5", editable=True),
    MetadataCell("overhead_rate", SHEET_IGCE_SUMMARY, "B28", editable=True),
    MetadataCell("ga_rate", SHEET_IGCE_SUMMARY, "B41", editable=True),
    MetadataCell("fee_rate", SHEET_IGCE_SUMMARY, "B44", editable=True),
    MetadataCell("cancellation_ceiling", SHEET_IGCE_SUMMARY, "E47", editable=True),
    MetadataCell("grand_total", SHEET_IGCE_SUMMARY, "H46", editable=False),  # Formula
    MetadataCell("total_hours", SHEET_IGCE_SUMMARY, "C24", editable=False),  # Formula
    MetadataCell("subtotal_labor", SHEET_IGCE_SUMMARY, "G26", editable=False),  # Formula
]


# ══════════════════════════════════════════════════════════════════════
#  IT Services Sheet — Labor Detail
# ══════════════════════════════════════════════════════════════════════

# Labor rows in IT Services sheet
IT_SERVICES_LABOR_START_ROW = 12
IT_SERVICES_LABOR_NUM_ROWS = 7  # Rows 12-18
IT_SERVICES_LABOR_ROWS: List[int] = list(
    range(IT_SERVICES_LABOR_START_ROW, IT_SERVICES_LABOR_START_ROW + IT_SERVICES_LABOR_NUM_ROWS)
)

# Multi-year column mappings: (hours_col, rate_col) as 1-indexed column numbers
IT_SERVICES_YEAR_COLUMNS: List[Tuple[int, int]] = [
    (2, 3),    # Base Year:   B=hours, C=rate
    (5, 6),    # Option Yr 1: E=hours, F=rate
    (8, 9),    # Option Yr 2: H=hours, I=rate
    (11, 12),  # Option Yr 3: K=hours, L=rate
    (14, 15),  # Option Yr 4: N=hours, O=rate
]

IT_SERVICES_COL_NAME = "A"

# Metadata cells in IT Services sheet
IT_SERVICES_CONTRACT_TYPE_CELL = "B5"
IT_SERVICES_POP_FROM_CELL = "B6"
IT_SERVICES_POP_TO_CELL = "D6"


# ══════════════════════════════════════════════════════════════════════
#  IT Goods Sheet — Goods Detail
# ══════════════════════════════════════════════════════════════════════

# Goods rows in IT Goods sheet
IT_GOODS_START_ROW = 10
IT_GOODS_NUM_ROWS = 8  # Rows 10-17
IT_GOODS_ROWS: List[int] = list(
    range(IT_GOODS_START_ROW, IT_GOODS_START_ROW + IT_GOODS_NUM_ROWS)
)

# Column mappings (1-indexed)
IT_GOODS_COL_PRODUCT_NAME = 1   # A
IT_GOODS_COL_MANUFACTURER = 2   # B
IT_GOODS_COL_MFR_NUMBER = 3     # C
IT_GOODS_COL_BRAND_ONLY = 4     # D
IT_GOODS_COL_QUANTITY = 5       # E
IT_GOODS_COL_UNIT_PRICE = 6     # F
IT_GOODS_COL_TOTAL = 7          # G (formula)

# Metadata cells in IT Goods sheet
IT_GOODS_CONTRACT_TYPE_CELL = "B5"
IT_GOODS_DELIVERY_DATE_CELL = "B6"


# ══════════════════════════════════════════════════════════════════════
#  Helper Functions
# ══════════════════════════════════════════════════════════════════════

def get_odc_row(label: str) -> int | None:
    """Match an ODC label to its row number in the IGCE sheet."""
    key = label.lower().strip()
    for lookup_key, row in IGCE_ODC_ROW_MAP.items():
        if lookup_key in key:
            return row
    return IGCE_ODC_ROW_MAP.get("other")


def get_labor_slot_rows() -> List[int]:
    """Get flattened list of all labor slot rows in IGCE summary sheet."""
    return IGCE_LABOR_ROWS.copy()


def get_labor_groups_as_tuples() -> List[Tuple[int, int]]:
    """Get labor groups as (start_row, num_slots) tuples for backwards compat."""
    return [(g.start_row, g.num_slots) for g in IGCE_LABOR_GROUPS]
