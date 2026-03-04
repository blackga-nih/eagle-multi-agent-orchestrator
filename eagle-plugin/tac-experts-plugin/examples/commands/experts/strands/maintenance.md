---
allowed-tools: Bash, Read, Grep, Glob
description: "Check Strands SDK health — verify imports, test BedrockModel, validate basic Agent invocation"
argument-hint: [--import | --bedrock | --agent | --full]
---

# Strands SDK Expert - Maintenance Command

Execute Strands SDK health checks and report status.

## Purpose

Validate the Strands Agents SDK installation, BedrockModel connectivity, Agent construction, and optionally run a basic invocation test.

## Usage

```
/experts:strands:maintenance --import
/experts:strands:maintenance --bedrock
/experts:strands:maintenance --agent
/experts:strands:maintenance --full
```

## Presets

| Flag | Checks | Description | AWS Required |
|------|--------|-------------|-------------|
| `--import` | Import only | Verify SDK package is importable | No |
| `--bedrock` | Import + BedrockModel | Check BedrockModel construction + AWS connectivity | Yes |
| `--agent` | Import + basic Agent | Run a minimal Agent invocation | Yes |
| `--full` | Everything | All checks + Agent test + multi-agent test | Yes |

## Workflow

### Phase 1: SDK Import Check

Always run first, regardless of preset:

```bash
# Verify Strands imports
python -c "
from strands import Agent, tool
from strands.models import BedrockModel
print('Core imports OK: Agent, tool, BedrockModel')

# Check optional imports
try:
    from strands.multiagent import Swarm, Graph, GraphBuilder
    print('Multi-agent imports OK: Swarm, Graph, GraphBuilder')
except ImportError as e:
    print(f'Multi-agent imports FAILED: {e}')

try:
    from strands.session import FileSessionManager, S3SessionManager
    print('Session imports OK: FileSessionManager, S3SessionManager')
except ImportError as e:
    print(f'Session imports FAILED: {e}')

try:
    from strands.handlers import CallbackHandler
    print('Handler imports OK: CallbackHandler')
except ImportError as e:
    print(f'Handler imports FAILED: {e}')
"
```

If this fails, report the error and stop.

### Phase 2: SDK Version Check

```bash
# Check installed version
pip show strands-agents 2>/dev/null || echo "strands-agents NOT installed"
pip show strands-agents-tools 2>/dev/null || echo "strands-agents-tools NOT installed (optional)"
pip show agent-skills-sdk 2>/dev/null || echo "agent-skills-sdk NOT installed (optional)"
```

### Phase 3: BedrockModel Connectivity (--bedrock, --agent, --full)

```bash
# Check AWS credentials
python -c "
import boto3
ident = boto3.client('sts').get_caller_identity()
print(f'AWS Account: {ident[\"Account\"]}')
print(f'ARN: {ident[\"Arn\"]}')
" 2>&1

# Check BedrockModel construction
python -c "
from strands.models import BedrockModel
model = BedrockModel(
    model_id='us.anthropic.claude-haiku-4-20250514-v1:0',
    region_name='us-east-1',
)
print(f'BedrockModel: OK')
print(f'Model ID: us.anthropic.claude-haiku-4-20250514-v1:0')
print(f'Region: us-east-1')
" 2>&1

# Check Bedrock model access
python -c "
import boto3
client = boto3.client('bedrock', region_name='us-east-1')
models = client.list_foundation_models(byProvider='Anthropic')
for m in models.get('modelSummaries', []):
    print(f'  {m[\"modelId\"]}: {m[\"modelName\"]}')
" 2>&1
```

### Phase 4: Basic Agent Test (--agent, --full)

```bash
# Run a minimal Agent invocation
python -c "
from strands import Agent
from strands.models import BedrockModel

model = BedrockModel(
    model_id='us.anthropic.claude-haiku-4-20250514-v1:0',
    region_name='us-east-1',
)

agent = Agent(
    model=model,
    system_prompt='You are a test agent. Be extremely brief.',
    callback_handler=None,
)

result = agent('Say hello in exactly 3 words.')
print(f'Result: {result}')
print(f'Stop reason: {result.stop_reason}')
print('Basic Agent invocation: PASS')
" 2>&1
```

### Phase 5: Tool Test (--full only)

