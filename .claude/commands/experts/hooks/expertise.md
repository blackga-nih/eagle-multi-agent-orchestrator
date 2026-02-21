---
type: expert-file
parent: "[[hooks/_index]]"
file-type: expertise
human_reviewed: false
source: claude-code-hooks-multi-agent-observability + claude-code-hooks-mastery
last_validated: 2026-02-17
tags: [expert-file, mental-model, hooks, observability]
---

# Hooks Expertise (Complete Mental Model)

> **Sources**: disler/claude-code-hooks-multi-agent-observability, disler/claude-code-hooks-mastery, TAC Lessons 5 + 12

---

## Part 1: The 12 Hook Events

Claude Code fires hooks at specific lifecycle points. Each hook receives JSON via stdin and can influence behavior via stdout.

### Event Reference

| Event | When It Fires | Input Fields | Can Block? |
|-------|--------------|--------------|------------|
| **SessionStart** | Session begins | source, model, agent_type | No (can inject context) |
| **SessionEnd** | Session ends | session_id | No |
| **UserPromptSubmit** | User sends prompt | prompt, session_id | Yes (modify/reject prompt) |
| **PreToolUse** | Before tool executes | tool_name, tool_input | Yes (deny tool call) |
| **PostToolUse** | After tool succeeds | tool_name, tool_result, tool_use_id | No |
| **PostToolUseFailure** | After tool fails | tool_name, error | No |
| **PermissionRequest** | Permission needed | tool_name, permission_type | No |
| **Notification** | User interaction needed | notification_type | No |
| **SubagentStart** | Subagent spawned | agent_id, agent_type | No |
| **SubagentStop** | Subagent finishes | agent_id, agent_transcript_path | No |
| **Stop** | Response complete | reason (turn_end, session_end) | No |
| **PreCompact** | Context compaction | custom_instructions | No (can backup) |

### Hook Input (JSON via stdin)

Every hook receives:
```json
{
  "session_id": "abc123",
  "session_dir": "/path/to/.claude/sessions/abc123",
  "transcript_path": "/path/to/transcript.jsonl",
  // ... event-specific fields
}
```

### Hook Output (JSON via stdout)

| Pattern | Purpose | Example |
|---------|---------|---------|
| `hookSpecificOutput.additionalContext` | Inject context at SessionStart | Status reports, git state |
| `hookSpecificOutput.permissionDecision: "deny"` | Block a tool call | Security, safety guards |
| `hookSpecificOutput.message` | Modify user prompt | Prompt validation |
| Exit code 0 | Success | Normal operation |
| Exit code non-0 | Failure | Hook failed (logged) |

---

## Part 2: The 7 Hook Patterns

### Pattern 1: Tool Blocking (PreToolUse)

Block dangerous operations before they execute.

```python
def handle(tool_name, tool_input):
    command = tool_input.get("command", "")
    if "rm -rf" in command:
        return {
            "hookSpecificOutput": {
                "permissionDecision": "deny",
                "reason": "Blocked: rm -rf is not allowed"
            }
        }
    return None  # Allow
```

**Use cases**: Block `rm -rf`, prevent `.env` access, restrict file writes to certain directories.

### Pattern 2: Context Injection (SessionStart)

Load development context at session start.

```python
def handle(session_data):
    context = []
    context.append(f"Branch: {get_git_branch()}")
    context.append(f"Uncommitted: {get_uncommitted_files()}")
    context.append(f"Recent issues: {get_github_issues()}")
    return {
        "hookSpecificOutput": {
            "additionalContext": "\n".join(context)
        }
    }
```

**Use cases**: Load git state, service health, open issues, recent errors.

### Pattern 3: Event Forwarding (Universal)

Forward all events to an observability server.

```python
def send_event(event_type, payload):
    requests.post("http://localhost:4000/events", json={
        "type": event_type,
        "timestamp": datetime.now().isoformat(),
        "session_id": payload.get("session_id"),
        **payload
    })
```

**Use cases**: Real-time dashboards, analytics, audit trails.

### Pattern 4: PostToolUse Validation

Validate outputs after tool execution (linting, type checking).

```python
# In agent definition hooks:
# PostToolUse for Write/Edit tools
def handle(tool_name, tool_result):
    if tool_name in ("Write", "Edit"):
        file_path = tool_result.get("file_path", "")
        if file_path.endswith(".py"):
            run_ruff(file_path)   # Lint check
            run_ty(file_path)     # Type check
```

