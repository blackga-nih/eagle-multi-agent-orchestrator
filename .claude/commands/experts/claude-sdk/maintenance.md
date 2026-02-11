---
allowed-tools: Bash, Read, Grep, Glob
description: "Check SDK health — verify imports, test basic query, validate Bedrock connectivity, check hook types"
argument-hint: [--import | --bedrock | --query | --full]
---

# Claude SDK Expert - Maintenance Command

Execute SDK health checks and report status.

## Purpose

Validate the Claude Agent SDK installation, Bedrock connectivity, hook type availability, and optionally run a basic query test.

## Usage

```
/experts:claude-sdk:maintenance --import
/experts:claude-sdk:maintenance --bedrock
/experts:claude-sdk:maintenance --query
/experts:claude-sdk:maintenance --full
```

## Presets

| Flag | Checks | Description | AWS Required |
|------|--------|-------------|-------------|
| `--import` | Import only | Verify SDK package is importable | No |
| `--bedrock` | Import + Bedrock | Check AWS/Bedrock env vars and connectivity | Yes |
| `--query` | Import + basic query | Run a minimal query() test | Yes |
| `--full` | Everything | All checks + query test + eval tests 1-6 | Yes |

## Workflow

### Phase 1: SDK Import Check

Always run first, regardless of preset:

```bash
# Verify SDK imports
python -c "
from claude_agent_sdk import (
    query,
    ClaudeAgentOptions,
    AgentDefinition,
    ClaudeSDKClient,
    tool,
    create_sdk_mcp_server,
    HookMatcher,
    PreToolUseHookInput,
    PostToolUseHookInput,
    StopHookInput,
    SubagentStartHookInput,
    SubagentStopHookInput,
    HookContext,
)
print('All SDK imports OK')
print(f'Modules: query, ClaudeAgentOptions, AgentDefinition, ClaudeSDKClient')
print(f'Tools: tool, create_sdk_mcp_server')
print(f'Hooks: HookMatcher, PreToolUseHookInput, PostToolUseHookInput, StopHookInput')
print(f'Hooks: SubagentStartHookInput, SubagentStopHookInput, HookContext')
"
```

If this fails, report the error and stop.

### Phase 2: SDK Version Check

```bash
# Check installed version
pip show claude-agent-sdk 2>/dev/null || pip show claude_agent_sdk 2>/dev/null
```

### Phase 3: Bedrock Connectivity (--bedrock, --query, --full)

```bash
# Check environment variables
python -c "
import os
bedrock = os.environ.get('CLAUDE_CODE_USE_BEDROCK', 'not set')
region = os.environ.get('AWS_REGION', 'not set')
print(f'CLAUDE_CODE_USE_BEDROCK: {bedrock}')
print(f'AWS_REGION: {region}')
"

# Check AWS credentials
python -c "import boto3; ident = boto3.client('sts').get_caller_identity(); print(f'AWS Account: {ident[\"Account\"]}, ARN: {ident[\"Arn\"]}')" 2>&1

# Check Bedrock model access
python -c "
import boto3
client = boto3.client('bedrock', region_name='us-east-1')
models = client.list_foundation_models(byProvider='Anthropic')
for m in models.get('modelSummaries', []):
    print(f'  {m[\"modelId\"]}: {m[\"modelName\"]}')
" 2>&1
```

### Phase 4: Basic Query Test (--query, --full)

