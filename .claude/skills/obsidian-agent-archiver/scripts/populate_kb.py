#!/usr/bin/env python3
"""
Populate Obsidian AI Agent Knowledge Base from a source repository.
Scans for ADWs, agents, skills, experts, and generates documentation.

Usage:
    python populate_kb.py \
        --source-repo "/path/to/agent-repo" \
        --obsidian-vault "/path/to/obsidian/vault"
"""

import argparse
import os
import re
import yaml
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

# Template paths (relative to skill directory)
SKILL_DIR = Path(__file__).parent.parent
TEMPLATE_DIR = SKILL_DIR / "templates"


def load_template(template_name: str) -> str:
    """Load a template file."""
    template_path = TEMPLATE_DIR / f"{template_name}-template.md"
    if template_path.exists():
        return template_path.read_text(encoding="utf-8")
    return ""


def parse_agent_file(file_path: Path) -> Dict:
    """Parse an agent markdown file with YAML frontmatter."""
    content = file_path.read_text(encoding="utf-8")

    # Extract YAML frontmatter
    frontmatter = {}
    body = content

    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            try:
                frontmatter = yaml.safe_load(parts[1]) or {}
            except yaml.YAMLError:
                pass
            body = parts[2].strip()

    return {
        "name": frontmatter.get("name", file_path.stem),
        "description": frontmatter.get("description", ""),
        "tools": frontmatter.get("tools", ""),
        "model": frontmatter.get("model", "sonnet"),
        "color": frontmatter.get("color", ""),
        "body": body,
        "source_path": str(file_path),
    }


def scan_agents(repo_path: Path) -> List[Dict]:
    """Scan for agent definitions in .claude/agents/."""
    agents = []
    agents_dir = repo_path / ".claude" / "agents"

    if agents_dir.exists():
        for agent_file in agents_dir.glob("*.md"):
            if not agent_file.name.startswith("_"):
                agents.append(parse_agent_file(agent_file))

    return agents


def scan_adw_workflows(repo_path: Path) -> List[Dict]:
    """Scan for ADW workflow files."""
    adws = []
    adw_dir = repo_path / "adws" / "adw_workflows"

    if adw_dir.exists():
        for workflow_file in adw_dir.glob("adw_*.py"):
            name = workflow_file.stem.replace("adw_", "")

            # Determine pattern from filename
            if "fix" in name:
                pattern = "plan_build_review_fix"
                steps = 4
            elif "review" in name:
                pattern = "plan_build_review"
                steps = 3
            else:
                pattern = "plan_build"
                steps = 2

            adws.append({
                "name": name,
                "pattern": pattern,
                "total_steps": steps,
                "source_path": str(workflow_file),
            })

    return adws


def scan_experts(repo_path: Path) -> List[Dict]:
    """Scan for expert definitions."""
    experts = []
    experts_dir = repo_path / ".claude" / "commands" / "experts"

    if experts_dir.exists():
        for expert_dir in experts_dir.iterdir():
            if expert_dir.is_dir():
                expertise_file = expert_dir / "expertise.yaml"
                if expertise_file.exists():
                    try:
                        content = yaml.safe_load(expertise_file.read_text(encoding="utf-8"))
                        experts.append({
                            "name": expert_dir.name,
                            "overview": content.get("overview", {}),
                            "source_path": str(expertise_file),
                        })
                    except yaml.YAMLError:
                        pass

    return experts


def scan_skills(repo_path: Path) -> List[Dict]:
    """Scan for skill definitions."""
    skills = []
    skills_dir = repo_path / ".claude" / "skills"

    if skills_dir.exists():
        for skill_dir in skills_dir.iterdir():
            if skill_dir.is_dir():
                skill_file = skill_dir / "SKILL.md"
                if skill_file.exists():
                    content = skill_file.read_text(encoding="utf-8")

                    # Parse frontmatter
                    frontmatter = {}
                    if content.startswith("---"):
                        parts = content.split("---", 2)
                        if len(parts) >= 3:
                            try:
                                frontmatter = yaml.safe_load(parts[1]) or {}
                            except:
                                pass

                    skills.append({
                        "name": frontmatter.get("name", skill_dir.name),
                        "description": frontmatter.get("description", ""),
                        "dependencies": frontmatter.get("dependencies", ""),
                        "source_path": str(skill_file),
                    })

    return skills


