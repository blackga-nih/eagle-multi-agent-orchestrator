---
description: Add a new evaluation test with full 8-registration checklist
argument-hint: "<test-name> <test-description> — e.g., 'test_session_resume' 'Verify session resume preserves history'"
model: opus
allowed-tools: Read, Write, Edit, Grep, Bash(python -m pytest:*)
---

# Add Evaluation Test

> Domain-specific expert extension for the eval domain. Encodes the exact
> 8-step registration checklist so every new test is wired into all systems.

## Purpose

Add a new test to the evaluation suite with all 8 required registrations.
Missing any registration causes the test to be silently skipped or miscounted.

## Test to Add: $ARGUMENTS

---

## 8-Registration Checklist

Every new test MUST be registered in all 8 locations. Check each one off
as you complete it.

### 1. Test Function (server/tests/test_eagle_sdk_eval.py)

Write the test function following this template:

```python
@pytest.mark.asyncio
async def test_{name}(eval_client):
    """
    {description}

    Tier: {basic|advanced|premium}
    Category: {session|agent|tool|streaming|auth}
    Expected: {what a passing result looks like}
    """
    # Arrange
    session_id = f"eval-{name}-{{uuid4().hex[:8]}}"

    # Act
    result = await eval_client.query(
        prompt="...",
        session_id=session_id,
        tenant_id="eval-tenant",
        tier="basic",
    )

    # Assert
    assert result is not None
    assert "expected_content" in result.lower()

    # Cleanup
    await eval_client.delete_session(session_id)
```

### 2. Test ID Registration (TEST_REGISTRY dict)

Add to the `TEST_REGISTRY` dictionary at the top of the test file:

```python
TEST_REGISTRY = {
    # ... existing tests ...
    "test_{name}": {
        "id": {next_id},
        "tier": "{basic|advanced|premium}",
        "category": "{category}",
        "description": "{description}",
        "timeout": 30,
    },
}
```

### 3. Tier Gate (conftest.py)

Ensure the test's tier is in the `TIER_GATES` mapping:

```python
TIER_GATES = {
    "basic": ["basic", "advanced", "premium"],
    "advanced": ["advanced", "premium"],
    "premium": ["premium"],
}
```

If the test uses a new tier, add it. Most tests are `basic`.

### 4. Category Tag (pytest markers)

Add the category marker to `pyproject.toml` if it doesn't exist:

```toml
[tool.pytest.ini_options]
markers = [
    "session: Session management tests",
    "agent: Agent orchestration tests",
    "tool: Tool execution tests",
    "streaming: SSE streaming tests",
    "auth: Authentication tests",
]
```

### 5. Eval Dashboard Registration (eval-stack.ts)

Add to the CloudWatch dashboard widget list:

```typescript
// In infrastructure/eval/eval-stack.ts
new cloudwatch.TextWidget({
  markdown: `### test_{name}\n{description}`,
  width: 6,
  height: 2,
}),
```

### 6. Cost Budget (cost tracking)

Add expected cost to the eval budget:

```python
# In server/tests/conftest.py or eval config
EVAL_COST_BUDGET = {
    # ... existing tests ...
    "test_{name}": {"max_tokens": 2000, "max_cost_usd": 0.05},
}
```

### 7. CI Matrix (GitHub Actions)

If the test needs special setup (e.g., DynamoDB local), add it to the CI matrix:

```yaml
# In .github/workflows/eval.yml
strategy:
  matrix:
    test-group:
      - "session"
      - "agent"
      - "{category}"  # Add if new category
```

### 8. Documentation (eval expertise.md)

Update the eval expert's expertise file with the new test:

```markdown
## Test: test_{name}
- **Category**: {category}
- **Tier**: {tier}
- **Validates**: {what it tests}
- **Added**: {date}
```

---

## Validation

After completing all 8 registrations, verify:

```bash
# Check all 8 registrations exist
echo "1. Test function:"
grep -c "async def test_{name}" server/tests/test_eagle_sdk_eval.py

echo "2. Registry entry:"
grep -c "test_{name}" server/tests/test_eagle_sdk_eval.py

echo "3. Tier gate:"
grep -c "{tier}" server/tests/conftest.py

echo "4. Category marker:"
grep -c "{category}" pyproject.toml

echo "5. Dashboard widget:"
grep -c "test_{name}" infrastructure/eval/eval-stack.ts

echo "6. Cost budget:"
grep -c "test_{name}" server/tests/conftest.py

echo "7. CI matrix:"
grep -c "{category}" .github/workflows/eval.yml

echo "8. Documentation:"
grep -c "test_{name}" .claude/commands/experts/eval/expertise.md
```

All 8 should return `1` or greater. If any returns `0`, that registration is missing.

```bash
# Run the test
python -m pytest server/tests/test_eagle_sdk_eval.py -k "test_{name}" -v
```
