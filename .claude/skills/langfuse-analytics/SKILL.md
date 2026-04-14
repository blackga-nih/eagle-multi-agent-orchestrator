---
name: langfuse-analytics
description: >
  Generate an analytical report from Langfuse traces — breakdown of skills,
  tools, documents created, and documents/sources fetched, grouped by environment
  (local / qa / prod). Reads today's traces (or any window) from Langfuse Cloud
  via REST API, aggregates TOOL/AGENT/GENERATION observations, and prints a
  human-readable summary. Use when someone says "langfuse analytics",
  "trace breakdown", "skills and tools used", "documents generated today",
  "langfuse report", or asks for an analytical rollup of Langfuse activity.
model: sonnet
---

# Langfuse Analytics — Activity Rollup

Pull traces + observations from Langfuse Cloud for a given window and produce a
breakdown of:

1. **Environments** hit (`eagle.environment` attribute — `local` / `qa` / `prod`)
2. **Tools invoked** (TOOL observations — `research`, `web_search`, `create_document`, etc.)
3. **Skills / specialist subagents** dispatched (AGENT observations + `research` inputs)
4. **Documents generated** (`create_document` calls — grouped by `document_type`)
5. **Documents / sources fetched** (`web_search`, `research`, `search_far`, `get_latest_document`)
6. **Top queries / keywords** submitted to research and web_search
7. **Per-user aggregates** — traces, sessions, tool calls, generations, tokens, cost (USD), docs, errors, top tool
8. **CloudWatch error scan** (optional, `--cloudwatch`) — reads the same log groups as `/check-cloudwatch-logs` and joins the error table into both markdown and HTML outputs

## Arguments

- `--window=1h|4h|24h|today|7d` — time window (default: `today`)
- `--env=local|qa|prod|all` — filter by environment (default: `all`)
- `--out=PATH` — write the markdown report to a file
- `--html=PATH` — write a self-contained HTML dashboard (KPI cards + per-user table + CloudWatch section)
- `--json=PATH` — also write raw aggregates as JSON
- `--cloudwatch` — also scan CloudWatch log groups for the same window (requires `aws sso login --profile eagle`)
- `--profile=eagle` / `--region=us-east-1` — override AWS SSO profile and region for the CloudWatch scan

Parse `$ARGUMENTS`:
- `/langfuse-analytics` → window=today, env=all
- `/langfuse-analytics --window=4h --env=qa` → last 4h, qa only
- `/langfuse-analytics --window=7d --out=docs/development/langfuse-week.md`

## Prerequisites

`server/.env` must define:
- `LANGFUSE_PUBLIC_KEY`
- `LANGFUSE_SECRET_KEY`
- `LANGFUSE_HOST` (optional, defaults to `https://us.cloud.langfuse.com`)
- `LANGFUSE_PROJECT_ID` (for trace URLs)

## How It Works

The script calls two Langfuse REST endpoints:

1. `GET /api/public/traces?fromTimestamp=…` — paginated, pulls trace shells
2. `GET /api/public/observations?fromStartTime=…` — paginated, pulls all spans/tools/generations

Each observation's environment is read from
`metadata.attributes["eagle.environment"]` (Strands SDK auto-instrumentation).
Tool inputs are parsed from the `input` array (list of `{role: "tool", content: JSON}`).

## Invocation

Run the bundled script:

```bash
python .claude/skills/langfuse-analytics/scripts/langfuse_report.py --window=today
```

The script loads `server/.env` automatically and prints a markdown report to stdout
(and optionally writes it to `--out=PATH`).

## Output Format

```
# Langfuse Activity Report — {window}
Generated: {ISO timestamp}

## Summary
- Total traces: N
- Total observations: N
- Environments: local=N, qa=N, prod=N
- Unique sessions: N
- Tool calls: N

## Environment Breakdown
| Environment | Traces | Tool calls | Generations | Errors |
| ----------- | ------ | ---------- | ----------- | ------ |
| local       | N      | N          | N           | N      |
| qa          | N      | N          | N           | N      |

## Tools Used
| Tool                    | Calls | Envs       |
| ----------------------- | ----- | ---------- |
| research                | 36    | local, qa  |
| web_search              | 17    | local      |
| query_compliance_matrix | 11    | local      |
| create_document         | 8     | local      |
| ...                     |       |            |

## Documents Generated (create_document)
| Doc Type            | Count | Titles (sample)                          |
| ------------------- | ----- | ---------------------------------------- |
| sow                 | 1     | SOW - NCI AI Chat Application ...        |
| igce                | 1     | IGCE - NCI AI Chat Application ...       |
| acquisition_plan    | 1     | Acquisition Plan - NCI AI Chat ...       |
| ...                 |       |                                          |

## Specialist Subagents / Skills Dispatched (research tool)
| Keyword / Topic                  | Calls |
| -------------------------------- | ----- |
| IDIQ minimum guarantee obligation | 2    |
| micro-purchase threshold         | 2     |
| ...                              |       |

## Sources Fetched (web_search + research)
- GSA Professional Services Schedule SIN 541611 / coaching facilitation (7 queries)
- FedRAMP High authorized cloud hosting vendors NIH (10 queries)
- HHS acquisition innovation CSAW (2 queries)
- GAO B-302358 IDIQ minimum obligation (2 queries)

## Errors (if any)
- [trace_id] {error message} — env={env} user={user}
```
