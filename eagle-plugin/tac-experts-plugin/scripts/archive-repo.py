#!/usr/bin/env python3
"""
TAC Repo Archival Script

Processes a TAC project repo into the plugin catalog:
  - Updates apps/README.md with app details
  - Updates docs/advanced-lessons.md with lesson entry
  - Updates data/tags.md with lesson-specific tags
  - Updates commands/experts/tac/tac-learning-expertise.md with new lesson

Usage:
  python scripts/archive-repo.py /path/to/tac/repo
  python scripts/archive-repo.py /path/to/tac/repo --lesson 28
  python scripts/archive-repo.py /path/to/tac/repo --dry-run
"""

import argparse
import os
import re
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parent.parent
APPS_README = PLUGIN_DIR / "apps" / "README.md"
ADVANCED_LESSONS = PLUGIN_DIR / "docs" / "advanced-lessons.md"
TAGS_FILE = PLUGIN_DIR / "data" / "tags.md"
EXPERTISE_FILE = PLUGIN_DIR / "commands" / "experts" / "tac" / "tac-learning-expertise.md"

# Known lesson-to-project mappings (for auto-detection)
KNOWN_PROJECTS = {
    "claude-code-hooks-mastery": 15,
    "claude-code-hooks-multi-agent-observability": 16,
    "claude-code-damage-control": 17,
    "install-and-maintain": 18,
    "agentic-finance-review": 19,
    "beyond-mcp": 20,
    "bowser": 21,
    "agent-sandboxes": 22,
    "fork-repository-skill": 23,
    "rd-framework-context-window-mastery": 24,
    "seven-levels-agentic-prompt-formats": 25,
    "multi-agent-orchestration-the-o-agent": 26,
    "building-domain-specific-agents": 27,
    "agent-experts": None,  # Bonus
    "orchestrator-agent-with-adws": None,  # Bonus
}


def detect_tech_stack(repo_path: Path) -> list[str]:
    """Detect tech stack from repo files."""
    techs = []
    indicators = {
        "Python": ["*.py", "pyproject.toml", "requirements.txt", "uv.lock"],
        "TypeScript": ["*.ts", "tsconfig.json"],
        "Vue 3": ["*.vue"],
        "React": ["*.tsx", "*.jsx"],
        "FastAPI": ["main.py"],  # check content later
        "Bun": ["bun.lockb", "bunfig.toml"],
        "SQLite": ["*.db", "*.sqlite"],
        "PostgreSQL": ["alembic/", "migrations/"],
        "E2B SDK": [],  # check imports
        "Claude Agent SDK": [],  # check imports
    }

    for tech, patterns in indicators.items():
        for pat in patterns:
            if pat.endswith("/"):
                if any((repo_path / "apps").rglob(pat.rstrip("/"))):
                    techs.append(tech)
                    break
            else:
                if list((repo_path / "apps").rglob(pat)) if (repo_path / "apps").exists() else list(repo_path.rglob(pat)):
                    techs.append(tech)
                    break

    # Check for FastAPI in Python files
    if "Python" in techs:
        for py_file in repo_path.rglob("main.py"):
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
                if "FastAPI" in content:
                    if "FastAPI" not in techs:
                        techs.append("FastAPI")
                if "anthropic" in content or "Agent(" in content:
                    if "Claude Agent SDK" not in techs:
                        techs.append("Claude Agent SDK")
                if "e2b" in content:
                    if "E2B SDK" not in techs:
                        techs.append("E2B SDK")
            except Exception:
                pass

    return techs


