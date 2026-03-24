---
allowed-tools: Bash, Read, Grep, Glob
description: "Check Strands SDK health — verify imports, Bedrock connectivity, tool registry, plugin discovery"
argument-hint: [--import | --bedrock | --tools | --full]
---

# Strands SDK Expert - Maintenance Command

Execute Strands SDK health checks and report status.

## Purpose

Validate the Strands Agents SDK installation, Bedrock connectivity, tool registry integrity, and plugin discovery pipeline.

## Usage

```
/experts:strands:maintenance --import
/experts:strands:maintenance --bedrock
/experts:strands:maintenance --tools
/experts:strands:maintenance --full
```

## Presets

| Flag | Checks | Description | AWS Required |
|------|--------|-------------|-------------|
| `--import` | Import only | Verify strands packages importable | No |
| `--bedrock` | Import + Bedrock | Check AWS/Bedrock model access | Yes |
| `--tools` | Import + tool registry | Verify TOOL_DISPATCH + plugin discovery | No |
| `--full` | Everything | All checks + tool count verification | Yes |

## Workflow

### Phase 1: SDK Import Check

```bash
cd server && python -c "
from strands import Agent, tool
from strands.models import BedrockModel
print('Strands imports OK')
print('  Agent, tool from strands')
print('  BedrockModel from strands.models')
"
```

### Phase 2: Package Version Check

```bash
pip show strands-agents 2>/dev/null
pip show strands-agents-bedrock 2>/dev/null
```

### Phase 3: Bedrock Connectivity (--bedrock, --full)

```bash
cd server && python -c "
import boto3
ident = boto3.client('sts').get_caller_identity()
print(f'AWS Account: {ident[\"Account\"]}')
print(f'ARN: {ident[\"Arn\"]}')

# Check model selection
import os, sys
sys.path.insert(0, '.')
from app.strands_agentic_service import _default_model
print(f'Default model: {_default_model()}')
"
```

### Phase 4: Tool Registry Check (--tools, --full)

```bash
cd server && python -c "
import sys; sys.path.insert(0, '.')
from app.agentic_service import TOOL_DISPATCH, TOOLS_NEEDING_SESSION
print(f'TOOL_DISPATCH: {len(TOOL_DISPATCH)} tools')
for name in sorted(TOOL_DISPATCH.keys()):
    session = ' [needs session]' if name in TOOLS_NEEDING_SESSION else ''
    print(f'  - {name}{session}')
"
```

### Phase 5: Plugin Discovery Check (--tools, --full)

```bash
cd server && python -c "
import sys; sys.path.insert(0, '.')
from eagle_skill_constants import AGENTS, SKILLS, PLUGIN_CONTENTS
print(f'AGENTS: {len(AGENTS)} discovered')
for name in sorted(AGENTS.keys()):
    print(f'  - {name}')
print(f'SKILLS: {len(SKILLS)} discovered')
for name in sorted(SKILLS.keys()):
    print(f'  - {name}')
print(f'PLUGIN_CONTENTS: {len(PLUGIN_CONTENTS)} total')
"
```

### Phase 6: Service Tool Defs Check (--tools, --full)

```bash
cd server && python -c "
import sys; sys.path.insert(0, '.')
from app.strands_agentic_service import SKILL_AGENT_REGISTRY
print(f'SKILL_AGENT_REGISTRY: {len(SKILL_AGENT_REGISTRY)} entries')
for name in sorted(SKILL_AGENT_REGISTRY.keys()):
    desc = SKILL_AGENT_REGISTRY[name]['description'][:60]
    print(f'  - {name}: {desc}...')
"
```

### Phase 7: Cross-Check (--full)

Verify TOOL_DISPATCH keys match _SERVICE_TOOL_DEFS keys:

```bash
cd server && python -c "
import sys; sys.path.insert(0, '.')
from app.agentic_service import TOOL_DISPATCH
from app.strands_agentic_service import _SERVICE_TOOL_DEFS
dispatch_keys = set(TOOL_DISPATCH.keys())
service_keys = set(_SERVICE_TOOL_DEFS.keys())
in_dispatch_only = dispatch_keys - service_keys
in_service_only = service_keys - dispatch_keys
if in_dispatch_only:
    print(f'WARNING: In TOOL_DISPATCH but not _SERVICE_TOOL_DEFS: {in_dispatch_only}')
if in_service_only:
    print(f'WARNING: In _SERVICE_TOOL_DEFS but not TOOL_DISPATCH: {in_service_only}')
if not in_dispatch_only and not in_service_only:
    print('OK: TOOL_DISPATCH and _SERVICE_TOOL_DEFS keys match (excluding utility tools)')
"
```

## Report Format

```markdown
## Strands SDK Maintenance Report

**Date**: {timestamp}
**Preset**: {--import | --bedrock | --tools | --full}
**Status**: HEALTHY | DEGRADED | FAILED

### SDK Import Check
- strands: PASS | FAIL
- strands.models: PASS | FAIL
- Versions: {versions}

### Bedrock Connectivity (if checked)
| Check | Status |
|-------|--------|
| AWS Account | {account_id} |
| Default Model | {model_id} |

### Tool Registry (if checked)
| Registry | Count |
|----------|-------|
| TOOL_DISPATCH | {N} handlers |
| _SERVICE_TOOL_DEFS | {N} descriptions |
| SKILL_AGENT_REGISTRY | {N} agents/skills |
| AGENTS (discovered) | {N} |
| SKILLS (discovered) | {N} |

### Issues Found
- {issue and fix}
```
