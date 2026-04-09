# EAGLE — Weekly Changelog

Week-by-week rollup of what shipped, derived from git history. Weeks are Mon–Sun. Repo runs `main` only; all PRs merge there. 607 commits total between 2026-01-30 and 2026-04-08.

> Generated 2026-04-09 from commit history. For the condensed top-10 highlights, see the [README](../../README.md#weekly-changelog-highlights).

---

## Week of 2026-01-26 — project seed
- [`b4dd25d`](https://github.com/CBIIT/sm_eagle/commit/b4dd25d) Initial commit
- [`60c1d45`](https://github.com/CBIIT/sm_eagle/commit/60c1d45) Create testing.txt

**Net:** repo stood up as fork from `sample-multi-tenant-agent-core-app`.

---

## Week of 2026-02-02 and 2026-02-09 — document viewer + early skills
- EAGLE-26 document viewer work ([`5945dde`](https://github.com/CBIIT/sm_eagle/commit/5945dde), [`b767072`](https://github.com/CBIIT/sm_eagle/commit/b767072), [`3d0b067`](https://github.com/CBIIT/sm_eagle/commit/3d0b067))
- UC tests 21–27 + viewer modal fixes ([`5b232fd`](https://github.com/CBIIT/sm_eagle/commit/5b232fd))
- Rename viewer → eval across routes ([`9bf73ad`](https://github.com/CBIIT/sm_eagle/commit/9bf73ad))
- SDK skill → subagent orchestration service + eval test 28 ([`8f92348`](https://github.com/CBIIT/sm_eagle/commit/8f92348))
- PDF + Word document export utilities ([`08ec3e5`](https://github.com/CBIIT/sm_eagle/commit/08ec3e5))
- 6 skill scenario diagrams, conversation trace capture, EAGLE plugin refactor ([`db6929a`](https://github.com/CBIIT/sm_eagle/commit/db6929a))
- AWS + Git experts, Excalidraw skill, specs, eval enhancements ([`1e2d79a`](https://github.com/CBIIT/sm_eagle/commit/1e2d79a))

**Net:** plugin architecture takes shape; NCI/OA document export pipeline lands.

---

## Week of 2026-02-16 — CDK infrastructure + documentation push
- CDK Core/Compute/CiCd stacks ([`5accad1`](https://github.com/CBIIT/sm_eagle/commit/5accad1))
- Restructure codebase to AWS QuickStart pattern ([`5fcb27f`](https://github.com/CBIIT/sm_eagle/commit/5fcb27f))
- Migrate DynamoDB 3-table → unified `eagle` single-table ([`2fa9d12`](https://github.com/CBIIT/sm_eagle/commit/2fa9d12))
- Home page redesign + document viewer integration ([`a3b2da9`](https://github.com/CBIIT/sm_eagle/commit/a3b2da9), [`4d34e80`](https://github.com/CBIIT/sm_eagle/commit/4d34e80))
- Playwright smoke/e2e + Justfile task runner + storage stack + lambda metadata ([`7cba8bc`](https://github.com/CBIIT/sm_eagle/commit/7cba8bc))
- Backend infra fix + bowser commands + Obsidian skills + Excalidraw diagrams ([`ba1c2a4`](https://github.com/CBIIT/sm_eagle/commit/ba1c2a4))
- Smoke test expanded to 22 tests + admin sub-page coverage ([`fb76a38`](https://github.com/CBIIT/sm_eagle/commit/fb76a38), [`2086151`](https://github.com/CBIIT/sm_eagle/commit/2086151))
- README rewrite for CDK + EAGLE plugin architecture ([`a469768`](https://github.com/CBIIT/sm_eagle/commit/a469768))
- Storage stack infrastructure ([`7882337`](https://github.com/CBIIT/sm_eagle/commit/7882337))

**Net:** the 6-stack CDK shape we use today was laid down this week, and Justfile became the canonical task runner.

---

## Week of 2026-02-23 — Claude SDK, EC2 runner, Strands POC
- AWS SSO credential support for local dev + Bedrock ([`19ccb8b`](https://github.com/CBIIT/sm_eagle/commit/19ccb8b))
- Replace stale AgentCore architecture diagram with real ASCII ([`e29085b`](https://github.com/CBIIT/sm_eagle/commit/e29085b))
- Add contract requirements matrix ([`e8551b0`](https://github.com/CBIIT/sm_eagle/commit/e8551b0))
- Migrate orchestration → Claude Agent SDK + validation ladder + scribe agent ([`e358c83`](https://github.com/CBIIT/sm_eagle/commit/e358c83))
- EC2 GitHub self-hosted runner CloudFormation stack ([`8121b0c`](https://github.com/CBIIT/sm_eagle/commit/8121b0c))
- Cache NCI account AZs, EC2 runner as standard deploy method ([`ba7f0bc`](https://github.com/CBIIT/sm_eagle/commit/ba7f0bc), [`de64951`](https://github.com/CBIIT/sm_eagle/commit/de64951))
- 4 bowser E2E validation skills ([`e321607`](https://github.com/CBIIT/sm_eagle/commit/e321607))
- Cognito auth global setup + streaming detection fix + session memory multi-turn test
- Sprint 1–4: specialist-skills + UC workflows, DynamoDB/S3/CloudWatch integration tests, tier-gating, post-deploy eval, ECS/ALB health checks in CI
- Restrict Bedrock IAM to Haiku 4.5 only ([`09e9c20`](https://github.com/CBIIT/sm_eagle/commit/09e9c20))
- Add `/pull-remote` skill + `/sync` hub-and-spoke skill ([`b74f72c`](https://github.com/CBIIT/sm_eagle/commit/b74f72c), [`3f13f82`](https://github.com/CBIIT/sm_eagle/commit/3f13f82))
- Excalidraw MCP App + admin AI Diagram Studio ([`36a4b9d`](https://github.com/CBIIT/sm_eagle/commit/36a4b9d))
- Rewrite `CLAUDE.md` using coleam00 template framework ([`1d4ce56`](https://github.com/CBIIT/sm_eagle/commit/1d4ce56))
- **Strands Agents SDK POC** — expert, tests, full migration plan ([`48395e9`](https://github.com/CBIIT/sm_eagle/commit/48395e9))
- Strands Phase 2–3: drop-in `strands_agentic_service` + route wiring ([`ea8d316`](https://github.com/CBIIT/sm_eagle/commit/ea8d316))
- Strands Phase 4–5: port eval suite + cleanup ([`ae222ee`](https://github.com/CBIIT/sm_eagle/commit/ae222ee))
- Strands session persistence (EAGLE-44) + real-time SSE via QueueCallbackHandler (EAGLE-48) ([`60c2950`](https://github.com/CBIIT/sm_eagle/commit/60c2950), [`c9d8563`](https://github.com/CBIIT/sm_eagle/commit/c9d8563))
- Jira expert domain + story-writer skill ([`beae65f`](https://github.com/CBIIT/sm_eagle/commit/beae65f))

**Net:** Strands SDK POC completed and wired; EC2 runner became the standard deploy path.

---

## Week of 2026-03-02 — Strands migration lands + tool observability
- Complete Strands migration + cleanup ([`3e8ebc1`](https://github.com/CBIIT/sm_eagle/commit/3e8ebc1), [`555b37f`](https://github.com/CBIIT/sm_eagle/commit/555b37f))
- Restore SSE streaming revert after sync overwrite ([`ad07f70`](https://github.com/CBIIT/sm_eagle/commit/ad07f70))
- Post-Strands cleanup: fix tests, update docs, rename diagrams ([`ca89780`](https://github.com/CBIIT/sm_eagle/commit/ca89780))
- Add `query_compliance_matrix` — deterministic contract decision tree ([`823a8e4`](https://github.com/CBIIT/sm_eagle/commit/823a8e4))
- Wire AWS service tools to supervisor + async queue bridge ([`195cec1`](https://github.com/CBIIT/sm_eagle/commit/195cec1))
- Streaming proxy fix + trivial-message fast path + IndexedDB cache ([`2d227fd`](https://github.com/CBIIT/sm_eagle/commit/2d227fd))
- Reduce chat latency for trivial messages 10s → <1s ([`6ed52a4`](https://github.com/CBIIT/sm_eagle/commit/6ed52a4))
- Test result persistence to DynamoDB + admin viewer ([`d2dbbd1`](https://github.com/CBIIT/sm_eagle/commit/d2dbbd1))
- Strands Agents SDK migration + feature backfill ([`8d1f56a`](https://github.com/CBIIT/sm_eagle/commit/8d1f56a))
- Add login page + Cognito session timeout ([`da696bd`](https://github.com/CBIIT/sm_eagle/commit/da696bd))
- DEV_MODE=true in ECS backend task definition ([`156a98e`](https://github.com/CBIIT/sm_eagle/commit/156a98e))
- Migration script + Lambda change ([`27ce3bc`](https://github.com/CBIIT/sm_eagle/commit/27ce3bc))
- User feedback feature — `FEEDBACK#` entity, `/api/feedback`, `/feedback` slash command ([`cd8c259`](https://github.com/CBIIT/sm_eagle/commit/cd8c259))
- Sub-commands per skill, admin CRUD skill, bigger command palette ([`ea27a2d`](https://github.com/CBIIT/sm_eagle/commit/ea27a2d))
- Wire workspace + agent prompts + skill templates to real APIs ([`04e8ac3`](https://github.com/CBIIT/sm_eagle/commit/04e8ac3))
- Global Ctrl+J feedback modal with DynamoDB persistence ([`a6389a3`](https://github.com/CBIIT/sm_eagle/commit/a6389a3))
- Prune dead schema types, unify `AcquisitionData`, expand `DocumentType` ([`64fa76d`](https://github.com/CBIIT/sm_eagle/commit/64fa76d))
- Eval DDB persistence + test analytics dashboard + `use-case-builder` skill ([`b53d5d3`](https://github.com/CBIIT/sm_eagle/commit/b53d5d3))
- AWS Backup plan: hourly DynamoDB + daily S3 ([`d56f85a`](https://github.com/CBIIT/sm_eagle/commit/d56f85a))
- Eval video recording + Haiku default + S3 seed documents ([`0f22a0f`](https://github.com/CBIIT/sm_eagle/commit/0f22a0f))
- Branded DOCX/PDF export + header nav + Ctrl+Enter feedback ([`bfecd82`](https://github.com/CBIIT/sm_eagle/commit/bfecd82))
- Default Bedrock model → Sonnet 4.6 ([`987f579`](https://github.com/CBIIT/sm_eagle/commit/987f579), [`15496de`](https://github.com/CBIIT/sm_eagle/commit/15496de))
- Auto-select model by AWS account at startup ([`c8c03cd`](https://github.com/CBIIT/sm_eagle/commit/c8c03cd))
- SSE keepalive to prevent ALB idle timeout on long Bedrock calls ([`413689c`](https://github.com/CBIIT/sm_eagle/commit/413689c))
- Auto-sync EAGLE-DEV-ALB target group after frontend deploy ([`6821fa2`](https://github.com/CBIIT/sm_eagle/commit/6821fa2))
- Feedback snapshot with page + message ID ([`b6f4bc5`](https://github.com/CBIIT/sm_eagle/commit/b6f4bc5))
- Full tool observability + dev-local workflow ([`fda8a17`](https://github.com/CBIIT/sm_eagle/commit/fda8a17))
- Emit `tool_result` for standalone tools: `load_data`, compliance, skills ([`de33e01`](https://github.com/CBIIT/sm_eagle/commit/de33e01), [`e08cc09`](https://github.com/CBIIT/sm_eagle/commit/e08cc09))
- **Migrate to Strands `stream_async()`** — eliminate two-queue SSE architecture ([`74616de`](https://github.com/CBIIT/sm_eagle/commit/74616de))
- SSE test suite + markdown tables + `load_data` fix + Excalidraw light theme ([`38bea88`](https://github.com/CBIIT/sm_eagle/commit/38bea88))
- Fast-path routing + thresholds + knowledge tools wired ([`a4a2025`](https://github.com/CBIIT/sm_eagle/commit/a4a2025))

**Net:** Strands SDK is fully in production, tool observability is complete, two-queue SSE is gone.

---

## Week of 2026-03-09 — native Office, document chat
- Implement document change log ([`da47c7a`](https://github.com/CBIIT/sm_eagle/commit/da47c7a))
- **Native DOCX/XLSX preview and editing** across the app, binary-safe document APIs, package document/changelog routes, AI-driven DOCX revision tooling ([`1b6a0be`](https://github.com/CBIIT/sm_eagle/commit/1b6a0be))
- Document chat context + download streaming fixes ([`3af1268`](https://github.com/CBIIT/sm_eagle/commit/3af1268), [`a8e743f`](https://github.com/CBIIT/sm_eagle/commit/a8e743f))
- Add PUT option for documents ([`60e53b3`](https://github.com/CBIIT/sm_eagle/commit/60e53b3))

**Net:** Office-format round-tripping in the chat UI.

---

## Week of 2026-03-16 — Langfuse tracing + MVP1 eval skill + admin observability
- **Langfuse OTEL tracing + MVP1 eval skill** ([`cf4b8d2`](https://github.com/CBIIT/sm_eagle/commit/cf4b8d2))
- Fix test suite after PR #24 merge ([`5cd60ca`](https://github.com/CBIIT/sm_eagle/commit/5cd60ca))
- **Langfuse-backed admin traces dashboard** ([`c7196fc`](https://github.com/CBIIT/sm_eagle/commit/c7196fc))
- Automated error webhook for API 5xx + streaming errors ([`d6e3f4e`](https://github.com/CBIIT/sm_eagle/commit/d6e3f4e))
- 7 MVP1 UC eval tests (36-42), demo script, test suite fixes ([`a58d8f9`](https://github.com/CBIIT/sm_eagle/commit/a58d8f9))
- Multi-turn copy-paste test prompts for all 9 MVP1 UCs ([`fb7eb66`](https://github.com/CBIIT/sm_eagle/commit/fb7eb66))
- Fix document generation saving raw templates instead of AI-filled content ([`f9ff9b3`](https://github.com/CBIIT/sm_eagle/commit/f9ff9b3))
- Real-time streaming UX (tool cards, agent status) + **Langfuse error classification** ([`61506d8`](https://github.com/CBIIT/sm_eagle/commit/61506d8))
- Template schema validation + expand doc type coverage ([`67460ae`](https://github.com/CBIIT/sm_eagle/commit/67460ae))
- Load data tool + streaming message ID fix ([`4d36ad1`](https://github.com/CBIIT/sm_eagle/commit/4d36ad1))
- S3 `PutObject` AccessDenied — add `EagleCoreStack` to CDK deploy ([`e29045b`](https://github.com/CBIIT/sm_eagle/commit/e29045b))
- Templates + upload flow + doc upload hardening ([`3b59f20`](https://github.com/CBIIT/sm_eagle/commit/3b59f20), [`263b5a2`](https://github.com/CBIIT/sm_eagle/commit/263b5a2))
- Teams QA channel webhook + daily digest ([`f8d5b18`](https://github.com/CBIIT/sm_eagle/commit/f8d5b18))
- S3 template viewer + frontend UI edits ([`fbaa2e4`](https://github.com/CBIIT/sm_eagle/commit/fbaa2e4))
- Dynamic required-docs computation + `finalize_package` tool ([`346eb2f`](https://github.com/CBIIT/sm_eagle/commit/346eb2f))
- Style FAR/DFARS citations in DOCX + PDF exports ([`189a2f1`](https://github.com/CBIIT/sm_eagle/commit/189a2f1))
- Tool timing telemetry + state update SSE events ([`5426254`](https://github.com/CBIIT/sm_eagle/commit/5426254))
- FAR database `s3_keys` field ([`aabf8a9`](https://github.com/CBIIT/sm_eagle/commit/aabf8a9))
- Frontend state tab + markdown components + admin preview toggle ([`8514541`](https://github.com/CBIIT/sm_eagle/commit/8514541))
- Enable **Bedrock prompt caching** + reduce per-request setup overhead ([`6aa9b45`](https://github.com/CBIIT/sm_eagle/commit/6aa9b45))
- Bedrock cache point saga: enable → bypass botocore validation → revert (Strands SDK can't parse) → upgrade boto3 → re-enable ([`64b4d76`](https://github.com/CBIIT/sm_eagle/commit/64b4d76) → [`9ad20ad`](https://github.com/CBIIT/sm_eagle/commit/9ad20ad))
- Refactor Phase 0–2: date utilities, DynamoDB singleton, centralized config, agent logs consolidation ([`c18d474`](https://github.com/CBIIT/sm_eagle/commit/c18d474), [`cb3f622`](https://github.com/CBIIT/sm_eagle/commit/cb3f622), [`1c8c403`](https://github.com/CBIIT/sm_eagle/commit/1c8c403), [`7325bbd`](https://github.com/CBIIT/sm_eagle/commit/7325bbd))
- Use **Cognito username for Langfuse user identity** + feedback store + admin tools ([`1f948d3`](https://github.com/CBIIT/sm_eagle/commit/1f948d3))
- Teams Adaptive Card formatting + morning report ([`2a167c2`](https://github.com/CBIIT/sm_eagle/commit/2a167c2))
- Restore reasoning store + align test assertions (fix 21 failing tests) ([`77fe7c0`](https://github.com/CBIIT/sm_eagle/commit/77fe7c0))
- Fix document naming regression + consolidate eval ignores in `pytest.ini` ([`a67c55a`](https://github.com/CBIIT/sm_eagle/commit/a67c55a))

**Net:** Langfuse observability is live end-to-end — OTEL export, admin trace viewer, error classification, user identity attribution. Prompt caching enabled.

---

## Week of 2026-03-23 — 30 new eval tests, QA env, /triage skill, /ship orchestrator
- 30 new eval tests (99–128): package creation, guardrails, content quality, skill quality ([`51e1613`](https://github.com/CBIIT/sm_eagle/commit/51e1613))
- SSE text spacing across tool boundaries + interleaved text/tool cards ([`ee86782`](https://github.com/CBIIT/sm_eagle/commit/ee86782))
- Fix 3 eval feature gaps: `session_store` imports, AP milestones, micro-purchase guardrail ([`8e27459`](https://github.com/CBIIT/sm_eagle/commit/8e27459))
- SOW scope leak + AI title regen + auto-fetch web search ([`cad8460`](https://github.com/CBIIT/sm_eagle/commit/cad8460))
- **Add QA environment**: CDK stack, deploy pipeline, Justfile ([`48e9593`](https://github.com/CBIIT/sm_eagle/commit/48e9593))
- Distinguish cancelled deploys from failures in Teams report ([`247abce`](https://github.com/CBIIT/sm_eagle/commit/247abce))
- QA IP-type TG + per-env concurrency groups ([`21ae664`](https://github.com/CBIIT/sm_eagle/commit/21ae664))
- Wire reasoning + handoff SSE events through streaming pipeline ([`28f8c50`](https://github.com/CBIIT/sm_eagle/commit/28f8c50))
- Document prerequisites guardrail: block generation without required info ([`6ade843`](https://github.com/CBIIT/sm_eagle/commit/6ade843))
- `web_fetch`: browser-realistic headers, cache fallbacks for 403s ([`376038f`](https://github.com/CBIIT/sm_eagle/commit/376038f))
- Security alerts + error sanitization ([`007fb8c`](https://github.com/CBIIT/sm_eagle/commit/007fb8c))
- Align agent logs panel with NCI light-mode palette ([`03faed8`](https://github.com/CBIIT/sm_eagle/commit/03faed8))
- Consolidate pre-inference status → single "Reasoning..." ([`cf3723a`](https://github.com/CBIIT/sm_eagle/commit/cf3723a))
- Fix pickle error in SSE stream: replace `asdict()` ([`74c78a0`](https://github.com/CBIIT/sm_eagle/commit/74c78a0))
- Wire git SHA into health endpoint ([`cab5f68`](https://github.com/CBIIT/sm_eagle/commit/cab5f68))
- Preload user context on session start ([`1df6dcc`](https://github.com/CBIIT/sm_eagle/commit/1df6dcc))
- **Enforce KB + compliance matrix before web search in supervisor cascade** ([`07b518c`](https://github.com/CBIIT/sm_eagle/commit/07b518c))
- Template provenance + multi-dimensional tagging + compliance clause references ([`0d1e769`](https://github.com/CBIIT/sm_eagle/commit/0d1e769))
- Remove orphaned `strands/` package + unused `chat-simple` components ([`b36b43d`](https://github.com/CBIIT/sm_eagle/commit/b36b43d))
- Expand doc upload classification to all 22 template categories with markdown persistence ([`a8ca2e9`](https://github.com/CBIIT/sm_eagle/commit/a8ca2e9))
- Fix S3 path duplication + Decimal serialization ([`d1cc0ec`](https://github.com/CBIIT/sm_eagle/commit/d1cc0ec))
- Conversation compaction via Strands `SummarizingConversationManager` ([`aa66290`](https://github.com/CBIIT/sm_eagle/commit/aa66290))
- Enforce 80%+ viewport width on all modals ([`85cd7dc`](https://github.com/CBIIT/sm_eagle/commit/85cd7dc))
- AI-powered template markdown standardization with batch API ([`2fb7261`](https://github.com/CBIIT/sm_eagle/commit/2fb7261))
- **`/triage` skill — unified diagnostic across DynamoDB feedback + CloudWatch + Langfuse** ([`f957de3`](https://github.com/CBIIT/sm_eagle/commit/f957de3))
- **Fix Langfuse trace nesting by wrapping Strands agent calls in parent spans** ([`875294f`](https://github.com/CBIIT/sm_eagle/commit/875294f))
- Activity panel event count fix + user/agent badge distinction ([`96e1e8f`](https://github.com/CBIIT/sm_eagle/commit/96e1e8f))
- **Nightly triage GitHub Actions workflow for dev + qa** ([`08f904d`](https://github.com/CBIIT/sm_eagle/commit/08f904d))
- Chat streaming flicker fix: RAF batching + scroll debounce + memoized markdown ([`46537b3`](https://github.com/CBIIT/sm_eagle/commit/46537b3))
- 503 health check flicker + auth status indicator ([`1f3bf84`](https://github.com/CBIIT/sm_eagle/commit/1f3bf84))
- Sidebar conversation list improvements + delete button ([`b57349a`](https://github.com/CBIIT/sm_eagle/commit/b57349a))
- Compact inline tool chips + click-to-modal (replaces full-width cards) ([`5ef82e7`](https://github.com/CBIIT/sm_eagle/commit/5ef82e7))
- Settings gear with admin mode toggle ([`52217c6`](https://github.com/CBIIT/sm_eagle/commit/52217c6))
- Memoize context values + hook returns ([`b6d4256`](https://github.com/CBIIT/sm_eagle/commit/b6d4256))
- Add formatting: **Prettier + ruff format** + format recipes ([`3fd551a`](https://github.com/CBIIT/sm_eagle/commit/3fd551a), [`1262751`](https://github.com/CBIIT/sm_eagle/commit/1262751))
- LICENSE + CONTRIBUTING + SECURITY + `.editorconfig` + PR template ([`8d619cb`](https://github.com/CBIIT/sm_eagle/commit/8d619cb))
- Clean root dir + reorganize docs + improve README ([`896efe6`](https://github.com/CBIIT/sm_eagle/commit/896efe6))
- AWS ops tools: S3 delete/copy/rename/presign, DynamoDB batch, CloudWatch Insights ([`e62ba58`](https://github.com/CBIIT/sm_eagle/commit/e62ba58))
- Enable micropurchase doc gen + checklist-first logic ([`feee8e6`](https://github.com/CBIIT/sm_eagle/commit/feee8e6))
- 5 Jira QA eval tests (138-142) for EAGLE-70 → EAGLE-76 ([`2b0fc04`](https://github.com/CBIIT/sm_eagle/commit/2b0fc04))
- Triage diagnostic skill for session-level troubleshooting ([`b6ff6bc`](https://github.com/CBIIT/sm_eagle/commit/b6ff6bc))
- **e2e-judge screenshot-based testing system with LLM-as-judge evaluation** ([`9e8855d`](https://github.com/CBIIT/sm_eagle/commit/9e8855d))
- Workflows/acquisition packages journey added to e2e-judge ([`58cf313`](https://github.com/CBIIT/sm_eagle/commit/58cf313))
- Activity panel all-packages list + document expansion ([`92826b6`](https://github.com/CBIIT/sm_eagle/commit/92826b6))
- Stream tool input into chip modal with live markdown preview ([`cd7140d`](https://github.com/CBIIT/sm_eagle/commit/cd7140d))
- 3-phase acquisition journey: consult → generate → finalize ([`e126cd1`](https://github.com/CBIIT/sm_eagle/commit/e126cd1))
- Wire package state events through SSE + inline state change cards ([`1cd8d1e`](https://github.com/CBIIT/sm_eagle/commit/1cd8d1e))
- Persist SSE streaming state across page refresh ([`a17d6b8`](https://github.com/CBIIT/sm_eagle/commit/a17d6b8))
- Required Document Metadata section on all generated documents ([`da4acd3`](https://github.com/CBIIT/sm_eagle/commit/da4acd3))
- Progressive KB document list loading (20 at a time) ([`4389bc5`](https://github.com/CBIIT/sm_eagle/commit/4389bc5))
- Knowledge Base tests + preview modal markdown ([`dab812f`](https://github.com/CBIIT/sm_eagle/commit/dab812f))
- Document generation diagnostics + progress status events ([`fa04579`](https://github.com/CBIIT/sm_eagle/commit/fa04579))
- **Improve CloudWatch and Langfuse observability for ECS tool execution** ([`06a3fc3`](https://github.com/CBIIT/sm_eagle/commit/06a3fc3))
- **Add `/admin` diagnostic command with Langfuse trace querying** ([`0909667`](https://github.com/CBIIT/sm_eagle/commit/0909667))
- **Enforce KB-first research cascade — fix 79% violation rate from Langfuse analysis** ([`c51a346`](https://github.com/CBIIT/sm_eagle/commit/c51a346))
- Contract Requirements Matrix modal (Ctrl+M) with 3 tabs ([`a47c443`](https://github.com/CBIIT/sm_eagle/commit/a47c443))
- Migrate frontend slash commands → dynamic backend registry ([`cbb76be`](https://github.com/CBIIT/sm_eagle/commit/cbb76be))
- `generate_html_playground` Strands tool + playground skill ([`e192382`](https://github.com/CBIIT/sm_eagle/commit/e192382))
- Eliminate all mock frontend data → real API calls ([`2c3b7dc`](https://github.com/CBIIT/sm_eagle/commit/2c3b7dc))
- Replace f-string document generators with **Bedrock LLM-backed generation** ([`65b222a`](https://github.com/CBIIT/sm_eagle/commit/65b222a))
- Add rich interactive compliance matrix visualization ([`de0d5cf`](https://github.com/CBIIT/sm_eagle/commit/de0d5cf))
- 33 tests for package enhancements: delete, clone, ZIP, export tracking ([`3974289`](https://github.com/CBIIT/sm_eagle/commit/3974289))
- Tier 4 frontend E2E tests added to mvp1-eval skill ([`7e5f193`](https://github.com/CBIIT/sm_eagle/commit/7e5f193))

**Net:** eval suite grew to ~130 tests; Langfuse observability surfaced a 79% cascade violation rate that led to hard-enforced KB-first routing; `/triage` and nightly-triage landed; full Office UI matured.

---

## Week of 2026-03-30 — model resilience, cold-start, Jira QA
- **Nova Pro fallback** when Sonnet 4.6 returns `ServiceUnavailableException` ([`c6a6eb9`](https://github.com/CBIIT/sm_eagle/commit/c6a6eb9))
- **45s TTFT timeout + automatic Haiku fallback** ([`0eec536`](https://github.com/CBIIT/sm_eagle/commit/0eec536))
- Restore greeting fast-path for trivial messages ([`c5235ba`](https://github.com/CBIIT/sm_eagle/commit/c5235ba))
- Make eval job opt-in only (off by default on push) ([`483a7a6`](https://github.com/CBIIT/sm_eagle/commit/483a7a6))
- Switch primary model Sonnet 4.6 → Haiku (Sonnet TTFT 100% failure) ([`9cf56ae`](https://github.com/CBIIT/sm_eagle/commit/9cf56ae))
- **Remove legacy `agentic_service.py` + `sdk_agentic_service.py` (−5,500 lines)** ([`ed61255`](https://github.com/CBIIT/sm_eagle/commit/ed61255))
- **Model circuit breaker with 4-model fallback chain** ([`f088656`](https://github.com/CBIIT/sm_eagle/commit/f088656))
- Remove dead weather MCP service ([`42bd9fe`](https://github.com/CBIIT/sm_eagle/commit/42bd9fe))
- Improve nightly triage — fix dev+qa race, unblock CloudWatch, close orphan spans ([`ce9df11`](https://github.com/CBIIT/sm_eagle/commit/ce9df11))
- Cold-start latency: parallel probe, lazy init, batch seeding ([`af08112`](https://github.com/CBIIT/sm_eagle/commit/af08112))
- 6 triage bug fixes: checklist completion, doc cards, cold-start, titles, feedback, ZIP export ([`e2c9324`](https://github.com/CBIIT/sm_eagle/commit/e2c9324))
- Overhaul tool card modals — 80vw width, markdown rendering ([`730150d`](https://github.com/CBIIT/sm_eagle/commit/730150d))
- Clickable checklist documents with viewer modal ([`3956edf`](https://github.com/CBIIT/sm_eagle/commit/3956edf))
- Fix stale "Package Updated" card on non-package turns ([`3f501ab`](https://github.com/CBIIT/sm_eagle/commit/3f501ab))
- Compliance matrix: normalization layer for method/type IDs ([`ace19d5`](https://github.com/CBIIT/sm_eagle/commit/ace19d5))
- `knowledge_search` `RecursionError` fix — sanitize DynamoDB items ([`5e3db01`](https://github.com/CBIIT/sm_eagle/commit/5e3db01))
- Strict enum schemas on `knowledge_search` inputs ([`97daf7d`](https://github.com/CBIIT/sm_eagle/commit/97daf7d))
- Fix document export/viewer: wrong sidecar path, missing content, no markdown passthrough ([`0a1a819`](https://github.com/CBIIT/sm_eagle/commit/0a1a819))
- Refactor `main.py` — extract knowledge routes, add `/ping`, deploy recipes ([`c9c0b9e`](https://github.com/CBIIT/sm_eagle/commit/c9c0b9e))
- Frontend dev mode — require explicit opt-in ([`677fddc`](https://github.com/CBIIT/sm_eagle/commit/677fddc))
- **Feedback-to-JIRA-to-Teams pipeline with action buttons** ([`fa30f4c`](https://github.com/CBIIT/sm_eagle/commit/fa30f4c))
- **Eval scoring enrichment — quality rollup, confidence, tool-call scores in reports** ([`d60bca1`](https://github.com/CBIIT/sm_eagle/commit/d60bca1))
- Fix feedback timeout + narrow greeting fast path ([`7dcd46d`](https://github.com/CBIIT/sm_eagle/commit/7dcd46d))
- Unified document store + Excel docs refactor ([`4f23487`](https://github.com/CBIIT/sm_eagle/commit/4f23487), [`dc951ad`](https://github.com/CBIIT/sm_eagle/commit/dc951ad))
- Wire `EAGLE_BACKEND_URL` + JIRA config into CDK compute stack ([`889f5ea`](https://github.com/CBIIT/sm_eagle/commit/889f5ea))
- Fix Triage P1s: Haiku model ID, OTLP startup probe, localhost feedback ([`5dba209`](https://github.com/CBIIT/sm_eagle/commit/5dba209))
- Feedback modal: area tags, screenshot capture, display name ([`73d69e5`](https://github.com/CBIIT/sm_eagle/commit/73d69e5))
- Fix Sonnet TTFT: restore 3-model cascade, reduce retries + timeout ([`fcdab2c`](https://github.com/CBIIT/sm_eagle/commit/fcdab2c))
- Haiku model ID: add `us.` prefix for cross-region inference ([`86b23ba`](https://github.com/CBIIT/sm_eagle/commit/86b23ba))
- Fix `knowledge_search` zero-results regression + regression tests ([`a153f31`](https://github.com/CBIIT/sm_eagle/commit/a153f31))
- **Triage P0: block OTLP exporter on 401 auth + fix `template_store` import** ([`1a3755a`](https://github.com/CBIIT/sm_eagle/commit/1a3755a))
- Langfuse test: mock `httpx.post` auth probe in exporter init ([`8432138`](https://github.com/CBIIT/sm_eagle/commit/8432138))
- Fix 12 broken tests: update mocks for unified document store refactor ([`fd601a5`](https://github.com/CBIIT/sm_eagle/commit/fd601a5))
- Twemoji eagle favicon on navy background ([`62617ed`](https://github.com/CBIIT/sm_eagle/commit/62617ed))
- **TTFT probe test for all Claude + Nova Bedrock models** ([`36a947c`](https://github.com/CBIIT/sm_eagle/commit/36a947c))
- **Bedrock-powered PDF parsing via Converse API document blocks** ([`25783a8`](https://github.com/CBIIT/sm_eagle/commit/25783a8))
- **IGCE Excel generation: position-based cell population + preserve live formulas** ([`8ce77ab`](https://github.com/CBIIT/sm_eagle/commit/8ce77ab))
- TTFT cold starts: keepalive loop + Bedrock invocation logging ([`66d79cb`](https://github.com/CBIIT/sm_eagle/commit/66d79cb))
- CDK: reference pre-provisioned Bedrock logging resources ([`f947406`](https://github.com/CBIIT/sm_eagle/commit/f947406))
- Circuit breaker: catch Bedrock read timeouts ([`8cbc278`](https://github.com/CBIIT/sm_eagle/commit/8cbc278))
- Compliance matrix: unify thresholds, expand J&A paths + 8(a) support ([`38f1416`](https://github.com/CBIIT/sm_eagle/commit/38f1416))
- KB cascade enforcement + compliance matrix deep research ([`af83106`](https://github.com/CBIIT/sm_eagle/commit/af83106))
- **Baseline-questions skill + v4/v5 evaluation scripts** ([`199e2d2`](https://github.com/CBIIT/sm_eagle/commit/199e2d2))
- Jira integration + triage notifications + infra updates ([`5650276`](https://github.com/CBIIT/sm_eagle/commit/5650276))
- **Context-aware IGCE XLSX generation + workbook-wide AI editing** ([`63803ce`](https://github.com/CBIIT/sm_eagle/commit/63803ce))
- **Enforce checklist lookup before document recommendations** ([`98bc7ab`](https://github.com/CBIIT/sm_eagle/commit/98bc7ab))
- Auto-fetch PMR checklist content in `query_compliance_matrix` ([`8160721`](https://github.com/CBIIT/sm_eagle/commit/8160721))
- **Composite research tool — dynamic KB + checklist in one call** ([`7d3e8ac`](https://github.com/CBIIT/sm_eagle/commit/7d3e8ac))
- **v6 baseline evaluation results: 19.5/20 avg, no regressions** ([`8d5016f`](https://github.com/CBIIT/sm_eagle/commit/8d5016f))
- Add delete button to acquisition packages ([`af14992`](https://github.com/CBIIT/sm_eagle/commit/af14992))
- Rename document stores + wipe all docs/packages from dev ([`6d2d663`](https://github.com/CBIIT/sm_eagle/commit/6d2d663))
- Fix KB search overflow + safeguard wipe script + local CloudWatch logging ([`c2a95e8`](https://github.com/CBIIT/sm_eagle/commit/c2a95e8))
- Isolate checklist fetching in research tool + `/kb-regenerate` command ([`a522b2d`](https://github.com/CBIIT/sm_eagle/commit/a522b2d))
- **Fix EAGLE-74 FAR numbering + EAGLE-77 template visibility (7/7 Jira QA PASS)** ([`1bb4c46`](https://github.com/CBIIT/sm_eagle/commit/1bb4c46))

**Net:** model resilience hardened (TTFT probe, circuit breaker, 4-model fallback, Nova Pro, TTFT timeout); feedback → JIRA → Teams fully wired; composite `research` tool replaces ad-hoc cascades; baseline-questions skill ships; Jira QA run scored 7/7 PASS; IGCE Excel + Bedrock-native PDF parsing land.

---

## Week of 2026-04-06 — prompt caching, V9 baseline, Sources tab, data schema
- **Enable Bedrock prompt caching for all models via Strands SDK** ([`90c44a5`](https://github.com/CBIIT/sm_eagle/commit/90c44a5))
- Propagate cache token usage from Strands SDK to REST response ([`f7c9c31`](https://github.com/CBIIT/sm_eagle/commit/f7c9c31))
- Surface subagent KB document reads in supervisor response ([`f0d5060`](https://github.com/CBIIT/sm_eagle/commit/f0d5060))
- **V9 baseline: dynamic questions, HTML report, 250/260 across 13 questions** ([`fc71160`](https://github.com/CBIIT/sm_eagle/commit/fc71160))
- `Research` tool card with structured modal display ([`0fd4353`](https://github.com/CBIIT/sm_eagle/commit/0fd4353))
- Require acquisition context before generating documents (SOW guardrail) ([`d1f23ec`](https://github.com/CBIIT/sm_eagle/commit/d1f23ec))
- Guarantee path-search doc fetching + AI ranker coverage + baseline `--questions` flag ([`dacf5ed`](https://github.com/CBIIT/sm_eagle/commit/dacf5ed))
- **Sources tab in activity panel + streamline supervisor tool instructions** ([`9e0a85d`](https://github.com/CBIIT/sm_eagle/commit/9e0a85d))
- **RO vs EAGLE search comparison doc + Jira QA memo + baseline Excel** ([`d526674`](https://github.com/CBIIT/sm_eagle/commit/d526674))
- Clean up repo root — untrack Office docs + scratch files ([`c9afa4c`](https://github.com/CBIIT/sm_eagle/commit/c9afa4c))
- Feedback submit fix on deployed env ([`8e6942f`](https://github.com/CBIIT/sm_eagle/commit/8e6942f))
- Tool cards "Writing…" stuck state fix ([`22c8f58`](https://github.com/CBIIT/sm_eagle/commit/22c8f58))
- Session delete now detaches linked packages ([`93615b1`](https://github.com/CBIIT/sm_eagle/commit/93615b1))
- **User-level isolation in knowledge search + checklist provenance** ([`2a0f0d2`](https://github.com/CBIIT/sm_eagle/commit/2a0f0d2))
- Fix EAGLE-77 template search guardrail blocking doc generation ([`53bc9da`](https://github.com/CBIIT/sm_eagle/commit/53bc9da))
- Checklist provenance fields added to `PackageChecklist` TS interface ([`1ea3a06`](https://github.com/CBIIT/sm_eagle/commit/1ea3a06))
- Package panel lost state fix + missing API proxy routes ([`b59bcf8`](https://github.com/CBIIT/sm_eagle/commit/b59bcf8))
- **Tabbed document viewer with color-coded tabs + cost/usage footer** ([`0912fcc`](https://github.com/CBIIT/sm_eagle/commit/0912fcc))
- **Rename `/workflows` → `/packages`** ([`d3532de`](https://github.com/CBIIT/sm_eagle/commit/d3532de), [`d3d03d3`](https://github.com/CBIIT/sm_eagle/commit/d3d03d3))
- **Scope `web_search` to .gov sites unless query is market research** ([`f55b800`](https://github.com/CBIIT/sm_eagle/commit/f55b800))
- Convert KB topic/agent/authority filters from hard gates → AI boost hints ([`8d5016f`](https://github.com/CBIIT/sm_eagle/commit/8d5016f))
- Fix streaming duplicates + SON template + package-document linking ([`d967111`](https://github.com/CBIIT/sm_eagle/commit/d967111))
- Render markdown above XLSX + baseline skill updated for 14-question suite ([`63c2f69`](https://github.com/CBIIT/sm_eagle/commit/63c2f69))
- Q14 Zeiss brand-name/GSA scenario added to baseline ([`e02e403`](https://github.com/CBIIT/sm_eagle/commit/e02e403))
- Filter package docs from research results + dedup `.docx`/`.content.md` siblings ([`bdfff95`](https://github.com/CBIIT/sm_eagle/commit/bdfff95))
- Package panel not loading on session-with-existing-package fix ([`5158864`](https://github.com/CBIIT/sm_eagle/commit/5158864))
- Web search tool cards: show query + results ([`f084b09`](https://github.com/CBIIT/sm_eagle/commit/f084b09))
- **Add data schema registry + overhaul execution plan** ([`a488047`](https://github.com/CBIIT/sm_eagle/commit/a488047))
- Align deployment docs with GitHub Actions workflow ([`e789bb4`](https://github.com/CBIIT/sm_eagle/commit/e789bb4))
- **Delete document-generation fast path; all doc-gen flows through supervisor** ([`20d8a0b`](https://github.com/CBIIT/sm_eagle/commit/20d8a0b), [`b1c9c38`](https://github.com/CBIIT/sm_eagle/commit/b1c9c38))

**Net:** prompt caching live everywhere; V9 baseline at 250/260 (96%) across 13 questions; Sources tab surfaces provenance; RO vs EAGLE comparison published; `/workflows` → `/packages` rename; data schema registry begins; doc-generation fast path removed in favor of supervisor-only flow.

---

## At a glance

| Theme | First landed | Where it is now |
|---|---|---|
| **Strands Agents SDK** | 2026-02-27 (POC) | Sole orchestration layer; legacy `agentic_service.py` deleted 2026-03-30 |
| **Langfuse observability** | 2026-03-17 (OTEL + admin viewer) | OTEL exporter, parent-span wrap fix, error classification, eval validators, admin `/admin/traces`, user identity from Cognito |
| **Evaluation suite** | 2026-02 (SDK skill test 28) | 142 numbered tests in [`test_strands_eval.py`](../../server/tests/test_strands_eval.py), baseline-questions skill, mvp1-eval 4-tier ladder, e2e-judge vision QA |
| **Circuit breaker + model resilience** | 2026-03-30 | 4-model chain with 45s TTFT + Haiku fallback + Nova Pro + nightly probe |
| **Compliance matrix** | 2026-03-03 | Deterministic threshold → method → vehicle → documents decision tree, 8(a)/J&A paths, KB-first cascade enforced |
| **Document pipeline (Office)** | 2026-03-09 (native DOCX/XLSX) | IGCE position-based, Bedrock PDF parse, workbook AI edit, tabbed viewer, 22 classification categories |
| **Nightly triage** | 2026-03-24 | GitHub Actions, Langfuse + CloudWatch + DDB feedback cross-reference, auto-commits report + fix plan |
| **Feedback → JIRA → Teams** | 2026-03-31 | Ctrl+J modal → feedback store → JIRA issue → Teams adaptive card with action buttons |
| **CDK stacks** | 2026-02-16 (Core, Compute, CiCd) | 6 stacks total (+Storage, Eval, Backup) |
| **QA environment** | 2026-03-23 | Second CDK deploy target with scoped concurrency groups |
