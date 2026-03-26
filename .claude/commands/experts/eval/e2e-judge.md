---
description: "Run the e2e-judge screenshot + vision pipeline via the /e2e-judge skill"
---

# E2E Vision Judge — Eval Expert Command

This command invokes the `/e2e-judge` skill to run screenshot-based E2E testing with LLM-as-judge evaluation against the deployed EAGLE app.

## What it does

1. Invokes the `e2e-judge` skill (`.claude/skills/e2e-judge/SKILL.md`)
2. The skill runs the Python orchestrator on the EC2 devbox via SSM
3. Playwright captures screenshots of each UI journey step
4. Claude Sonnet (Bedrock) evaluates each screenshot for visual quality
5. Results are uploaded to S3 and displayed in a gallery

## Usage

Run `/experts:eval:e2e-judge` to invoke this command, which will call the `/e2e-judge` skill.

If you want to run specific journeys, tell the user to specify them:
- `login,home,chat` — core pages
- `workflows` — acquisition packages + checklist modal
- `admin` — admin dashboard sub-pages
- `all` — everything including responsive and acquisition_package lifecycle

## Instructions

Invoke the `/e2e-judge` skill. Pass through any user arguments (journey selection, purge-cache, etc.).

Read `.claude/skills/e2e-judge/SKILL.md` for the full skill instructions, then follow them.

Key context from eval expertise (Part 13):
- **Devbox**: `i-0390c06d166d18926`, Python at `/usr/bin/python3.12`
- **Code**: `/home/ec2-user/e2e-judge/server/tests/`
- **Judge model**: `us.anthropic.claude-sonnet-4-5-20250929-v1:0`
- **Auth selectors**: `#email`, `#password`, `button[type='submit']`
- **Page loads**: `wait_until="domcontentloaded"` (not networkidle)
- **S3 bucket**: `eagle-eval-artifacts-695681773636-dev`