```bash
# Run a minimal query to verify SDK + Bedrock end-to-end
python -c "
import asyncio
from claude_agent_sdk import query, ClaudeAgentOptions

async def test():
    options = ClaudeAgentOptions(
        model='haiku',
        permission_mode='bypassPermissions',
        max_turns=1,
        max_budget_usd=0.02,
        env={
            'CLAUDE_CODE_USE_BEDROCK': '1',
            'AWS_REGION': 'us-east-1',
        },
    )
    msg_count = 0
    session_id = None
    async for msg in query(prompt='Say hello in exactly 3 words.', options=options):
        msg_type = type(msg).__name__
        msg_count += 1
        if msg_type == 'SystemMessage' and hasattr(msg, 'data'):
            session_id = msg.data.get('session_id') if isinstance(msg.data, dict) else None
        if msg_type == 'ResultMessage':
            usage = getattr(msg, 'usage', {})
            cost = getattr(msg, 'total_cost_usd', 0)
            print(f'  Usage: {usage}')
            print(f'  Cost: \${cost:.6f}')
    print(f'  Messages: {msg_count}')
    print(f'  Session ID: {session_id}')
    print('  Basic query: PASS' if msg_count > 0 else '  Basic query: FAIL')

asyncio.run(test())
" 2>&1
```

### Phase 5: Full Eval Test (--full only)

```bash
# Run SDK pattern tests (1-6)
python server/tests/test_eagle_sdk_eval.py --model haiku --tests 1,2,3,4,5,6
```

### Phase 6: Test File Compilation

```bash
# Verify test files compile
python -c "import py_compile; py_compile.compile('server/tests/test_eagle_sdk_eval.py', doraise=True); print('test_eagle_sdk_eval.py: OK')"
python -c "import py_compile; py_compile.compile('server/tests/test_agent_sdk.py', doraise=True); print('test_agent_sdk.py: OK')"
```

### Phase 7: Analyze and Report

1. Compile all check results
2. Report to user

## Report Format

```markdown
## Claude SDK Maintenance Report

**Date**: {timestamp}
**Preset**: {--import | --bedrock | --query | --full}
**Status**: HEALTHY | DEGRADED | FAILED

### SDK Import Check

- claude_agent_sdk: PASS | FAIL ({error})
- Version: {version}

### Bedrock Connectivity (if checked)

| Check | Status |
|-------|--------|
| CLAUDE_CODE_USE_BEDROCK | {value} |
| AWS_REGION | {value} |
| AWS credentials | PASS | FAIL |
| Bedrock model access | {N} Anthropic models |

### Basic Query Test (if run)

| Metric | Value |
|--------|-------|
| Messages received | {N} |
| Session ID | {id or None} |
| Input tokens | {N} |
| Output tokens | {N} |
| Cost | ${N} |
| Status | PASS | FAIL |

### Eval Tests (if run)

| # | Test Name | Status |
|---|-----------|--------|
| 1 | Session Creation | PASS |
| 2 | Session Resume | PASS |
| 3 | Trace Observation | PASS |
| 4 | Subagent Orchestration | PASS |
| 5 | Cost Tracking | PASS |
| 6 | Tier-Gated Tools | PASS |

### Issues Found

- {issue description and recommended fix}

### Next Steps

- {recommended actions}
```

## Quick Checks

If you just want to verify the SDK is healthy without a full run:

```bash
# Import only (fastest)
python -c "from claude_agent_sdk import query; print('OK')"

# Version check
pip show claude-agent-sdk 2>/dev/null | grep Version

# Environment check
echo "CLAUDE_CODE_USE_BEDROCK=$CLAUDE_CODE_USE_BEDROCK"
echo "AWS_REGION=$AWS_REGION"
```

## Troubleshooting

### Import Error
```bash
# Check if package is installed
pip list | grep claude
# Install if missing
pip install claude-agent-sdk
```

### Bedrock Connection Error
```bash
# Check AWS credentials
aws sts get-caller-identity
# Check region
echo $AWS_REGION
# Test Bedrock directly
aws bedrock list-foundation-models --by-provider Anthropic --query 'modelSummaries[].modelId' --output text
```

### Query Timeout
- Check network connectivity to AWS
- Verify Bedrock model access permissions
- Try with `max_turns=1` and `max_budget_usd=0.01`

### Hook Import Error
- Hooks were added in SDK 0.1.19+
- Upgrade: `pip install --upgrade claude-agent-sdk`
