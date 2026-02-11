# Claude Merge Analysis Workflow Documentation

This document describes the GitHub Actions workflow that integrates Claude Code for automated merge analysis, report generation, and feature branch creation.

## Overview

The workflow (`claude-merge-analysis.yml`) implements an automation system that:

1. **Triggers** on pull requests, issues, or comments
2. **Analyzes** code changes using Claude Code
3. **Generates** structured analysis reports and action plans
4. **Creates** feature branches with recommended changes (optional)

## Architecture & Patterns

### Key Patterns Used

This implementation follows established patterns from:

1. **anthropics/claude-code-action** - Official Claude Code GitHub Action
   - Repository: https://github.com/anthropics/claude-code-action
   - Pattern: Structured JSON outputs for automation
   - Pattern: Multi-step workflows with context passing

2. **pull_request_target Event** - Secure fork handling
   - Pattern: Run with base-repo write permissions for external PRs
   - Security: Prevents malicious code execution from forks
   - Reference: Custom automations branch documentation

3. **Structured Outputs Pattern** - Validated JSON between steps
   - Pattern: Claude generates validated JSON that becomes GitHub Action outputs
   - Pattern: Context passing via artifacts and outputs
   - Enables deterministic automation

## Workflow Structure

### Job 1: Merge Analysis

**Purpose**: Analyze PR/issue and generate structured plan

**Key Steps**:
1. Checkout repository (with security considerations for forks)
2. Collect PR/Issue context (diff, metadata)
3. Run Claude Code Action with merge analysis prompt
4. Parse structured JSON output
5. Post report as PR/Issue comment
6. Upload analysis artifact

**Outputs**:
- `analysis-report`: Human-readable summary
- `structured-plan`: JSON plan for automation
- `suggested-branch`: Recommended feature branch name
- `has-changes`: Boolean indicating if changes are needed

**Claude Prompt Strategy**:
- Instructs Claude to analyze merge conflicts, risks, test coverage
- Requires structured JSON output with specific schema
- Includes PR diff and repository context

### Job 2: Create Feature Branch

**Purpose**: Implement recommendations and create feature branch

**Key Steps**:
1. Download analysis artifact
2. Create feature branch from suggested name
3. Apply recommended changes via Claude using the analysis plan
4. Commit and push changes
5. Create pull request

**Implementation**:
- Uses `context_files` to pass the analysis plan to Claude
- Claude reads the structured plan and implements recommended changes
- Changes are based on the analysis findings

## Setup Requirements

### 1. Install Claude GitHub App

1. Install the Claude GitHub App on your repository
2. Required permissions:
   - Contents: Read/Write
   - Issues: Read/Write
   - Pull Requests: Read/Write

**Reference**: https://code.claude.com/docs/en/github-actions

### 2. Configure Secrets

Add to repository secrets:

**Option A: Anthropic API Key**
```
ANTHROPIC_API_KEY=your-api-key
```

**Option B: AWS Bedrock** (if using Bedrock)
```
AWS_ACCESS_KEY_ID=your-key
AWS_SECRET_ACCESS_KEY=your-secret
AWS_REGION=us-east-1
```

**Option C: Google Vertex AI** (if using Vertex)
```
GOOGLE_APPLICATION_CREDENTIALS=path-to-credentials
```

### 3. Workflow Permissions

The workflow requires:
- `contents: write` - Create branches and PRs
- `issues: write` - Comment on issues
- `pull-requests: write` - Create PRs
- `id-token: write` - OIDC for cloud providers

## Trigger Mechanisms

### 1. Pull Request Events
```yaml
pull_request:
  types: [opened, synchronize, reopened]
```
- Automatically analyzes PRs when opened or updated
- Uses `pull_request_target` for secure fork handling

### 2. Issue Comments
```yaml
issue_comment:
  types: [created]
```
- Trigger by mentioning `@claude` in a comment
- Example: `@claude analyze merge`

### 3. Issue Labels
```yaml
issues:
  types: [opened, labeled]
```
- Trigger when issue has `claude-analyze` label
- Useful for manual triggering

## Structured Output Schema

Claude is instructed to output JSON with this schema:

```json
{
  "summary": "Brief summary of analysis",
  "risk_level": "low|medium|high",
  "conflicts_detected": boolean,
  "test_coverage_adequate": boolean,
  "action_items": [
    {
      "priority": "high|medium|low",
      "description": "What needs to be done",
      "files_affected": ["path/to/file1"]
    }
  ],
  "suggested_branch_name": "feature/claude-analysis-YYYYMMDD-HHMMSS",
  "recommended_changes": {
    "files_to_modify": ["path/to/file"],
    "suggested_commits": [
      {
        "message": "Commit message",
        "files": ["path/to/file"]
      }
    ]
  },
  "has_changes": boolean
}
```

## Context Passing Implementation

### Pattern: Artifact-Based Context Passing

The workflow passes the analysis plan from Job 1 to Job 2 via artifacts:

```yaml
# Job 1: Upload analysis plan
- name: Upload Analysis Artifact
  uses: actions/upload-artifact@v4
  with:
    name: claude-analysis-plan
    path: claude_analysis_plan.json

# Job 2: Download and use
- name: Download Analysis Artifact
  uses: actions/download-artifact@v4
  with:
    name: claude-analysis-plan

- name: Apply Recommended Changes
  uses: anthropics/claude-code-action@v1
  with:
    context_files: |
      claude_analysis_plan.json
```

The analysis plan contains all the information needed for Claude to implement the recommended changes:
- Action items with priorities
- Files that need modification
- Suggested commit messages
- Recommended changes structure

## Security Considerations

### 1. External PR Security (pull_request_target)

**Pattern**: Use `pull_request_target` for external PRs
- Runs with base-repo write permissions
- Prevents malicious code execution from external forks
- Checks out base branch, not the fork branch

**Reference**: Custom automations documentation

### 2. Secret Management

- Never expose API keys in logs
- Use repository secrets
- Limit Claude app permissions to minimum required

### 3. CI on Claude Commits

- Configure CI to not block on Claude-generated commits
- Use labels or commit message patterns to identify automated commits

## Advanced Patterns

### Extending the Workflow

The workflow can be extended with additional jobs that use the analysis plan:
- Testing job that creates tests based on the analysis
- Documentation job that updates docs for changed features
- Security scanning job that reviews identified risks

Each job can download the analysis artifact and use it independently.

### Custom Automation Prompts

Store prompts in repository:
- `.github/claude-prompts/merge-analysis.md`
- `.github/claude-prompts/testing-specialist.md`
- Reference in workflow for maintainability

### Conditional Branching

Use workflow outputs to conditionally spawn agents:
```yaml
if: needs.merge-analysis.outputs.risk_level == 'high'
```

## Troubleshooting

### Claude Action Not Running

1. Check Claude GitHub App is installed
2. Verify `ANTHROPIC_API_KEY` secret is set
3. Check workflow permissions
4. Review workflow trigger conditions

### Structured Output Parsing Fails

1. Verify Claude output is valid JSON
2. Check JSON schema matches expected format
3. Review Claude prompt for JSON output requirements
4. Check `jq` parsing in workflow steps

### Branch Creation Fails

1. Verify `GITHUB_TOKEN` has write permissions
2. Check branch name is valid (no special characters)
3. Ensure base branch exists
4. Review git configuration in workflow

### Changes Not Being Applied

1. Verify artifacts are uploaded/downloaded correctly
2. Check that the analysis plan contains `has_changes: true`
3. Ensure context files are passed to Claude action
4. Review Claude prompt to ensure it reads the analysis plan

## Cost Optimization

### Model Selection

- Use `claude-opus-4-6` for analysis (higher quality)
- Use `claude-sonnet-4-5` for simpler tasks (lower cost)
- Configure via `claude_args: --model`

### Token Limits

- Set appropriate `--max-tokens` based on task
- Analysis: 8000 tokens
- Implementation: 8000 tokens

### Conditional Execution

- Only run expensive analysis when needed
- Use `if` conditions to skip jobs
- Cache artifacts to avoid re-analysis

## References

### Official Documentation

1. **Claude Code Action Repository**
   - https://github.com/anthropics/claude-code-action
   - Examples, usage patterns, structured outputs

2. **Claude Code GitHub Actions Docs**
   - https://code.claude.com/docs/en/github-actions
   - Setup, quickstart, Agent SDK reference

3. **Custom Automations**
   - pull_request_target pattern documentation
   - External PR security handling

### Related Patterns

- **GitHub Actions Best Practices**: Security, permissions, secrets
- **Structured Outputs**: JSON validation, context passing
- **Artifact Management**: Passing data between workflow jobs

## Example Usage

### Trigger via PR

1. Open a pull request
2. Workflow automatically triggers
3. Claude analyzes the PR
4. Report posted as comment
5. If changes needed, feature branch created automatically

### Trigger via Comment

1. Comment on PR/Issue: `@claude analyze merge`
2. Workflow triggers on comment
3. Analysis runs and reports back

### Trigger via Label

1. Add `claude-analyze` label to issue
2. Workflow triggers
3. Analysis runs on issue context

## Future Enhancements

### Potential Improvements

1. **Multi-Repository Analysis**: Analyze cross-repo dependencies
2. **Historical Context**: Include previous PRs in analysis
3. **Team Preferences**: Learn from team review patterns
4. **Integration Testing**: Run tests in analysis phase
5. **Security Scanning**: Integrate security analysis
6. **Performance Analysis**: Detect performance regressions

### Advanced Forking Patterns

1. **Parallel Agents**: Run multiple specialized agents simultaneously
2. **Agent Chains**: Chain agents (analysis → testing → documentation)
3. **Context Aggregation**: Merge multiple agent outputs
4. **Human-in-the-Loop**: Request approval before creating branches

## Conclusion

This workflow demonstrates a production-ready pattern for:
- Automated code analysis with Claude Code
- Structured output generation for automation
- Feature branch creation with recommended changes
- Secure handling of external contributions
- Integration with GitHub's PR/Issue workflow

The implementation follows best practices from the Claude Code ecosystem and GitHub Actions patterns, providing a solid foundation for AI-assisted development workflows.