def create_kb_structure(obsidian_vault: Path):
    """Create the AI-Agent-KB folder structure."""
    kb_path = obsidian_vault / "AI-Agent-KB"

    folders = [
        "_assets/banners",
        "_assets/icons",
        "_assets/placeholders",
        "01-ADWs",
        "02-Agents",
        "03-Skills",
        "04-MCP-Servers",
        "05-Prompts",
        "06-Scripts",
        "07-Experts",
    ]

    for folder in folders:
        (kb_path / folder).mkdir(parents=True, exist_ok=True)
        print(f"Created: {kb_path / folder}")

    return kb_path


def generate_agent_doc(agent: Dict, kb_path: Path) -> Path:
    """Generate documentation for an agent."""
    today = datetime.now().strftime("%Y-%m-%d")

    content = f"""---
type: agent
name: "{agent['name']}"
banner: "[[_assets/banners/agent-banner.png]]"
status: active
version: 1.0.0
model: {agent.get('model', 'claude-opus-4-5-20251101')}
tools: {agent.get('tools', '[]')}
created: {today}
updated: {today}
tags: [agent]
cssclasses: [cards, cards-cover]
---

![[agent-banner.png|banner]]

# {agent['name']}

## Purpose
{agent.get('description', 'No description provided.')}

## System Prompt
```
{agent.get('body', 'See source file for full prompt.')}
```

## Source Files
- Agent Definition: `{agent['source_path']}`

## Changelog
- {today}: Auto-generated from source repository
"""

    output_path = kb_path / "02-Agents" / f"{agent['name']}.md"
    output_path.write_text(content, encoding="utf-8")
    print(f"Generated: {output_path}")

    return output_path


def generate_adw_doc(adw: Dict, kb_path: Path) -> Path:
    """Generate documentation for an ADW."""
    today = datetime.now().strftime("%Y-%m-%d")

    # Generate mermaid diagram based on pattern
    if adw['total_steps'] == 2:
        diagram = """```mermaid
graph LR
    A[Plan] --> B[Build]
    style A fill:#D97757,color:#fff
    style B fill:#C26D52,color:#fff
```"""
    elif adw['total_steps'] == 3:
        diagram = """```mermaid
graph LR
    A[Plan] --> B[Build]
    B --> C[Review]
    style A fill:#D97757,color:#fff
    style B fill:#C26D52,color:#fff
    style C fill:#191919,color:#fff
```"""
    else:
        diagram = """```mermaid
graph LR
    A[Plan] --> B[Build]
    B --> C[Review]
    C --> D[Fix]
    style A fill:#D97757,color:#fff
    style B fill:#C26D52,color:#fff
    style C fill:#191919,color:#fff
    style D fill:#5C5C5C,color:#fff
```"""

    content = f"""---
type: adw
name: "{adw['name']}"
banner: "[[_assets/banners/adw-banner.png]]"
status: active
pattern: {adw['pattern']}
total_steps: {adw['total_steps']}
created: {today}
updated: {today}
tags: [adw, workflow]
cssclasses: [cards, cards-cover, cards-2-3]
---

![[adw-banner.png|banner]]

# {adw['name']}

## Overview
{adw['total_steps']}-step AI Developer Workflow.

## Pattern
> **Type**: `{adw['pattern']}`
> **Steps**: {adw['total_steps']}

## Workflow Diagram
{diagram}

## Source Files
- Workflow: `{adw['source_path']}`

## Changelog
- {today}: Auto-generated from source repository
"""

    output_path = kb_path / "01-ADWs" / f"{adw['name']}.md"
    output_path.write_text(content, encoding="utf-8")
    print(f"Generated: {output_path}")

    return output_path


