---
name: claude-handoff
description: "Bundle a sanitized Claude Code environment for handoff to a co-worker — config + session history + readable HTML transcripts + auto-generated setup guide. Use when user says 'hand off my environment', 'transfer my Claude Code setup', 'onboard a co-worker', 'export my Claude environment', or 'package my project for someone else'."
allowed-tools:
  - Read
  - Write
  - Bash
  - Glob
  - AskUserQuestion
---

<objective>
Produce a portable, sanitized handoff bundle of the user's Claude Code environment for the **current project** so a co-worker can clone the repo and operate with an identical agent setup (skills, agents, commands, hooks, plugins) plus the full session history of the project.

Output: a single timestamped directory at `./handoff-claude-{YYYYMMDD-HHMMSS}/` containing:
- `repo-info.md` — clone instructions + commit SHA
- `claude-user-config/` — sanitized `~/.claude/` slice (no creds, no personal caches). Includes the `pp-claude-sessions` skill (Python query CLI) so the co-worker has a ready-to-use reader for the bundled JSONLs.
- `session-history/jsonl/` — scrubbed session JSONLs for `claude --resume` AND for the `pp-claude-sessions` query CLI
- `session-history/readable/` — HTML transcripts (fallback if resume fails)
- `session-history/memory/` — project memory (audited)
- `HANDOFF.md` — step-by-step setup for the co-worker, including a "Browsing session history" section that points at the query CLI
</objective>

<inputs>
- Current working directory (used to derive the encoded session path)
- `$HOME/.claude/` (user-level Claude Code config)
- Optional flags from user prompt:
  - `--no-sessions` → skip session JSONL + HTML export (config only)
  - `--no-html` → skip readable HTML transcript generation
  - `--out <path>` → override output directory
  - `--name <coworker>` → personalize HANDOFF.md
</inputs>

<exclusions>
**NEVER copy these — personal/secret/machine-specific:**
- `~/.claude/.credentials.json` (auth tokens)
- `~/.claude/settings.local.json` (personal allow rules)
- `~/.claude/history.jsonl` (cross-project prompt history)
- `~/.claude/cache/`, `paste-cache/`, `file-history/`, `shell-snapshots/`
- `~/.claude/telemetry/`, `debug/`, `stats-cache.json`, `mcp-needs-auth-cache.json`
- `~/.claude/sessions/`, `session-env/`, `tasks/`, `todos/`, `plans/`, `ide/`
- `~/.claude/backups/`
- The user's own `MEMORY.md` entries that look personal — audit before copying

**NEVER copy from project:**
- `.claude/settings.local.json` (Claude auto-gitignores it)
- `.env*`, `.aws/`, `node_modules/`, `.next/`, `__pycache__/`, build outputs
</exclusions>

<process>

### Step 1 — Confirm scope
Show a dry-run summary BEFORE doing any copying:
- Project root (cwd)
- Encoded session dir name and total size of `~/.claude/projects/<encoded>/`
- Number of `.jsonl` session files
- Detected `~/.claude/` subdirs that will be copied vs skipped
- Detected plugins from `~/.claude/plugins/installed_plugins.json`
- Output directory path

Ask user to confirm via AskUserQuestion (Proceed / Adjust scope / Cancel).

### Step 2 — Derive encoded session path
The CWD is encoded by replacing every non-alphanumeric character with `-`. Example:
- `C:\Users\<name>\code\some_repo` → `C--Users--name--code-some-repo`

Verify the directory exists at `~/.claude/projects/<encoded>/`. If not, warn and ask whether to continue config-only.

### Step 3 — Create output skeleton
```
handoff-claude-{TS}/
├── repo-info.md
├── claude-user-config/
│   ├── settings.json              ← sanitized (paths rewritten to placeholders)
│   ├── agents/
│   ├── skills/
│   ├── commands/
│   ├── hooks/
│   ├── get-shit-done/             ← if exists
│   ├── gsd-file-manifest.json     ← if exists
│   └── plugins/
│       ├── installed_plugins.json
│       ├── known_marketplaces.json
│       └── marketplaces/
├── session-history/
│   ├── jsonl/                     ← *.jsonl files
│   ├── memory/                    ← audited memory
│   └── readable/                  ← HTML (if --no-html not set)
└── HANDOFF.md
```

