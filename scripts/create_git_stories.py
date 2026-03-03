"""Create 4 new Jira stories for git workflow, folder structure, .gitignore, and hooks."""
import os
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

BASE = os.getenv("JIRA_BASE_URL")
TOKEN = os.getenv("JIRA_API_TOKEN")
headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

new_stories = [
    {
        "summary": "Define Git Branching Strategy and PR Workflow",
        "labels": ["git", "dx", "assignee:aws-dev"],
        "description": (
            "Establish a consistent branching model and pull request workflow for the team.\n\n"
            "*Goals:*\n"
            "- Choose branching model: trunk-based vs GitFlow vs GitHub Flow\n"
            "- Define branch naming conventions: feat/, fix/, sync/, chore/\n"
            "- Set PR merge strategy: squash vs merge commit vs rebase\n"
            "- Require PR description template (summary, test plan, breaking changes)\n"
            "- Configure branch protection rules on main: require review + CI green\n"
            "- Document the hub-and-spoke sync model (blackga-nih hub, gblack686 upstream, CBIIT sm_eagle)\n\n"
            "*Owner:* AWS/infra dev (knows client VCS policies)\n"
            "*Expert domain:* git"
        ),
    },
    {
        "summary": "Audit and Standardize Repository Folder Structure",
        "labels": ["git", "dx", "assignee:aws-dev"],
        "description": (
            "Review and clean up the top-level folder layout to match project conventions.\n\n"
            "*Scope:*\n"
            "- Audit root-level loose files (*.txt, *.docx, *.zip) and move to docs/ or archive/\n"
            "- Verify client/ backend/ server/ infrastructure/ eagle-plugin/ naming is consistent\n"
            "- Ensure scripts/ only contains automation (no one-off experiments)\n"
            "- Confirm .claude/ structure matches TAC expert layout\n"
            "- Remove or archive stale branches referenced in local worktrees\n"
            "- Add CONTRIBUTING.md with folder map and guidance on where new files belong\n\n"
            "*Owner:* AWS/infra dev (familiar with client standards)\n"
            "*Expert domain:* git, deployment"
        ),
    },
    {
        "summary": "Review and Harden .gitignore for Multi-Tenant Repo",
        "labels": ["git", "security", "assignee:aws-dev"],
        "description": (
            "Ensure .gitignore protects secrets and account-specific files across all environments.\n\n"
            "*Must exclude:*\n"
            "- .env, .env.local, .env.* (all environments)\n"
            "- infrastructure/cdk-eagle/bootstrap-*.yaml (account-specific bootstrap)\n"
            "- infrastructure/cdk-eagle/cdk.out/ (synth artifacts)\n"
            "- node_modules/, __pycache__/, .venv/\n"
            "- .claude/settings.local.json (local agent permissions)\n"
            "- Any *.pem, *.key, *.p12 certificate files\n"
            "- IDE-specific: .idea/, .vscode/settings.json, .DS_Store\n\n"
            "*Also verify:*\n"
            "- The hub vs spoke .gitignore delta is intentional and documented\n"
            "- CI/CD pipeline does not accidentally commit ignored files\n\n"
            "*Owner:* AWS/infra dev\n"
            "*Expert domain:* git, hooks"
        ),
    },
    {
        "summary": "Implement Git Hooks for Code Quality Gates",
        "labels": ["hooks", "git", "dx", "assignee:greg"],
        "description": (
            "Add pre-commit and commit-msg hooks to enforce code quality before changes reach main.\n\n"
            "*Pre-commit hooks:*\n"
            "- Run ruff check on staged Python files (backend)\n"
            "- Run tsc --noEmit on staged TypeScript files (frontend)\n"
            "- Block commits that add secrets patterns (grep for AWS key prefixes, tokens)\n"
            "- Warn if NCI account ID (695681773636) is staged in non-infra files\n\n"
            "*Commit-msg hooks:*\n"
            "- Enforce conventional commit format: type(scope): description\n"
            "- Valid types: feat, fix, docs, chore, refactor, test, ci\n\n"
            "*Tooling options:*\n"
            "- pre-commit framework (.pre-commit-config.yaml) for team-wide hooks\n"
            "- Claude Code hooks (.claude/hooks/) for agent-aware gating\n\n"
            "*Owner:* Greg (Claude Code hooks expert)\n"
            "*Expert domain:* hooks, git"
        ),
    },
]

created = []
for story in new_stories:
    payload = {
        "fields": {
            "project": {"key": "EAGLE"},
            "summary": story["summary"],
            "issuetype": {"name": "Story"},
            "labels": story["labels"],
            "description": story["description"],
        }
    }
    r = requests.post(f"{BASE}/rest/api/2/issue", headers=headers, json=payload)
    if r.status_code in (200, 201):
        key = r.json()["key"]
        created.append((key, story["summary"], story["labels"]))
        print(f"[CREATED] {key} -- {story['summary']}")
    else:
        print(f"[FAIL] {story['summary'][:60]}: {r.status_code} {r.text[:300]}")

print()
for key, summary, labels in created:
    print(f"  {key}: {summary}")
    print(f"    labels: {labels}")