```bash
# Test @tool decorator
python -c "
from strands import Agent, tool
from strands.models import BedrockModel

@tool
def add_numbers(a: int, b: int) -> str:
    \"\"\"Add two numbers together.

    Args:
        a: First number
        b: Second number
    \"\"\"
    return str(a + b)

model = BedrockModel(
    model_id='us.anthropic.claude-haiku-4-20250514-v1:0',
    region_name='us-east-1',
)

agent = Agent(
    model=model,
    system_prompt='Use the add_numbers tool to answer math questions. Be brief.',
    tools=[add_numbers],
    callback_handler=None,
)

result = agent('What is 17 + 25?')
print(f'Result: {result}')
tool_used = '42' in str(result)
print(f'Tool used correctly: {tool_used}')
print('Tool test: PASS' if tool_used else 'Tool test: FAIL')
" 2>&1
```

### Phase 6: Migration Readiness Check (--full only)

```bash
# Check if current EAGLE infrastructure is compatible
python -c "
import sys
sys.path.insert(0, 'server')

# Check plugin store (DynamoDB prompt infrastructure)
try:
    import importlib.util
    spec = importlib.util.find_spec('app.plugin_store', 'server')
    print('plugin_store.py: FOUND')
except:
    print('plugin_store.py: check manually at server/app/plugin_store.py')

# Check skill constants
try:
    from eagle_skill_constants import SKILL_CONSTANTS, SKILL_AGENT_REGISTRY
    print(f'SKILL_CONSTANTS: {len(SKILL_CONSTANTS)} skills loaded')
    print(f'SKILL_AGENT_REGISTRY: {len(SKILL_AGENT_REGISTRY)} agents registered')
except Exception as e:
    print(f'eagle_skill_constants: {e}')

# Check eagle-plugin directory
import os
plugin_dir = 'eagle-plugin'
if os.path.isdir(plugin_dir):
    agents = os.listdir(os.path.join(plugin_dir, 'agents')) if os.path.isdir(os.path.join(plugin_dir, 'agents')) else []
    skills = os.listdir(os.path.join(plugin_dir, 'skills')) if os.path.isdir(os.path.join(plugin_dir, 'skills')) else []
    print(f'eagle-plugin/agents/: {len(agents)} agents')
    print(f'eagle-plugin/skills/: {len(skills)} skills')
else:
    print('eagle-plugin/: NOT FOUND')
" 2>&1
```

### Phase 7: Analyze and Report

1. Compile all check results
2. Report to user

## Report Format

```markdown
## Strands SDK Maintenance Report

**Date**: {timestamp}
**Preset**: {--import | --bedrock | --agent | --full}
**Status**: HEALTHY | DEGRADED | FAILED

### SDK Import Check

- strands-agents: PASS | FAIL ({error})
- Version: {version}
- Multi-agent: PASS | FAIL
- Sessions: PASS | FAIL

### BedrockModel Connectivity (if checked)

| Check | Status |
|-------|--------|
| AWS credentials | PASS | FAIL |
| BedrockModel construction | PASS | FAIL |
| Bedrock model access | {N} Anthropic models |

### Basic Agent Test (if run)

| Metric | Value |
|--------|-------|
| Result | {text} |
| Stop reason | {reason} |
| Status | PASS | FAIL |

### Tool Test (if run)

| Metric | Value |
|--------|-------|
| Tool executed | Yes / No |
| Correct result | Yes / No |
| Status | PASS | FAIL |

### Migration Readiness (if checked)

| Component | Status |
|-----------|--------|
| plugin_store.py | FOUND / MISSING |
| SKILL_CONSTANTS | {N} skills |
| SKILL_AGENT_REGISTRY | {N} agents |
| eagle-plugin/ | {N} agents, {N} skills |

### Issues Found

- {issue description and recommended fix}

### Next Steps

- {recommended actions}
```

## Troubleshooting

### Import Error
```bash
pip install strands-agents
pip install strands-agents-tools  # optional: pre-built tools
pip install agent-skills-sdk      # optional: AgentSkills.io
```

### BedrockModel Error
```bash
# Check AWS credentials
aws sts get-caller-identity
# Check Bedrock access
aws bedrock list-foundation-models --by-provider Anthropic --query 'modelSummaries[].modelId' --output text
```

### Agent Timeout
- Check network connectivity to AWS
- Verify Bedrock model access permissions
- Try with shorter prompt and `callback_handler=None`
