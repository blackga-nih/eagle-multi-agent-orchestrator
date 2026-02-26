#!/usr/bin/env python3
"""
Sync TAC plugin components to AI-Agent-KB (Obsidian vault).

Copies agents, commands, hooks, and expert files to the correct KB
subdirectory, adds/updates YAML frontmatter with KB-required fields,
and calls add_banners_all.py for MTG card assignment.

Usage:
  # Sync a single file
  python scripts/sync-to-obsidian.py examples/agents/hooks-expert-agent.md

  # Sync all plugin examples
  python scripts/sync-to-obsidian.py --all

  # Dry run
  python scripts/sync-to-obsidian.py examples/agents/hooks-expert-agent.md --dry-run
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parent.parent
KB_ROOT = Path(r"C:\Users\gblac\OneDrive\Desktop\obsidian\Gbautomation\AI-Agent-KB")
KB_SCRIPTS = KB_ROOT / "_scripts"
BANNER_SCRIPT = KB_SCRIPTS / "add_banners_all.py"

# Component type detection from path patterns (order matters — more specific first)
PATH_TYPE_MAP = [
    ("experts/", "expert"),
    ("agents/", "agent"),
    ("hooks/", "hook"),
    ("skills/", "skill"),
    ("adws/", "adw"),
    ("commands/", "command"),
]

# KB destination folders by component type
KB_DESTINATIONS = {
    "agent": KB_ROOT / "agents",
    "command": KB_ROOT / "commands",
    "hook": KB_ROOT / "hooks",
    "skill": KB_ROOT / "skills",
    "expert": KB_ROOT / "experts",
    "adw": KB_ROOT / "adws",
}

# Required frontmatter fields by type
REQUIRED_FRONTMATTER = {
    "agent": {
        "type": "agent",
        "status": "active",
        "source": "tac-experts-plugin",
    },
    "command": {
        "type": "command",
        "status": "active",
        "source": "tac-experts-plugin",
    },
    "hook": {
        "type": "hook",
        "status": "active",
        "source": "tac-experts-plugin",
    },
    "skill": {
        "type": "skill",
        "status": "active",
        "source": "tac-experts-plugin",
    },
    "expert": {
        "type": "expert",
        "status": "active",
        "source": "tac-experts-plugin",
    },
    "adw": {
        "type": "adw",
        "status": "active",
        "source": "tac-experts-plugin",
    },
}


def detect_component_type(file_path: Path) -> str | None:
    """Detect component type from file path or frontmatter."""
    rel = str(file_path.relative_to(PLUGIN_DIR)) if file_path.is_relative_to(PLUGIN_DIR) else str(file_path)
    rel = rel.replace("\\", "/")

    # Path-based detection (ordered list, most specific first)
    for pattern, comp_type in PATH_TYPE_MAP:
        if pattern in rel:
            return comp_type

    # Frontmatter-based detection
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        if content.startswith("---"):
            fm_end = content.index("---", 3)
            fm = content[3:fm_end]
            type_match = re.search(r"^type:\s*(.+)", fm, re.MULTILINE)
            if type_match:
                return type_match.group(1).strip().lower()
    except Exception:
        pass

    # Extension-based fallback
    if file_path.suffix == ".py":
        return "hook"  # Python files are usually hooks
    if file_path.suffix == ".sh":
        return "hook"

    return None


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from markdown content."""
    if not content.startswith("---"):
        return {}, content

    try:
        fm_end = content.index("---", 3)
        fm_text = content[3:fm_end].strip()
        body = content[fm_end + 3:].strip()

        fm = {}
        for line in fm_text.split("\n"):
            if ":" in line:
                key, _, value = line.partition(":")
                key = key.strip()
                value = value.strip()
                # Handle arrays
                if value.startswith("[") and value.endswith("]"):
                    fm[key] = [v.strip().strip('"').strip("'") for v in value[1:-1].split(",")]
                else:
                    fm[key] = value.strip('"').strip("'")

        return fm, body
    except ValueError:
        return {}, content


def build_frontmatter(fm: dict) -> str:
    """Build YAML frontmatter string from dict."""
    lines = ["---"]
    for key, value in fm.items():
        if isinstance(value, list):
            lines.append(f"{key}: [{', '.join(value)}]")
        else:
            lines.append(f'{key}: "{value}"' if " " in str(value) else f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines)


def ensure_frontmatter(content: str, comp_type: str, name: str) -> str:
    """Ensure content has proper KB frontmatter."""
    fm, body = parse_frontmatter(content)

    # Add required fields if missing
    required = REQUIRED_FRONTMATTER.get(comp_type, {})
    for key, value in required.items():
        if key not in fm:
            fm[key] = value

    # Ensure name
    if "name" not in fm:
        fm["name"] = name

    # Ensure date
    if "date_synced" not in fm:
        fm["date_synced"] = datetime.now().strftime("%Y-%m-%d")
    else:
        fm["date_synced"] = datetime.now().strftime("%Y-%m-%d")

    # Ensure tags include source
    tags = fm.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",")]
    if "tac-experts-plugin" not in tags:
        tags.append("tac-experts-plugin")
    fm["tags"] = tags

    return build_frontmatter(fm) + "\n\n" + body


def get_kb_destination(comp_type: str, source_path: Path) -> Path:
    """Get the KB destination path for a component."""
    base_dir = KB_DESTINATIONS.get(comp_type)
    if not base_dir:
        return KB_ROOT / source_path.name

    name = source_path.stem
    # Expert files go into subdirectories
    if comp_type == "expert":
        # Detect domain from path (e.g., experts/tac/plan.md -> tac)
        rel = str(source_path.relative_to(PLUGIN_DIR)) if source_path.is_relative_to(PLUGIN_DIR) else str(source_path)
        parts = Path(rel).parts
        for i, part in enumerate(parts):
            if part == "experts" and i + 1 < len(parts):
                domain = parts[i + 1]
                return base_dir / domain / source_path.name
        return base_dir / source_path.name

    # Skills go into subdirectories
    if comp_type == "skill":
        return base_dir / name / source_path.name

    return base_dir / f"{name}.md"