### Step 4 — Sanitize `settings.json`
Read `~/.claude/settings.json`. Replace every absolute path containing the user's home (e.g. `C:/Users/<name>/...` and `C:\Users\<name>\...`) with the placeholder `{{CLAUDE_HOME}}`. Write to `claude-user-config/settings.json`. Document the placeholder in HANDOFF.md so the co-worker does a single search/replace.

### Step 5 — Copy user-level config (allowlist only)
Use `cp -r` with the explicit list. Skip anything in `<exclusions>`.

### Step 6 — Copy + scrub session JSONLs (unless --no-sessions)

**Step 6a — Run the credential scrubber (MANDATORY when sessions are included).**

Raw JSONLs frequently contain Bash output that captured AWS STS credentials,
GitHub PATs, secret access keys, or other tokens. They MUST be scrubbed before
they leave the originating dev's machine. Use the co-located scrubber:

```bash
python {SKILL_DIR}/scrub-jsonl.py \
  --src ~/.claude/projects/<encoded>/ \
  --dst <bundle>/session-history/jsonl/ \
  --username <originator-username> \
  --email <originator-email-if-known> \
  --verify
```

The `--verify` flag re-scans output and exits non-zero if any sensitive pattern
remains. If verify fails, STOP — do not proceed to bundling. Investigate the
residual matches, extend the scrubber's rules, and re-run.

The scrubber redacts (non-exhaustive): AWS access key IDs (ASIA/AKIA + 16),
`aws_secret_access_key=<value>`, `aws_session_token=<value>`, real
`sk-ant-<60+chars>` Anthropic keys, GitHub PATs (`ghp_`/`gho_`/`ghu_`+),
Slack tokens (`xox[abprs]-`), JWT-shaped bearer tokens, and any
`api_key|secret|token|password=<high-entropy>` assignment.

It does NOT redact AWS account numbers (those are not secret — they appear in
every ARN) or `sk-ant-...` literal placeholders in docs.

**Step 6b — Copy and audit memory.**

Copy the `memory/` subfolder into `session-history/memory/`. Read each `.md`
and flag any line that looks personal (names, non-project emails, personal
preferences unrelated to work). Show the user the flagged lines and ask
whether to redact before bundling.