def count_apps(repo_path: Path) -> list[dict]:
    """Count and describe apps in the repo."""
    apps_dir = repo_path / "apps"
    apps = []
    if not apps_dir.exists():
        return apps

    for item in sorted(apps_dir.iterdir()):
        if item.is_dir() and not item.name.startswith((".", "_")):
            app_info = {"name": item.name, "path": str(item.relative_to(repo_path))}

            # Detect app type
            has_frontend = any(item.rglob("*.vue")) or any(item.rglob("*.tsx")) or any(item.rglob("*.jsx"))
            has_backend = any(item.rglob("main.py")) or any(item.rglob("index.ts"))
            has_both = has_frontend and has_backend

            if has_both:
                app_info["type"] = "Fullstack"
            elif has_frontend:
                app_info["type"] = "Frontend"
            elif has_backend:
                app_info["type"] = "Backend"
            else:
                # Check for scripts
                if any(item.rglob("*.py")):
                    app_info["type"] = "Script"
                elif any(item.rglob("*.ts")):
                    app_info["type"] = "CLI"
                else:
                    app_info["type"] = "Other"

            # Try to get description from README
            readme = item / "README.md"
            if readme.exists():
                try:
                    text = readme.read_text(encoding="utf-8", errors="ignore")
                    lines = text.strip().split("\n")
                    for line in lines[1:10]:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            app_info["description"] = line[:120]
                            break
                except Exception:
                    pass

            apps.append(app_info)

    # Also check for standalone scripts in apps/
    for item in sorted(apps_dir.iterdir()):
        if item.is_file() and item.suffix in (".py", ".ts") and not item.name.startswith((".", "_")):
            apps.append({
                "name": item.stem,
                "path": str(item.relative_to(repo_path)),
                "type": "Script",
            })

    return apps


def extract_readme_summary(repo_path: Path) -> str:
    """Extract first meaningful paragraph from README."""
    readme = repo_path / "README.md"
    if not readme.exists():
        return f"TAC project: {repo_path.name}"

    try:
        text = readme.read_text(encoding="utf-8", errors="ignore")
        lines = text.strip().split("\n")
        summary_lines = []
        in_content = False

        for line in lines:
            stripped = line.strip()
            # Skip title and badges
            if stripped.startswith("# ") and not in_content:
                in_content = True
                continue
            if in_content and stripped and not stripped.startswith(("![", "[![", "---", "```")):
                summary_lines.append(stripped)
                if len(summary_lines) >= 3:
                    break

        return " ".join(summary_lines)[:300] if summary_lines else f"TAC project: {repo_path.name}"
    except Exception:
        return f"TAC project: {repo_path.name}"


def detect_key_pattern(repo_path: Path) -> str:
    """Detect the key TAC pattern from repo content."""
    patterns = {
        "hooks": "Hook lifecycle",
        "observability": "Real-time event streaming",
        "damage": "PreToolUse defense-in-depth",
        "install": "DAI pattern",
        "ssva": "Specialized Self-Validating Agents",
        "mcp": "Tool delivery comparison",
        "browser": "Browser automation",
        "sandbox": "E2B isolated forks",
        "fork": "Skill auto-discovery",
        "context": "Context window optimization",
        "prompt": "Prompt format escalation",
        "orchestrat": "Multi-agent orchestration",
        "domain": "Progressive agent specialization",
        "expert": "ACT-LEARN-REUSE adaptive agents",
        "adw": "AI Developer Workflows",
    }

    name = repo_path.name.lower()
    for keyword, pattern in patterns.items():
        if keyword in name:
            return pattern

    return "Agent development pattern"


def auto_detect_lesson(repo_path: Path) -> int | None:
    """Auto-detect lesson number from project name or content."""
    name = repo_path.name
    if name in KNOWN_PROJECTS:
        return KNOWN_PROJECTS[name]

    # Try to find lesson number in README
    readme = repo_path / "README.md"
    if readme.exists():
        try:
            text = readme.read_text(encoding="utf-8", errors="ignore")
            match = re.search(r"[Ll]esson\s+(\d+)", text)
            if match:
                return int(match.group(1))
        except Exception:
            pass

    return None


def generate_apps_section(repo_path: Path, lesson_num: int | None, apps: list[dict], tech_stack: list[str], key_pattern: str) -> str:
    """Generate a section for apps/README.md."""
    name = repo_path.name
    lesson_label = f"Lesson {lesson_num}" if lesson_num else "Bonus"

    lines = [
        f"\n---\n",
        f"\n## {lesson_label}: {name.replace('-', ' ').title()}\n",
        f"\n**Source**: `Desktop/tac/{name}/apps/`",
        f"**Pattern**: {key_pattern}.\n",
    ]

    for app in apps:
        lines.append(f"\n### `{app['name']}`")
        lines.append(f"**Type**: {app['type']} | **Stack**: {', '.join(tech_stack[:3])}\n")
        if "description" in app:
            lines.append(f"{app['description']}\n")

    return "\n".join(lines)