def sync_file(source: Path, dry_run: bool = False) -> bool:
    """Sync a single file to the KB."""
    if not source.exists():
        print(f"  [ERROR] Source not found: {source}")
        return False

    comp_type = detect_component_type(source)
    if not comp_type:
        print(f"  [SKIP]  Cannot detect type for: {source.name}")
        return False

    dest = get_kb_destination(comp_type, source)
    name = source.stem

    # Read source content
    content = source.read_text(encoding="utf-8", errors="ignore")

    # For Python/shell hooks, wrap in markdown
    if source.suffix in (".py", ".sh"):
        lang = "python" if source.suffix == ".py" else "bash"
        wrapped = f"# {name}\n\n```{lang}\n{content}\n```\n"
        content = wrapped

    # Ensure proper frontmatter
    content = ensure_frontmatter(content, comp_type, name)

    if dry_run:
        print(f"  [DRY]  {source.name} -> {dest.relative_to(KB_ROOT)} ({comp_type})")
        return True

    # Create destination directory
    dest.parent.mkdir(parents=True, exist_ok=True)

    # Write to KB
    dest.write_text(content, encoding="utf-8")
    print(f"  [SYNC] {source.name} -> {dest.relative_to(KB_ROOT)} ({comp_type})")
    return True


def collect_all_syncable() -> list[Path]:
    """Collect all syncable files from the plugin."""
    files = []

    # Example agents
    agents_dir = PLUGIN_DIR / "examples" / "agents"
    if agents_dir.exists():
        files.extend(sorted(agents_dir.glob("*.md")))

    # Example commands
    commands_dir = PLUGIN_DIR / "examples" / "commands"
    if commands_dir.exists():
        files.extend(sorted(commands_dir.glob("*.md")))

    # Example hooks
    hooks_dir = PLUGIN_DIR / "examples" / "hooks"
    if hooks_dir.exists():
        files.extend(sorted(hooks_dir.glob("*.py")))

    # TAC expert files
    tac_dir = PLUGIN_DIR / "commands" / "experts" / "tac"
    if tac_dir.exists():
        files.extend(sorted(tac_dir.glob("*.md")))

    return files


def run_banner_assignment(folders: set[str], dry_run: bool):
    """Run the KB banner assignment script for affected folders."""
    if dry_run:
        print(f"\n  [DRY] Would run add_banners_all.py for folders: {', '.join(folders)}")
        return

    if not BANNER_SCRIPT.exists():
        print(f"\n  [WARN] Banner script not found: {BANNER_SCRIPT}")
        print("         MTG cards will not be assigned. Run manually:")
        print(f"         python {BANNER_SCRIPT}")
        return

    for folder in folders:
        print(f"\n  [MTG]  Assigning cards for {folder}/...")
        try:
            result = subprocess.run(
                [sys.executable, str(BANNER_SCRIPT), "--folder", folder],
                cwd=str(KB_SCRIPTS.parent),
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode == 0:
                # Count assigned cards from output
                assigned = result.stdout.count("[ASSIGN]") + result.stdout.count("[OK]")
                print(f"         {assigned} cards processed")
            else:
                print(f"         Warning: {result.stderr[:200]}")
        except subprocess.TimeoutExpired:
            print("         Timeout - banner script took too long")
        except Exception as e:
            print(f"         Error: {e}")


def main():
    parser = argparse.ArgumentParser(description="Sync plugin components to AI-Agent-KB")
    parser.add_argument("source", nargs="?", help="Source file path (relative to plugin dir)")
    parser.add_argument("--all", action="store_true", help="Sync all plugin examples")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be synced")
    parser.add_argument("--no-banners", action="store_true", help="Skip MTG card assignment")
    args = parser.parse_args()

    if not args.source and not args.all:
        parser.print_help()
        sys.exit(1)

    # Verify KB exists
    if not KB_ROOT.exists():
        print(f"Error: AI-Agent-KB not found at {KB_ROOT}")
        sys.exit(1)

    print(f"{'=' * 60}")
    print(f"Sync to AI-Agent-KB")
    print(f"{'=' * 60}")
    print(f"  Source: {'All plugin examples' if args.all else args.source}")
    print(f"  Target: {KB_ROOT}")
    if args.dry_run:
        print(f"  Mode:   DRY RUN")
    print()

    # Collect files to sync
    if args.all:
        files = collect_all_syncable()
        print(f"Found {len(files)} files to sync:\n")
    else:
        source_path = Path(args.source)
        if not source_path.is_absolute():
            source_path = PLUGIN_DIR / source_path
        files = [source_path]

    # Sync each file
    synced = 0
    failed = 0
    affected_folders: set[str] = set()

    for f in files:
        if sync_file(f, args.dry_run):
            synced += 1
            comp_type = detect_component_type(f)
            if comp_type and comp_type in KB_DESTINATIONS:
                folder_name = KB_DESTINATIONS[comp_type].name
                affected_folders.add(folder_name)
        else:
            failed += 1

    print(f"\n{'─' * 40}")
    print(f"Synced: {synced}  Failed: {failed}")

    # Run banner assignment
    if affected_folders and not args.no_banners:
        run_banner_assignment(affected_folders, args.dry_run)

    print()
    if args.dry_run:
        print("Dry run complete. Run without --dry-run to sync.")
    else:
        print("Sync complete.")


if __name__ == "__main__":
    main()
