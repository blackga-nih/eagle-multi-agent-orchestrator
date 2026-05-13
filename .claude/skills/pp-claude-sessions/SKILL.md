---
name: pp-claude-sessions
description: "Printing-Press-shaped CLI for Claude Code session JSONLs. Read-only queries over a scrubbed handoff bundle or any ~/.claude/projects/<encoded>/ dir. Subcommands: list, show, search, tools, stats, which, doctor, feedback. Use when someone asks 'search the session history', 'what tools were used', 'show session X', 'when did we work on Y', or wants a CLI over Claude Code transcripts."
author: "EAGLE team"
license: "Apache-2.0"
argument-hint: "<command> [args] | doctor | which '<question>'"
allowed-tools: "Read Bash"
metadata:
  openclaw:
    requires:
      runtime: python>=3.10
    install:
      - kind: script
        runtime: python
        entry: query.py
---

# pp-claude-sessions — Printing Press CLI for Claude Code session history

Read-only query interface over a directory of Claude Code session JSONLs.
Default source is `./session-history/jsonl/` (the layout produced by the
[`claude-handoff`](../claude-handoff/SKILL.md) skill), with `--src` override
for any `~/.claude/projects/<encoded>/` directory.

Stdlib-only. No Go, no `npm install`, no binary to fetch — Python 3.10+ is
the only prerequisite. This keeps the CLI portable to whatever machine the
handoff bundle ends up on.

## Prerequisites: verify the script is on disk

This skill drives a single Python script: `query.py` co-located with this
`SKILL.md`. **Verify it's runnable before invoking any command from this
skill.** If missing, the skill is not installed correctly — install the
parent `claude-handoff` skill first.

```bash
python "$(dirname "$(realpath SKILL.md)")"/query.py --version
```

Run `query.py doctor --src <path>` to verify the data source is readable.

## When Not to Use This CLI

Do not activate this CLI for requests that require creating, updating,
deleting, publishing, commenting, replaying, resuming, or otherwise
mutating session state. This is read-only inspection over JSONL files
on disk. For session replay use `claude --resume` instead.

## Command Reference

**list** — Enumerate sessions

- `query.py list` — Returns one entry per `*.jsonl` with msg counts, timestamps, git branch, and the first user message preview (120 chars).
- Flags: `--limit N`

**show** — Pretty-print a single session

- `query.py show <session-id>` — Full session with user + assistant text (prose only by default; tool_use shown as `[tool_use: ToolName]`). Accepts unique-prefix matching.
- Flags: `--all` (include non user/assistant entries), `--limit N`

**search** — Substring/regex across all sessions

- `query.py search "<pattern>"` — Case-insensitive regex over user+assistant text. Returns session_id + role + timestamp + uuid + match + 80 chars of surrounding context.
- Flags: `--case`, `--context N`, `--limit N`, `--include-tools` (forensic mode — also matches inside Bash commands, Edit args, and other tool_use inputs)

**tools** — Count tool invocations

- `query.py tools` — Aggregate `{tool_name: count}` across all sessions plus totals.
- Flags: `--by-session` (also breaks down per session)

**stats** — Overall summary

- `query.py stats` — Total sessions, total messages, user/assistant split, tool_use total, first/last timestamp, top git branches.

### Finding the right command

When you know what you want to do but not which command does it, ask the CLI directly:

```bash
query.py which "<capability in your own words>"
```

`which` resolves a natural-language capability query to the best matching command from this CLI's curated feature index. Exit code `0` means at least one match; exit code `2` means no confident match — fall back to `--help` or use a narrower query.

## Auth Setup

No authentication required.

Run `query.py doctor` to verify setup: Python version, `--src` dir present, JSONL files parseable.

## Agent Mode

Add `--agent` to any command. Expands to: `--json --compact --no-input --no-color --yes`.

- **Pipeable** — JSON on stdout, errors on stderr
- **Filterable** — `--select` keeps a subset of fields. Dotted paths descend into nested structures; arrays traverse element-wise. Critical for keeping context small on verbose results:

  ```bash
  query.py --select session_id,messages,first_user_message list --limit 5
  ```
- **Previewable** — `--dry-run` shows what would run without doing it
- **Offline-friendly** — entirely local; never makes network calls (except `--deliver webhook:`)
- **Non-interactive** — never prompts, every input is a flag
- **Read-only** — does not write to the `--src` directory; only writes to `--deliver file:<path>` or to the feedback log

### Response envelope

Every command's output is wrapped in a provenance envelope:

```json
{
  "meta": {"source": "local", "scanned_at": "<iso>", "reason": "<context>"},
  "results": <data>
}
```

Parse `.results` for data and `.meta.source` (always `"local"` for this CLI — there's no remote API). The `meta.reason` field carries a free-text hint such as `"truncated at limit 50"` or `"0 hits for /pattern/"`.

## Agent Feedback

When you (or the agent) notice something off about this CLI, record it:

```
query.py feedback add "the --include-tools flag doesn't index thinking blocks"
query.py feedback add --stdin < notes.txt
query.py feedback list --limit 10
```

Entries are stored locally at `~/.pp-claude-sessions/feedback.jsonl`. They are never POSTed anywhere — this CLI has no telemetry. Write what *surprised* you, not a bug report. Short, specific, one line.

## Output Delivery

Every command accepts `--deliver <sink>`. The output goes to the named sink instead of stdout, so agents can route command results without hand-piping. Three sinks are supported:

| Sink | Effect |
|------|--------|
| `stdout` | Default; write to stdout only |
| `file:<path>` | Atomically write output to `<path>` (tmp + rename) |
| `webhook:<url>` | POST the output body to the URL (`application/json` or `application/x-ndjson` when `--compact`) |

Unknown schemes are refused with a structured error naming the supported set. Webhook failures return non-zero and log the URL + HTTP status on stderr.

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 2 | Usage error (wrong arguments / no confident `which` match) |
| 3 | Resource not found (session-id doesn't match / no JSONLs in src) |
| 5 | Read error (webhook delivery failed) |
| 10 | Config error (`--src` not found, no default dir) |

## Argument Parsing

Parse `$ARGUMENTS`:

1. **Empty, `help`, or `--help`** → show `query.py --help` output
2. **Anything else** → Direct Use (execute as CLI command with `--agent`)

## Direct Use

1. Check if installed: `python <skill-dir>/query.py --version`
   If not found, the parent `claude-handoff` skill isn't installed — install it first.
2. Match the user query to the best command from the Command Reference above.
3. Execute with the `--agent` flag:
   ```bash
   python <skill-dir>/query.py <command> [args] --agent --src <jsonl-dir>
   ```
4. If ambiguous, ask the CLI: `query.py which "<their query>"`.
5. For verbose results, narrow with `--select` and `--limit`.

## Common Recipes

```bash
# 1) "What tools did we use the most in the handoff bundle?"
query.py --src ./session-history/jsonl --agent tools --select by_tool

# 2) "Show me sessions from the feat/* branches"
query.py --src ./session-history/jsonl --agent --select session_id,git_branch,messages list \
  | jq '.results[] | select(.git_branch | startswith("feat/"))'

# 3) "When did we first work on the SSE watchdog?"
query.py --src ./session-history/jsonl --agent search "SSE watchdog" --limit 5 --context 120

# 4) "Forensic: did any session capture a sk-ant key in a Bash command?"
query.py --src ./session-history/jsonl --agent search "sk-ant-" --include-tools --limit 20

# 5) Pull the first user message of every session into a file
query.py --src ./session-history/jsonl --select session_id,first_user_message \
  --deliver file:session-index.json list
```
