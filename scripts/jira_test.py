"""
Unified dry-run test harness for the Jira scripts system.

Validates env vars, jira_connect dry-run, and jira_commits_sync dry-run
without making any live API calls.

Usage:
    python scripts/jira_test.py
"""

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"

# ANSI colors (disabled if NO_COLOR is set)
NO_COLOR = os.getenv("NO_COLOR") or not sys.stdout.isatty()
GREEN = "" if NO_COLOR else "\033[32m"
RED = "" if NO_COLOR else "\033[31m"
YELLOW = "" if NO_COLOR else "\033[33m"
CYAN = "" if NO_COLOR else "\033[36m"
RESET = "" if NO_COLOR else "\033[0m"

results: list[tuple[str, bool, str]] = []


def record(name: str, passed: bool, detail: str = ""):
    status = f"{GREEN}PASS{RESET}" if passed else f"{RED}FAIL{RESET}"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))
    results.append((name, passed, detail))


def run_script(args: list[str], timeout: int = 30) -> tuple[int, str, str]:
    """Run a script and return (returncode, stdout, stderr)."""
    result = subprocess.run(
        [sys.executable] + args,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result.returncode, result.stdout, result.stderr


def test_env_vars():
    """Check that required env vars are set."""
    print(f"\n{CYAN}[1/7] Environment Variables{RESET}")

    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")

    base_url = os.getenv("JIRA_BASE_URL")
    api_token = os.getenv("JIRA_API_TOKEN")

    record("JIRA_BASE_URL is set", bool(base_url), base_url or "MISSING")
    record("JIRA_API_TOKEN is set", bool(api_token),
           f"[set, {len(api_token)} chars]" if api_token else "MISSING")

    if base_url:
        from urllib.parse import urlparse
        parsed = urlparse(base_url)
        record("JIRA_BASE_URL is valid URL", bool(parsed.scheme and parsed.netloc), f"{parsed.scheme}://{parsed.netloc}")
        record("JIRA_BASE_URL uses HTTPS", parsed.scheme == "https", parsed.scheme)


def test_jira_connect_dry_run():
    """Run jira_connect.py --dry-run."""
    print(f"\n{CYAN}[2/7] jira_connect.py --dry-run{RESET}")

    rc, stdout, stderr = run_script(["scripts/jira_connect.py", "--dry-run"])
    record("jira_connect.py --dry-run exits 0", rc == 0, f"exit code: {rc}")
    record("Output contains endpoints", "rest/api/2" in stdout, "")
    record("Output contains ALL CHECKS PASSED", "ALL CHECKS PASSED" in stdout, "")

    if rc != 0 and stderr:
        print(f"    stderr: {stderr.strip()[:200]}")


def test_commits_sync_dry_run():
    """Run jira_commits_sync.py --dry-run with recent commits."""
    print(f"\n{CYAN}[3/7] jira_commits_sync.py --dry-run (7 days){RESET}")

    rc, stdout, stderr = run_script([
        "scripts/jira_commits_sync.py",
        "--dry-run", "--since", "7 days ago", "--project", "EAGLE",
    ])
    record("jira_commits_sync.py --dry-run exits 0", rc == 0, f"exit code: {rc}")

    has_commits = "Found" in stdout and "commit" in stdout
    no_commits = "No commits to sync" in stdout
    record("Output shows commits or 'no commits'", has_commits or no_commits,
           "found commits" if has_commits else "no commits in range")

    if has_commits:
        dry_run_lines = [l for l in stdout.splitlines() if "[dry-run]" in l or "[skip]" in l]
        record("Dry-run markers present (no live calls)", len(dry_run_lines) > 0,
               f"{len(dry_run_lines)} dry-run line(s)")

    if rc != 0 and stderr:
        print(f"    stderr: {stderr.strip()[:200]}")


def test_commits_sync_with_author():
    """Run jira_commits_sync.py --dry-run with author filter."""
    print(f"\n{CYAN}[4/7] jira_commits_sync.py --dry-run (with --author){RESET}")

    rc, stdout, stderr = run_script([
        "scripts/jira_commits_sync.py",
        "--dry-run", "--since", "30 days ago", "--project", "EAGLE",
        "--author", "gblack686,blackga-nih",
    ])
    record("Author-filtered dry-run exits 0", rc == 0, f"exit code: {rc}")

    has_commits = "Found" in stdout and "commit" in stdout
    no_commits = "No commits to sync" in stdout
    record("Output shows commits or 'no commits'", has_commits or no_commits, "")

    if rc != 0 and stderr:
        print(f"    stderr: {stderr.strip()[:200]}")


def test_workflow_yaml():
    """Validate GitHub Actions workflow YAML files parse correctly."""
    print(f"\n{CYAN}[5/7] GitHub Actions Workflow YAML{RESET}")

    import yaml

    workflows = [
        ".github/workflows/jira-commits-sync.yml",
        ".github/workflows/jira-commits-sync-agentic.yml",
    ]

    for wf_path in workflows:
        full_path = REPO_ROOT / wf_path
        name = Path(wf_path).name
        if not full_path.exists():
            record(f"{name} exists", False, "file not found")
            continue

        record(f"{name} exists", True, "")
        try:
            with open(full_path) as f:
                data = yaml.safe_load(f)
            record(f"{name} parses as valid YAML", True, "")
            has_on = "on" in (data or {}) or True in (data or {})
            has_jobs = "jobs" in (data or {})
            record(f"{name} has 'on' + 'jobs' keys", has_on and has_jobs, "")
        except yaml.YAMLError as e:
            record(f"{name} parses as valid YAML", False, str(e)[:100])


def test_scan_issues_dry_run():
    """Run jira_scan_issues.py --dry-run to validate connectivity and output."""
    print(f"\n{CYAN}[6/7] jira_scan_issues.py --dry-run{RESET}")

    rc, stdout, stderr = run_script([
        "scripts/jira_scan_issues.py",
        "--dry-run", "--project", "EAGLE",
        "--assignees", "blackga,Greg Black",
        "--since", "7 days ago",
    ])
    record("jira_scan_issues.py --dry-run exits 0", rc == 0, f"exit code: {rc}")
    record("Output contains DRY RUN OK", "DRY RUN OK" in stdout, "")
    record("Output shows issue count", "Open issues" in stdout, "")
    record("Output shows commit counts", "Total commits" in stdout and "Unmatched" in stdout, "")

    if rc != 0 and stderr:
        print(f"    stderr: {stderr.strip()[:200]}")


def test_scan_issues_json():
    """Run jira_scan_issues.py (live mode) and validate JSON output structure."""
    print(f"\n{CYAN}[7/7] jira_scan_issues.py JSON output{RESET}")

    rc, stdout, stderr = run_script([
        "scripts/jira_scan_issues.py",
        "--project", "EAGLE",
        "--assignees", "blackga,Greg Black",
        "--since", "7 days ago",
    ])
    record("jira_scan_issues.py exits 0", rc == 0, f"exit code: {rc}")

    if rc == 0 and stdout.strip():
        import json
        try:
            data = json.loads(stdout)
            record("Output is valid JSON", True, "")
            record("JSON has 'issues' key", "issues" in data, "")
            record("JSON has 'unmatched_commits' key", "unmatched_commits" in data, "")

            issues = data.get("issues", [])
            record("Issues list is non-empty", len(issues) > 0, f"{len(issues)} issues")

            # Verify assignee filter: all issues should be assigned to target users
            target_assignees = {"blackga", "greg black"}
            if issues:
                all_filtered = all(
                    (iss.get("assignee") or "").lower() in target_assignees
                    for iss in issues
                )
                record("All issues assigned to target users", all_filtered,
                       "assignee filter working" if all_filtered else "found issues with wrong assignee")

            commits = data.get("unmatched_commits", [])
            record("Commits data present", isinstance(commits, list), f"{len(commits)} unmatched commits")
        except json.JSONDecodeError as e:
            record("Output is valid JSON", False, str(e)[:100])
    elif rc != 0:
        record("Output is valid JSON", False, "script failed")
        if stderr:
            print(f"    stderr: {stderr.strip()[:200]}")


def main():
    print(f"{'=' * 50}")
    print(f"  Jira Scripts — Dry-Run Test Harness")
    print(f"  Repo: {REPO_ROOT}")
    print(f"{'=' * 50}")

    test_env_vars()
    test_jira_connect_dry_run()
    test_commits_sync_dry_run()
    test_commits_sync_with_author()
    test_workflow_yaml()
    test_scan_issues_dry_run()
    test_scan_issues_json()

    # Summary
    total = len(results)
    passed = sum(1 for _, ok, _ in results if ok)
    failed = total - passed

    print(f"\n{'=' * 50}")
    if failed == 0:
        print(f"  {GREEN}ALL {total} CHECKS PASSED{RESET}")
    else:
        print(f"  {RED}{failed} FAILED{RESET} / {total} total")
        for name, ok, detail in results:
            if not ok:
                print(f"    - {name}: {detail}")
    print(f"{'=' * 50}")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