**Use cases**: Auto-lint on file write, run tests after code changes, validate JSON schema.

### Pattern 5: Stop Hook Guard

Prevent infinite loops when Stop hooks trigger Claude to continue.

```python
import os

GUARD = "stop_hook_active"

if os.environ.get(GUARD):
    sys.exit(0)  # Already running, skip

os.environ[GUARD] = "1"
try:
    # Do stop hook work
    handle_stop(data)
finally:
    del os.environ[GUARD]
```

**Use cases**: TTS announcements, transcript capture, session summaries.

### Pattern 6: Dispatcher Routing

Route lifecycle hooks to domain-specific handlers.

```python
# utils/dispatcher.py
PRE_TOOL_HANDLERS = {
    "Bash": [
        ("aws ", "aws.command_watcher", "handle"),
        ("git worktree", "git.worktree_watcher", "handle"),
        ("rm ", "dev.dangerous_blocker", "handle"),
    ],
}

def dispatch_pre_tool(tool_name, tool_input):
    handlers = PRE_TOOL_HANDLERS.get(tool_name, [])
    command = tool_input.get("command", "")
    for pattern, module, func in handlers:
        if pattern in command:
            result = load_handler(module, func)(tool_name, tool_input)
            if result and result.get("block"):
                return result
    return None
```

**Use cases**: Multi-domain projects, scalable hook management.

### Pattern 7: TTS Notification

Audio announcements with priority fallback.

```python
def speak(message):
    if os.getenv("ELEVENLABS_API_KEY"):
        elevenlabs_speak(message)  # ~75ms latency
    elif os.getenv("OPENAI_API_KEY"):
        openai_speak(message)
    else:
        pyttsx3_speak(message)  # Offline fallback
```

**Use cases**: Stop announcements, permission prompts, session start greetings.

---

## Part 3: Hook Architecture

### TAC-Compliant Directory Structure

```
.claude/
├── settings.json              # Hook configuration (one entry per event)
└── hooks/
    ├── send_event.py          # Universal event sender
    ├── pre_tool_use.py        # Lifecycle hook (root level)
    ├── post_tool_use.py       # Lifecycle hook (root level)
    ├── session_start.py       # Lifecycle hook (root level)
    ├── session_end.py         # Lifecycle hook (root level)
    ├── user_prompt_submit.py  # Lifecycle hook (root level)
    ├── notification.py        # Lifecycle hook (root level)
    ├── stop.py                # Lifecycle hook (root level)
    ├── subagent_start.py      # Lifecycle hook (root level)
    ├── subagent_stop.py       # Lifecycle hook (root level)
    ├── pre_compact.py         # Lifecycle hook (root level)
    ├── permission_request.py  # Lifecycle hook (root level)
    ├── post_tool_use_failure.py
    ├── utils/                 # Only allowed subfolder
    │   ├── constants.py       # Session/log management
    │   ├── dispatcher.py      # Pattern-based routing
    │   ├── summarizer.py      # AI event summarization
    │   ├── model_extractor.py # Model info from transcripts
    │   ├── llm/               # LLM integrations
    │   │   ├── anth.py        # Anthropic API
    │   │   └── oai.py         # OpenAI API
    │   └── tts/               # Text-to-speech
    │       ├── elevenlabs_tts.py
    │       ├── openai_tts.py
    │       └── pyttsx3_tts.py
    └── validators/            # Stop hook validators
        ├── validate_new_file.py
        └── validate_file_contains.py
```

**Core Rule**: Lifecycle hooks stay flat at root. Only `utils/` and `validators/` subfolders allowed.

### settings.json Configuration

```json
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "",
      "hooks": [{"type": "command", "command": "uv run .claude/hooks/pre_tool_use.py"}]
    }],
    "PostToolUse": [{
      "matcher": "",
      "hooks": [{"type": "command", "command": "uv run .claude/hooks/post_tool_use.py"}]
    }],
    "SessionStart": [{
      "hooks": [{"type": "command", "command": "uv run .claude/hooks/session_start.py --load-context"}]
    }],
    "Stop": [{
      "matcher": "turn_end",
      "hooks": [{"type": "command", "command": "uv run .claude/hooks/stop.py --on-turn"}]
    }, {
      "matcher": "",
      "hooks": [{"type": "command", "command": "uv run .claude/hooks/stop.py"}]
    }]
  }
}
```

### Matcher System