def generate_expert_doc(expert: Dict, kb_path: Path) -> Path:
    """Generate documentation for an expert."""
    today = datetime.now().strftime("%Y-%m-%d")
    overview = expert.get("overview", {})

    content = f"""---
type: expert
name: "{expert['name']}"
banner: "[[_assets/banners/expert-banner.png]]"
domain: [{expert['name']}]
status: active
created: {today}
updated: {today}
tags: [expert, domain-expertise]
cssclasses: [cards, cards-cover]
---

![[expert-banner.png|banner]]

# {expert['name'].title()} Expert

## Domain Overview
{overview.get('description', 'No description provided.')}

## Core Insight
> **Key Insight**: {overview.get('core_insight', 'See expertise file.')}

## Source Files
- Expertise YAML: `{expert['source_path']}`

## Changelog
- {today}: Auto-generated from source repository
"""

    output_path = kb_path / "07-Experts" / f"{expert['name']}.md"
    output_path.write_text(content, encoding="utf-8")
    print(f"Generated: {output_path}")

    return output_path


def generate_dashboard(kb_path: Path):
    """Generate the main dashboard."""
    template = load_template("dashboard")
    output_path = kb_path / "_Dashboard.md"
    output_path.write_text(template, encoding="utf-8")
    print(f"Generated: {output_path}")


def generate_indexes(kb_path: Path):
    """Generate index pages for each category."""
    indexes = [
        ("01-ADWs", "_ADW-Index.md", "adw", "ADW"),
        ("02-Agents", "_Agent-Index.md", "agent", "Agent"),
        ("03-Skills", "_Skill-Index.md", "skill", "Skill"),
        ("04-MCP-Servers", "_MCP-Index.md", "mcp-server", "MCP Server"),
        ("05-Prompts", "_Prompt-Index.md", "prompt", "Prompt"),
        ("06-Scripts", "_Script-Index.md", "script", "Script"),
        ("07-Experts", "_Expert-Index.md", "expert", "Expert"),
    ]

    for folder, filename, type_name, display_name in indexes:
        content = f"""---
type: index
category: {type_name}
banner: "[[_assets/banners/{type_name.split('-')[0]}-banner.png]]"
cssclasses: [cards, cards-cover, cards-2-3]
---

![[{type_name.split('-')[0]}-banner.png|banner]]

# {display_name} Index

> All {display_name}s in the knowledge base.

## Gallery View

```dataview
TABLE WITHOUT ID
  link(file.link, name) as "Name",
  status as "Status",
  file.mday as "Modified"
FROM "AI-Agent-KB/{folder}"
WHERE type = "{type_name}"
SORT file.mday DESC
```

---

[[_Dashboard|<- Back to Dashboard]]
"""
        output_path = kb_path / folder / filename
        output_path.write_text(content, encoding="utf-8")
        print(f"Generated: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Populate Obsidian AI Agent KB")
    parser.add_argument(
        "--source-repo",
        type=str,
        required=True,
        help="Path to source repository with agents/ADWs"
    )
    parser.add_argument(
        "--obsidian-vault",
        type=str,
        required=True,
        help="Path to Obsidian vault"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan only, don't create files"
    )

    args = parser.parse_args()
    source_repo = Path(args.source_repo)
    obsidian_vault = Path(args.obsidian_vault)

    print("=" * 60)
    print("Obsidian AI Agent KB Population Script")
    print("=" * 60)
    print(f"Source: {source_repo}")
    print(f"Vault: {obsidian_vault}")
    print("-" * 60)

    # Scan source repository
    print("\nScanning source repository...")
    agents = scan_agents(source_repo)
    adws = scan_adw_workflows(source_repo)
    experts = scan_experts(source_repo)
    skills = scan_skills(source_repo)

    print(f"\nFound:")
    print(f"  - {len(agents)} agents")
    print(f"  - {len(adws)} ADW workflows")
    print(f"  - {len(experts)} experts")
    print(f"  - {len(skills)} skills")

    if args.dry_run:
        print("\n[DRY RUN] No files created.")
        return

    # Create folder structure
    print("\nCreating folder structure...")
    kb_path = create_kb_structure(obsidian_vault)

    # Generate documentation
    print("\nGenerating documentation...")

    for agent in agents:
        generate_agent_doc(agent, kb_path)

    for adw in adws:
        generate_adw_doc(adw, kb_path)

    for expert in experts:
        generate_expert_doc(expert, kb_path)

    # Generate indexes and dashboard
    print("\nGenerating indexes...")
    generate_indexes(kb_path)
    generate_dashboard(kb_path)

    print("\n" + "=" * 60)
    print("Population complete!")
    print(f"Knowledge base created at: {kb_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