def generate_lesson_entry(repo_path: Path, lesson_num: int | None, key_pattern: str, summary: str) -> str:
    """Generate an entry for docs/advanced-lessons.md."""
    name = repo_path.name

    if lesson_num is None:
        return ""  # Don't add bonus projects to advanced-lessons

    return f"""
---

## Lesson {lesson_num}: {name.replace('-', ' ').title()}

**{key_pattern}.**

{summary}

**Source**: `Desktop/tac/{name}/`
**Apps**: See `apps/README.md` for detailed app catalog.
"""


def generate_tag_entry(lesson_num: int | None, repo_path: Path, key_pattern: str) -> str:
    """Generate a tag entry for data/tags.md."""
    if lesson_num is None:
        return ""

    tag = f"lesson-{lesson_num}-{repo_path.name[:20]}"
    return f'| `{tag}` | Lesson | {key_pattern} |\n'


def generate_expertise_entry(lesson_num: int | None, repo_path: Path, key_pattern: str, apps: list[dict]) -> str:
    """Generate an entry for tac-learning-expertise.md."""
    if lesson_num is None:
        return ""

    name = repo_path.name
    app_count = len(apps)

    return f"""
### Lesson {lesson_num}: {name.replace('-', ' ').title()}

**Pattern**: {key_pattern}
**Apps**: {app_count} reference implementations in `Desktop/tac/{name}/apps/`
**Key insight**: See `apps/README.md` for detailed breakdowns.
"""


def update_apps_readme(content: str, dry_run: bool) -> str:
    """Append content to apps/README.md before the Technology Stack Summary."""
    if not APPS_README.exists():
        print(f"  [SKIP] {APPS_README} not found")
        return ""

    text = APPS_README.read_text(encoding="utf-8", errors="ignore")

    # Insert before "## Technology Stack Summary" if it exists
    marker = "## Technology Stack Summary"
    if marker in text:
        idx = text.index(marker)
        new_text = text[:idx] + content + "\n" + text[idx:]
    else:
        new_text = text + content

    if dry_run:
        print(f"  [DRY] Would append {len(content)} chars to {APPS_README.name}")
    else:
        APPS_README.write_text(new_text, encoding="utf-8")
        print(f"  [OK]  Updated {APPS_README.name}")

    return new_text


def update_advanced_lessons(content: str, dry_run: bool) -> str:
    """Append lesson entry to docs/advanced-lessons.md."""
    if not content or not ADVANCED_LESSONS.exists():
        print(f"  [SKIP] No lesson entry to add or file missing")
        return ""

    text = ADVANCED_LESSONS.read_text(encoding="utf-8", errors="ignore")
    new_text = text.rstrip() + "\n" + content

    if dry_run:
        print(f"  [DRY] Would append {len(content)} chars to {ADVANCED_LESSONS.name}")
    else:
        ADVANCED_LESSONS.write_text(new_text, encoding="utf-8")
        print(f"  [OK]  Updated {ADVANCED_LESSONS.name}")

    return new_text


def update_tags(tag_entry: str, dry_run: bool) -> str:
    """Insert tag entry into data/tags.md under Lessons section."""
    if not tag_entry or not TAGS_FILE.exists():
        print(f"  [SKIP] No tag entry to add or file missing")
        return ""

    text = TAGS_FILE.read_text(encoding="utf-8", errors="ignore")

    # Find the end of the Lessons table (before ### Infrastructure)
    marker = "### Infrastructure"
    if marker in text:
        idx = text.index(marker)
        new_text = text[:idx] + tag_entry + "\n" + text[idx:]
    else:
        # Append before the last ---
        new_text = text.rstrip() + "\n" + tag_entry

    if dry_run:
        print(f"  [DRY] Would add tag to {TAGS_FILE.name}")
    else:
        TAGS_FILE.write_text(new_text, encoding="utf-8")
        print(f"  [OK]  Updated {TAGS_FILE.name}")

    return new_text


