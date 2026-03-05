---
allowed-tools: Read, Write, Glob, Grep, Bash
description: "Validate GitHub Actions workflow syntax, check repository state, and report Git/CI-CD health"
argument-hint: [--all | --workflows | --branches | --secrets]
---

# Git/CI-CD Expert - Maintenance Command

Validate workflow syntax, check repository state, and report CI/CD health.

## Usage

```
/experts:git:maintenance --all
/experts:git:maintenance --workflows
/experts:git:maintenance --branches
```

## Presets

| Flag | Checks | Description |
|------|--------|-------------|
| `--all` | Everything | Full Git/CI-CD health check |
| `--workflows` | YAML validation | Syntax check all workflow files |
| `--branches` | Branch state | List branches, check main status |
| `--secrets` | Secret usage | Audit secrets referenced in workflows |

## Workflow

### Phase 1: Workflow YAML Validation

```bash
python -c "
import yaml, glob, os
print('GitHub Actions Workflow Validation')
print('=' * 55)
files = glob.glob('.github/workflows/*.yml')
if not files:
    print('  No workflow files found')
else:
    for f in files:
        try:
            with open(f) as fh:
                data = yaml.safe_load(fh)
            triggers = list(data.get('on', {}).keys()) if isinstance(data.get('on'), dict) else [str(data.get('on', 'unknown'))]
            jobs = list(data.get('jobs', {}).keys())
            print(f'  {os.path.basename(f):40s} OK')
            print(f'    Triggers: {triggers}')
            print(f'    Jobs:     {jobs}')
        except Exception as e:
            print(f'  {os.path.basename(f):40s} FAIL')
            print(f'    Error: {e}')
    print(f'  Summary: {len(files)} workflow files checked')
"
```

### Phase 2: Branch State Check

```bash
echo "Branch State Check"
echo "====================================================="
echo "  Current branch: $(git branch --show-current)"
echo "  Main branch status:"
git log main --oneline -5 2>/dev/null || echo "  main branch not found locally"
echo ""
echo "  Recent branches:"
git branch --sort=-committerdate --format='  %(refname:short) (%(committerdate:relative))' | head -10
echo ""
echo "  Remote tracking:"
git remote -v
```

### Phase 3: Secrets Audit

```bash
python -c "
import re, glob
print()
print('Secrets Referenced in Workflows')
print('=' * 55)
secrets = set()
for f in glob.glob('.github/workflows/*.yml'):
    with open(f) as fh:
        content = fh.read()
    found = re.findall(r'secrets\\.([A-Z_]+)', content)
    for s in found:
        secrets.add(s)
for s in sorted(secrets):
    print(f'  - {s}')
print(f'  Total: {len(secrets)} unique secrets referenced')
"
```

### Phase 4: Action Version Audit

```bash
python -c "
import re, glob
print()
print('Actions Version Audit')
print('=' * 55)
for f in sorted(glob.glob('.github/workflows/*.yml')):
    with open(f) as fh:
        content = fh.read()
    actions = re.findall(r'uses:\\s*([\\w-]+/[\\w-]+)@(\\S+)', content)
    if actions:
        import os
        print(f'  {os.path.basename(f)}:')
        for name, version in actions:
            is_sha = len(version) == 40 and all(c in '0123456789abcdef' for c in version)
            pin_status = 'SHA-pinned' if is_sha else 'VERSION TAG'
            print(f'    {name}@{version[:12]}... [{pin_status}]')
"
```

## Report Format

```markdown
## Git/CI-CD Maintenance Report

### Workflow Validation

| File | Status | Jobs | Triggers |
|------|--------|------|----------|
| deploy.yml | OK | 2 | push, PR, dispatch |
| claude-merge-analysis.yml | OK | 2 | PR, comments, issues |

### Branch State

- Current: {branch}
- Main: {last commit}
- Active branches: {count}

### Secrets

{count} unique secrets referenced across workflows

### Action Pinning

- SHA-pinned: {count}
- Version tag: {count}
- Recommendation: {pin any floating tags}
```