### Step 7 — Generate readable HTML transcripts (unless --no-html)
Use `claude-code-log` (Python CLI):
```bash
pip install --quiet claude-code-log
claude-code-log session-history/jsonl/ --output session-history/readable/
```
If `claude-code-log` install fails, skip with a warning and document the manual fallback in HANDOFF.md (link to https://github.com/daaain/claude-code-log).

### Step 8 — Write `repo-info.md`
Capture for the co-worker:
- Remote URL: `git config --get remote.origin.url`
- Current branch: `git rev-parse --abbrev-ref HEAD`
- Current commit: `git rev-parse HEAD`
- Working tree status: `git status --short` (note any uncommitted work — co-worker should know they're getting committed state only)

### Step 9 — Generate `HANDOFF.md`
Use this template (substitute values from earlier steps):

```markdown
# Claude Code Environment Handoff — {project-name}

You're picking up an identical Claude Code agent environment. This bundle gives
you the same skills, agents, slash commands, hooks, plugins, and session
history as the original developer.

## Prerequisites
- Claude Code installed and signed in with **your own** Anthropic credentials
- Git, Node.js, Python (project-specific stack — see repo CLAUDE.md)

## Setup (5 steps)

### 1. Clone the repo
```bash
git clone {remote-url} {desired-path}
cd {desired-path}
git checkout {commit-sha}   # optional: match the exact handoff state
```

Record your absolute clone path — you need it for step 3.

### 2. Install user-level Claude config
Copy `claude-user-config/*` into your `~/.claude/` directory.

**Search/replace `{{CLAUDE_HOME}}` → your actual `~/.claude/` absolute path** in
`~/.claude/settings.json`. Examples:
- macOS/Linux: `/Users/yourname/.claude` or `/home/yourname/.claude`
- Windows: `C:/Users/yourname/.claude`

Verify hooks reference paths that exist on your machine.

### 3. Install session history (optional but recommended)
Compute your **encoded session directory name**:
- Take your absolute clone path from step 1
- Replace every non-alphanumeric character with `-`
- Example: `C:\Users\jane\code\sm_eagle` → `C--Users-jane-code-sm-eagle`

Create `~/.claude/projects/<your-encoded-name>/` and copy
`session-history/jsonl/*.jsonl` into it. Also copy `session-history/memory/`
in there.

Then run from inside the cloned repo:
```bash
claude --resume
```

### 4. Browsable transcripts (fallback)
If `--resume` doesn't surface the sessions (Claude Code post-v2.1.9 has known
issues with cross-machine path encoding), open
`session-history/readable/index.html` instead. Skim relevant past sessions for
context and start a fresh `claude` session — the project's `CLAUDE.md` and
`.claude/` directory already give Claude full project awareness.

### 5. Plugins
On first launch Claude may prompt to trust the marketplaces in
`~/.claude/plugins/known_marketplaces.json`. Approve to enable the same plugin
set: {plugin-list}.

## What's NOT in this bundle (you provide your own)
- Anthropic credentials → you sign in fresh
- AWS / cloud creds → you configure your own profile
- `.env` files → ask for these via secure channel
- Personal allow rules (`settings.local.json`) → grow your own as you work

## Quick verification
- `claude` should start with the project's CLAUDE.md auto-loaded
- `/help` should list all the project's slash commands (incl. `/experts/*`, `/gsd-*`)
- `/agents` should list all the subagents (aws-expert-agent, gsd-planner, etc.)
- Run a small task to confirm hooks fire (e.g. a simple Edit) — no errors

## Need to debug something?
- Settings: `~/.claude/settings.json` (user) vs `.claude/settings.json` (project)
- Hook scripts: `~/.claude/hooks/`
- Session logs: `~/.claude/projects/<your-encoded-name>/`
- Project memory loaded automatically: `CLAUDE.md` at repo root
```

### Step 10 — Print summary
After bundling, print:
- Bundle path
- Total size
- File counts per subdir
- Suggested next step: `zip -r handoff-claude-{TS}.zip handoff-claude-{TS}/` for transfer

</process>

<safety>
- **Never** include `.credentials.json` even if the user asks. Refuse and explain why (it's their auth token).
- **Never** copy `.env*` files from the project.
- **Never** ship raw JSONLs without running `scrub-jsonl.py --verify` first (Step 6a). JSONLs routinely contain logged Bash output with AWS STS keys, GitHub PATs, and other tokens.
- Always show the dry-run summary BEFORE copying — let the user cancel if scope looks wrong.
- Memory audit step (Step 6b) is non-optional when sessions are included — protects against leaking personal notes.
- Bundle output must be inside the current project (or `--out` override) — never write to `~/.claude/` itself.
</safety>

<edge_cases>
- **No git repo**: skip `repo-info.md` git fields, capture cwd only, warn user.
- **Encoded session dir doesn't exist**: project has no Claude Code history yet — proceed config-only.
- **User on macOS/Linux**: paths in settings.json may use `/Users/<name>` or `/home/<name>` — sanitize accordingly.
- **claude-code-log unavailable**: fall back to noting the JSONLs and linking the tool in HANDOFF.md.
- **Memory dir contains obvious PII**: pause and redact, don't auto-include.
- **Scrubber `--verify` fails**: STOP. Inspect residual matches, extend the rule set in `scrub-jsonl.py`, re-run. Never ship JSONLs that fail verify.
- **Bundle size > 1GB**: warn user, suggest `--no-sessions` or just `--no-html`.
</edge_cases>

<output_contract>
On success, return to the user:
1. The bundle directory absolute path
2. Total size
3. File counts (jsonl count, html count, agents count, skills count)
4. Any warnings (skipped files, redacted memory entries, missing tools)
5. The exact command to zip and transfer the bundle
</output_contract>
