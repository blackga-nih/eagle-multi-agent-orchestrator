---
type: expert-file
file-type: index
domain: frontend
tags: [expert, frontend, nextjs, tailwind, chat, dashboard, test-results, html]
---

# Frontend Expert

> Next.js admin dashboard, EAGLE chat interface, test results viewers, and legacy HTML dashboard specialist.

## Domain Scope

This expert covers:
- **Next.js App** - `client/` (App Router, pages, components, API routes, auth)
- **Chat Interface** - `/chat-advanced` complex chat with forms, agent logs, sidebar panels
- **Minimalist Chat** - `/` simple chat with EAGLE reference design
- **Admin Dashboard** - `/admin/tests` (test results), `/admin/eval` (eval viewer with use cases)
- **Test Result Mappings** - TEST_NAMES, TEST_DEFS, SKILL_TEST_MAP, readiness panel, category system
- **Legacy HTML Dashboard** - `test_results_dashboard.html` (standalone test results viewer)
- **Auth & Context** - Cognito user pool, auth-context.tsx, session-context.tsx
- **Styling** - Tailwind CSS with NCI color palette, globals.css animations

## Available Commands

| Command | Purpose |
|---------|---------|
| `/experts:frontend:question` | Answer frontend questions without coding |
| `/experts:frontend:plan` | Plan frontend changes or new features |
| `/experts:frontend:self-improve` | Update expertise after frontend work |
| `/experts:frontend:plan_build_improve` | Full ACT-LEARN-REUSE workflow |
| `/experts:frontend:maintenance` | Check builds, validate mappings, verify consistency |

## Key Files

| File | Purpose |
|------|---------|
| `expertise.md` | Complete mental model for frontend domain |
| `question.md` | Query command for read-only questions |
| `plan.md` | Planning command for frontend changes |
| `self-improve.md` | Expertise update command |
| `plan_build_improve.md` | Full workflow command |
| `maintenance.md` | Build check and mapping validation |

## Architecture

```
client/
  |-- app/
  |   |-- page.tsx                  # / (minimalist chat)
  |   |-- chat-advanced/page.tsx    # /chat-advanced (complex chat)
  |   |-- login/page.tsx            # /login (Cognito auth)
  |   |-- admin/
  |   |   |-- page.tsx              # /admin (dashboard home)
  |   |   |-- tests/page.tsx        # /admin/tests (test results viewer)
  |   |   |-- eval/page.tsx         # /admin/eval (eval viewer + use cases)
  |   |   |-- agents/               # Agent management
  |   |   |-- costs/                # Cost tracking
  |   |   |-- analytics/            # Analytics
  |   |-- api/
  |       |-- trace-logs/route.ts   # Local trace_logs.json API
  |       |-- cloudwatch/route.ts   # CloudWatch query API
  |       |-- prompts/route.ts      # Skill prompt file API
  |       |-- invoke/route.ts       # Agent invocation
  |
  |-- components/
  |   |-- chat/                     # Complex chat components
  |   |-- chat-simple/              # Minimalist chat components
  |   |-- layout/                   # TopNav, SidebarNav
  |   |-- auth/                     # AuthGuard
  |   |-- forms/                    # Intake forms
  |   |-- checklist/                # Document checklist
  |
  |-- contexts/
  |   |-- auth-context.tsx          # Cognito auth provider
  |   |-- session-context.tsx       # Session persistence
  |
  |-- tailwind.config.ts            # NCI color palette
  |-- app/globals.css               # Animations, markdown styles

test_results_dashboard.html         # Standalone HTML dashboard
```

## ACT-LEARN-REUSE Pattern

```
ACT    ->  Modify components, update mappings, add pages
LEARN  ->  Update expertise.md with patterns and issues
REUSE  ->  Apply patterns to future frontend development
```