| Matcher | Scope | Example |
|---------|-------|---------|
| `""` (empty) | All events of this type | Catch-all handler |
| `"Bash"` | Only Bash tool calls | PreToolUse for shell commands |
| `"Write"` | Only Write tool calls | PostToolUse for file validation |
| `"turn_end"` | Only turn completions | Stop hook for turn memory |

### Global vs Project Hooks

| Level | Location | Scope |
|-------|----------|-------|
| **Global** | `~/.claude/settings.json` | All projects (TTS, personal preferences) |
| **Project** | `.claude/settings.json` | This project only (validation, security) |

Both levels run. Project hooks do NOT override global hooks — they stack.

---

## Part 4: Agent Integration

### Agent-Specific Hooks

Agents can define their own PostToolUse hooks for validation:

```markdown
---
name: builder
model: opus
color: cyan
hooks:
  PostToolUse:
    - matcher: "Write"
      hooks: [{ type: "command", command: "ruff check {file}" }]
    - matcher: "Edit"
      hooks: [{ type: "command", command: "ty check {file}" }]
---
```

### Builder/Validator Pattern

| Agent | Tools | Purpose |
|-------|-------|---------|
| **Builder** | Write, Edit | Execute tasks, PostToolUse validates |
| **Validator** | Read, Grep, Glob only | Read-only verification of builder output |

### Subagent Lifecycle Hooks

Track agent team coordination:

```
SubagentStart → agent spawned (agent_id, agent_type)
SubagentStop  → agent finished (agent_id, agent_transcript_path)
```

Use these to:
- Track which agents are active
- Capture agent transcripts for analysis
- Measure agent execution time
- Route agent completions to dashboards

---

## Part 5: Observability Pipeline

### Event Flow

```
Hook Event → send_event.py → HTTP POST → Server → Database → Dashboard
                  │
                  ├── --summarize  → AI summary of event
                  ├── --add-chat   → Include conversation transcript
                  └── --notify     → TTS announcement
```

### Server Stack (Reference Implementation)

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Server | Bun (TypeScript) | Event ingestion on port 4000 |
| Database | SQLite | Persistent event storage |
| Dashboard | Vue.js | Real-time event visualization |
| Transport | HTTP POST | Hook → Server communication |

### Key Metrics to Track

| Metric | Source Hook | Purpose |
|--------|-----------|---------|
| Tool usage | PostToolUse | Which tools are used most |
| Failures | PostToolUseFailure | Error rate by tool |
| Blocked calls | PreToolUse | Security enforcement |
| Session duration | SessionStart/End | Time per session |
| Agent count | SubagentStart/Stop | Parallelism level |
| Context usage | PreCompact | Context window pressure |
| Turn count | Stop (turn_end) | Turns per session |

---

## Part 6: Implementation Recipes

### Recipe 1: Minimum Viable Hooks (10 minutes)

Start with just two hooks for immediate value:

```json
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "Bash",
      "hooks": [{"type": "command", "command": "uv run .claude/hooks/pre_tool_use.py"}]
    }],
    "SessionStart": [{
      "hooks": [{"type": "command", "command": "uv run .claude/hooks/session_start.py --load-context"}]
    }]
  }
}
```

### Recipe 2: Full Observability (30 minutes)

All 12 events piped through universal sender:

```json
{
  "hooks": {
    "PreToolUse": [{"hooks": [{"type": "command", "command": "uv run .claude/hooks/send_event.py PreToolUse"}]}],
    "PostToolUse": [{"hooks": [{"type": "command", "command": "uv run .claude/hooks/send_event.py PostToolUse"}]}],
    "SessionStart": [{"hooks": [{"type": "command", "command": "uv run .claude/hooks/send_event.py SessionStart"}]}],
    "SessionEnd": [{"hooks": [{"type": "command", "command": "uv run .claude/hooks/send_event.py SessionEnd"}]}],
    "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "uv run .claude/hooks/send_event.py UserPromptSubmit"}]}],
    "Notification": [{"hooks": [{"type": "command", "command": "uv run .claude/hooks/send_event.py Notification"}]}],
    "Stop": [{"hooks": [{"type": "command", "command": "uv run .claude/hooks/send_event.py Stop"}]}],
    "SubagentStart": [{"hooks": [{"type": "command", "command": "uv run .claude/hooks/send_event.py SubagentStart"}]}],
    "SubagentStop": [{"hooks": [{"type": "command", "command": "uv run .claude/hooks/send_event.py SubagentStop"}]}],
    "PreCompact": [{"hooks": [{"type": "command", "command": "uv run .claude/hooks/send_event.py PreCompact"}]}],
    "PermissionRequest": [{"hooks": [{"type": "command", "command": "uv run .claude/hooks/send_event.py PermissionRequest"}]}],
    "PostToolUseFailure": [{"hooks": [{"type": "command", "command": "uv run .claude/hooks/send_event.py PostToolUseFailure"}]}]
  }
}
```

