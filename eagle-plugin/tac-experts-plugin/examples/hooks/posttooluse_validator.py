#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas"]
# ///
#
# PostToolUse Validator — Validates CSV output after Write/Edit operations.
# Demonstrates the Block/Retry Self-Correction Loop (TAC Lesson 19: SSVA).
#
# When this hook blocks, the reason string becomes Claude's next correction
# task. The agent reads the block reason, fixes the file, and the hook
# re-validates on the next Write — this is autonomous self-correction.
#
# Configure in settings.json (global):
# {
#   "hooks": {
#     "PostToolUse": [
#       {
#         "matcher": "Write|Edit",
#         "hooks": [{
#           "type": "command",
#           "command": "uv run .claude/hooks/posttooluse_validator.py"
#         }]
#       }
#     ]
#   }
# }
#
# Or in agent frontmatter (scoped — SSVA pattern):
# ---
# hooks:
#   PostToolUse:
#     - matcher: "Write|Edit"
#       hooks:
#         - type: command
#           command: "uv run .claude/hooks/posttooluse_validator.py"
# ---

import json
import sys
from pathlib import Path

# ── Configuration ──────────────────────────────────────
REQUIRED_COLUMNS = ["date", "description", "amount"]
MAX_ROWS = 10000
EXPECTED_DATE_FORMAT = r"^\d{4}-\d{2}-\d{2}$"


def main():
    hook_input = json.loads(sys.stdin.read())
    tool_name = hook_input.get("tool_name", "")
    tool_input = hook_input.get("tool_input", {})

    # Only validate CSV file writes
    file_path = tool_input.get("file_path", "")
    if not file_path.endswith(".csv"):
        allow()
        return

    # Validate the written CSV
    errors = validate_csv(file_path)

    if errors:
        block(
            f"CSV validation failed for {Path(file_path).name}:\n"
            + "\n".join(f"  - {e}" for e in errors)
            + "\n\nFix these issues and write the file again."
        )
    else:
        allow(f"CSV validated: {Path(file_path).name} passed all checks.")


def validate_csv(file_path: str) -> list[str]:
    """Validate a CSV file and return list of errors (empty = pass)."""
    import re

    try:
        import pandas as pd
    except ImportError:
        return ["pandas not installed — cannot validate CSV"]

    path = Path(file_path)
    if not path.exists():
        return [f"File not found: {file_path}"]

    errors = []

    try:
        df = pd.read_csv(path)
    except Exception as e:
        return [f"Cannot parse CSV: {e}"]

    # Check required columns
    for col in REQUIRED_COLUMNS:
        if col not in df.columns:
            errors.append(
                f"Missing required column '{col}'. "
                f"Found columns: {list(df.columns)}. "
                f"Add the '{col}' column."
            )

    # Check row count
    if len(df) > MAX_ROWS:
        errors.append(
            f"Too many rows: {len(df)} (max {MAX_ROWS}). "
            f"Split into multiple files or filter data."
        )

    # Check for empty dataframe
    if len(df) == 0:
        errors.append("CSV is empty — must contain at least one data row.")

    # Check date format if column exists
    if "date" in df.columns:
        bad_dates = df[~df["date"].astype(str).str.match(EXPECTED_DATE_FORMAT)]
        if len(bad_dates) > 0:
            samples = bad_dates["date"].head(3).tolist()
            errors.append(
                f"Invalid date format in {len(bad_dates)} rows. "
                f"Expected YYYY-MM-DD, found: {samples}. "
                f"Reformat all dates to YYYY-MM-DD."
            )

    # Check amount is numeric if column exists
    if "amount" in df.columns:
        non_numeric = pd.to_numeric(df["amount"], errors="coerce").isna()
        if non_numeric.any():
            count = non_numeric.sum()
            errors.append(
                f"{count} non-numeric values in 'amount' column. "
                f"Ensure all amounts are numbers (no currency symbols or text)."
            )

    return errors


def allow(message: str = ""):
    """Allow the tool call to proceed."""
    output = {}
    if message:
        output = {"message": message}
    print(json.dumps(output))
    sys.exit(0)


def block(reason: str):
    """Block with a reason — this reason becomes Claude's next correction task."""
    print(json.dumps({
        "decision": "block",
        "reason": reason
    }))
    sys.exit(2)


if __name__ == "__main__":
    main()