def update_expertise(content: str, dry_run: bool) -> str:
    """Append lesson to tac-learning-expertise.md."""
    if not content or not EXPERTISE_FILE.exists():
        print(f"  [SKIP] No expertise entry or file missing")
        return ""

    text = EXPERTISE_FILE.read_text(encoding="utf-8", errors="ignore")
    new_text = text.rstrip() + "\n" + content

    if dry_run:
        print(f"  [DRY] Would append {len(content)} chars to {EXPERTISE_FILE.name}")
    else:
        EXPERTISE_FILE.write_text(new_text, encoding="utf-8")
        print(f"  [OK]  Updated {EXPERTISE_FILE.name}")

    return new_text


def update_quick_reference(lesson_num: int | None, repo_path: Path, apps: list[dict], key_pattern: str, dry_run: bool):
    """Update the Quick Reference table in apps/README.md."""
    if lesson_num is None:
        return

    if not APPS_README.exists():
        return

    text = APPS_README.read_text(encoding="utf-8", errors="ignore")
    name = repo_path.name
    app_count = len(apps)

    new_row = f"| {lesson_num} | {name.replace('-', ' ').title()[:25]} | {name} | {app_count} | {key_pattern} |"

    # Find "**Total**:" line and insert before it
    total_marker = "**Total**:"
    if total_marker in text:
        idx = text.index(total_marker)
        # Find the line start
        line_start = text.rfind("\n", 0, idx)
        new_text = text[:line_start] + f"\n{new_row}" + text[line_start:]

        if dry_run:
            print(f"  [DRY] Would add row to Quick Reference table")
        else:
            APPS_README.write_text(new_text, encoding="utf-8")
            print(f"  [OK]  Updated Quick Reference table")


def main():
    parser = argparse.ArgumentParser(description="Archive a TAC repo into the plugin catalog")
    parser.add_argument("repo_path", help="Path to the TAC project repo")
    parser.add_argument("--lesson", default="auto", help="Lesson number (or 'auto' to detect)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without modifying files")
    args = parser.parse_args()

    repo_path = Path(args.repo_path).resolve()
    if not repo_path.exists():
        print(f"Error: {repo_path} does not exist")
        sys.exit(1)

    # Detect lesson number
    if args.lesson == "auto":
        lesson_num = auto_detect_lesson(repo_path)
    else:
        lesson_num = int(args.lesson) if args.lesson != "none" else None

    # Extract metadata
    apps = count_apps(repo_path)
    tech_stack = detect_tech_stack(repo_path)
    key_pattern = detect_key_pattern(repo_path)
    summary = extract_readme_summary(repo_path)

    # Print summary
    print(f"{'=' * 60}")
    print(f"TAC Repo Archival: {repo_path.name}")
    print(f"{'=' * 60}")
    print(f"  Lesson:      {lesson_num or 'Bonus'}")
    print(f"  Apps:        {len(apps)}")
    print(f"  Tech stack:  {', '.join(tech_stack) or 'Unknown'}")
    print(f"  Key pattern: {key_pattern}")
    print(f"  Summary:     {summary[:80]}...")
    print()

    if apps:
        print("  Apps found:")
        for app in apps:
            print(f"    - {app['name']} ({app['type']})")
        print()

    if args.dry_run:
        print("[DRY RUN MODE - no files will be modified]\n")

    # Generate content
    apps_section = generate_apps_section(repo_path, lesson_num, apps, tech_stack, key_pattern)
    lesson_entry = generate_lesson_entry(repo_path, lesson_num, key_pattern, summary)
    tag_entry = generate_tag_entry(lesson_num, repo_path, key_pattern)
    expertise_entry = generate_expertise_entry(lesson_num, repo_path, key_pattern, apps)

    # Apply updates
    print("Updating files:")
    update_apps_readme(apps_section, args.dry_run)
    update_advanced_lessons(lesson_entry, args.dry_run)
    update_tags(tag_entry, args.dry_run)
    update_expertise(expertise_entry, args.dry_run)

    print()
    if args.dry_run:
        print("Dry run complete. Run without --dry-run to apply changes.")
    else:
        print(f"Archival complete for {repo_path.name}.")
        print(f"Review changes in apps/README.md, docs/advanced-lessons.md, data/tags.md")


if __name__ == "__main__":
    main()