### Recipe 3: Security-First Hooks

Focus on blocking dangerous operations:

```python
# pre_tool_use.py - Security guards
BLOCKED_PATTERNS = [
    ("rm -rf /", "Blocked: recursive delete at root"),
    (".env", "Blocked: environment file access"),
    ("DROP TABLE", "Blocked: destructive SQL"),
    ("--force", "Blocked: force flag requires approval"),
]

def handle(tool_name, tool_input):
    command = tool_input.get("command", "")
    for pattern, reason in BLOCKED_PATTERNS:
        if pattern in command:
            return deny(reason)
    return None
```

### Recipe 4: Turn-by-Turn Memory

Capture learnings at each turn boundary:

```python
# stop.py with turn_end matcher
def handle_turn(data):
    transcript = read_transcript(data["transcript_path"])
    last_turn = extract_last_turn(transcript)

    category = classify_turn(last_turn)  # No API call, keyword-based

    save_turn_log(
        category=category,
        summary=last_turn[:500],
        files_modified=extract_files(last_turn),
        timestamp=datetime.now()
    )
```

---

## Part 7: Best Practices

### Performance Rules

| Rule | Why |
|------|-----|
| Hooks must complete in < 60 seconds | Timeout kills the hook |
| No API calls in classification hooks | Keep latency low |
| Use keyword matching over LLM calls | Fast, deterministic |
| Cache model names and session data | Avoid re-reading transcripts |
| Use `uv run` for Python hooks | Fast dependency resolution |

### Safety Rules

| Rule | Why |
|------|-----|
| `stop_hook_active` guard on Stop hooks | Prevent infinite loops |
| Validate all file paths | Prevent directory traversal |
| Never block Claude's core operation | Hooks fail silently on error |
| Test hooks in isolation before deploying | Avoid breaking sessions |
| Use `try/except` with `pass` for TTS | Audio failures are non-critical |

### Design Rules

| Rule | Why |
|------|-----|
| Flat structure at root | TAC compliance, simple routing |
| One entry per event type | Minimal settings.json |
| Universal sender pattern | Single HTTP endpoint |
| Domain handlers in `utils/` | Scalable organization |
| Matchers for filtering | Targeted hook execution |

---

## Part 8: Hook Execution Environment

| Property | Value |
|----------|-------|
| **Runtime** | Subprocess (shell command) |
| **Timeout** | 60 seconds per hook |
| **Parallelism** | All matching hooks run simultaneously |
| **Working Directory** | Project root |
| **Input** | JSON via stdin |
| **Output** | stdout for hookSpecificOutput, stderr for logging |
| **Exit Code** | 0 = success, non-0 = failure (logged, not fatal) |

### Environment Variables Available

| Variable | Value |
|----------|-------|
| `CLAUDE_SESSION_ID` | Current session ID |
| `CLAUDE_MODEL` | Current model name |
| `USER` | OS username |
| `HOME` | Home directory |
| Project `.env` | If dotenv loaded |

---

## Part 9: Reference Implementations

| Repository | Hook Count | Focus |
|------------|-----------|-------|
| `claude-code-hooks-multi-agent-observability` | 12 (all events) | Full observability pipeline |
| `claude-code-hooks-mastery` | 6 | Core patterns and meta-agents |
| `claude-code-damage-control` | 2 | PreToolUse security blocking |
| `agentic-finance-review` | 3 | PostToolUse validation |

### Key Files to Study

| File | Pattern | Learning |
|------|---------|----------|
| `send_event.py` | Universal sender | One file for all events |
| `pre_tool_use.py` | Tool blocking | `permissionDecision: "deny"` |
| `session_start.py` | Context injection | `additionalContext` pattern |
| `stop.py` | Stop guard | `stop_hook_active` env var |
| `notification.py` | TTS chain | ElevenLabs > OpenAI > pyttsx3 |
| `user_prompt_submit.py` | Prompt validation | Agent naming via LLM |
| `pre_compact.py` | Transcript backup | Save before context loss |
| `utils/dispatcher.py` | Domain routing | Pattern-based handler dispatch |
