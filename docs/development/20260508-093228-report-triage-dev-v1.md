# EAGLE Triage Report

**Date**: 2026-05-08
**Environment**: dev
**Window**: 24h
**Tenant**: default-dev
**Mode**: Full
**Sources**: DynamoDB Feedback, CloudWatch Logs (dev), Langfuse Traces (dev)

## Executive Summary

No critical (P0) or high-priority (P1) issues detected in the dev environment over the past 24 hours. The most significant finding is a **document generation failure cluster** — 6 batch `create_job` calls and 1 direct `create_document` call failed due to a Float-to-Decimal serialization error when writing to DynamoDB, all within a single session. Additionally, **knowledge search AI ranking** experienced 6 JSON parse failures (gracefully falling back to deterministic matching), and **document schema validation** flagged 15+ warnings for the unrecognized contract type "FFP Task Orders". Two users were active with 14 Langfuse traces and zero user-reported feedback.

## Source Data

### DynamoDB Feedback

| Metric | Value |
|--------|-------|
| General feedback items | 0 |
| Message-level feedback items | 0 |
| Bug reports | 0 |
| Thumbs down | 0 |
| Thumbs up | 0 |

No feedback submitted by users in the default-dev tenant during the 24h window.

### CloudWatch Errors

**Log Group: `/eagle/ecs/backend-dev`** — 180 records matched, 34,193 scanned

| # | Category | Count | Severity | Time Range |
|---|----------|-------|----------|------------|
| 1 | OTel "Failed to detach context" | 7 | Noise | 20:55:50 |
| 2 | Batch doc gen `create_job` failures | 6 | ACTIONABLE | 20:06:21 |
| 3 | Knowledge search AI ranking JSON parse failures | 6 | Warning | 19:43–20:20 |
| 4 | Document validation warnings (unknown contract_type / estimated_value) | ~15 | Warning | 20:14–20:16 |
| 5 | Bedrock document parser ValidationException (test.pdf) | 3 | ACTIONABLE | 14:47:10 |
| 6 | Keepalive ping failure / InvalidSignatureException | 2 | Warning | 21:02:56 |
| 7 | `create_document` Float→Decimal type error | 1 | ACTIONABLE | 20:10:41 |
| 8 | S3 Vectors SSL certificate failure | 1 | Warning | 20:54:25 |
| 9 | AccessDeniedException on web_search Converse | 1 | ACTIONABLE | 14:47:31 |
| 10 | web_search timeout | 1 | Warning | 14:47:31 |
| 11 | web_fetch DNS resolution failure | 1 | Warning | 14:47:32 |
| 12 | S3 NoSuchKey for package content | 1 | Warning | 14:46:40 |

**Log Group: `/eagle/ecs/frontend-dev`** — 0 errors (5 records scanned)

**Log Group: `/eagle/app`** — 0 errors (0 records scanned)

#### Detailed Error Analysis

**1. Batch Document Generation Failures (6x, session `9867fbe5`)**
```
logger: eagle.tools.batch_doc_gen
msg: "batch_generate_documents: create_job failed for PKG-2026-0026/{doc_type}"
doc_types: sow, igce, market_research, acquisition_plan, justification, qasp
timestamp: 2026-05-07T20:06:21
```
All 6 failures occurred in the same session at the same second, indicating a batch operation where all document types failed simultaneously. Root cause is the Float/Decimal error (see #7).

**2. Float→Decimal Type Error (1x, session `9867fbe5`)**
```
logger: eagle.strands_agent
msg: "Service tool create_document failed: Float types are not supported. Use Decimal types instead."
timestamp: 2026-05-07T20:10:41
```
DynamoDB rejects Python `float` values. The `estimated_value` field in document data arrives as `float` from the AI model and is passed through to DynamoDB without conversion.

**3. Knowledge Search AI Ranking JSON Parse Failures (6x)**
```
logger: eagle.knowledge_tools
msg: "knowledge_search AI ranking failed, falling back: {JSON parse error}"
errors: "Unterminated string" (2x), "Expecting property name" (1x), "Expecting value" (1x), other (2x)
```
The LLM occasionally returns malformed JSON from the ranking prompt. The system gracefully falls back to deterministic matching, but this degrades result quality.

**4. Document Schema Validation Warnings (~15x)**
```
logger: eagle.document_generation / eagle.ai_document_schema
msg: "Unknown contract_type: FFP Task Orders"
msg: "estimated_value: Input should be a valid number, unable to parse string as a number"
doc_types: qasp, eval_criteria, igce, justification, acquisition_plan
```
"FFP Task Orders" is not in the `CONTRACT_TYPE_ALIASES` map. The `estimated_value` field receives non-numeric strings (e.g., "$150,000" or "TBD") that fail Pydantic `float` validation.

**5. Bedrock Document Parser ValidationException (3x)**
```
logger: eagle.bedrock_document_parser
msg: "Bedrock Converse failed for test.pdf: ValidationException"
timestamp: 2026-05-07T14:47:10
```
Likely triggered by eval/test suite runs. The model returned an error during PDF parsing via Converse API.

**6. Keepalive / Signature Expired (2x)**
```
logger: eagle.strands_agent
msg: "keepalive_ping: us.anthropic.claude-sonnet-4-6 FAILED: InvalidSignatureException... Signature expired"
timestamp: 2026-05-07T21:02:56
```
AWS SigV4 signature clock skew. The container's cached credentials expired between signature generation and API call. Circuit breaker was notified.

**7. S3 Vectors SSL Certificate Failure (1x)**
```
logger: eagle.knowledge_tools
msg: "exec_semantic_search: S3 Vectors query failed: SSL validation failed... CERTIFICATE_VERIFY_FAILED"
timestamp: 2026-05-07T20:54:25
```
Intermittent SSL handshake failure with the S3 Vectors endpoint. Semantic search gracefully returned empty results.

**8. AccessDeniedException on web_search (1x)**
```
logger: eagle.web_search
msg: "web_search ClientError [AccessDeniedException]: Not authorized to call Converse"
timestamp: 2026-05-07T14:47:31
```
Likely triggered by eval/test suite. IAM role may lack `bedrock:InvokeModel` for the model used by web_search.

### Langfuse Trace Errors

| Metric | Value |
|--------|-------|
| Total traces | 14 |
| Successful | 7 |
| Error traces | 0 |
| Orphan traces (filtered) | 7 |
| Avg latency | 76 ms |
| Total cost | $5.0517 |
| Unique users | 2 |

No error-level traces detected. The 7 orphan traces (client disconnect before span close) were correctly filtered as noise per known patterns.

## Cross-Reference Analysis

### Session Correlation Map

No cross-source correlations found. With zero DynamoDB feedback items and zero Langfuse error traces, cross-referencing is limited to CloudWatch-internal session analysis.

| Session ID | Source | Error Count | Details |
|------------|--------|-------------|---------|
| `9867fbe5-0835-4574-b455-8769ba604593` | CloudWatch only | 7 | 6x batch doc gen failures + 1x Float/Decimal create_document error |
| `5875c925-287e-46db-b84f-fb97ae710bd0` | CloudWatch only | 7 | OTel detach context (noise) |

### Error Pattern Clusters

| Cluster | CloudWatch Signal | Langfuse Signal | Feedback Signal | Verdict |
|---------|------------------|-----------------|-----------------|---------|
| **Document Generation** | 7 errors (Float/Decimal + batch failures) | None | None | Application bug — P2 |
| **Knowledge Search Quality** | 6 JSON parse warnings | None | None | LLM output reliability — P2 |
| **Document Schema Gaps** | ~15 validation warnings | None | None | Schema incomplete — P2 |
| **Bedrock Parser** | 3 ValidationException errors | None | None | Test-triggered — P2 |
| **Infra/Auth** | 4 (signature, SSL, AccessDenied, NoSuchKey) | None | None | Intermittent — P3 |
| **OTel Noise** | 7 detach errors | None | None | Noise (known) |

### Trend Analysis

- **No escalation trend**: Error counts are low and isolated to specific sessions/operations.
- **Document generation cluster**: All 7 errors in session `9867fbe5` occurred within a 4-minute window (20:06–20:10), suggesting a single user session that triggered batch generation with bad data.
- **Knowledge search failures**: Spread across 30 minutes (19:43–20:20), consistent with normal background query traffic hitting LLM JSON edge cases.
- **Test artifacts**: The Bedrock parser, web_search, and web_fetch errors all occurred at 14:47, coinciding with test run completion ("Saved test run... 1826 passed, 0 failed"), confirming these are eval-suite artifacts.
- **Keepalive at 21:02**: Single instance of credential clock skew, not recurring.

## Prioritized Issue List

| # | Issue | Severity | Score | Sources | Sessions | Root Cause |
|---|-------|----------|-------|---------|----------|------------|
| 1 | Document generation Float→Decimal serialization error | P2 | 3 | CW | 1 | `estimated_value` arrives as Python `float`, DynamoDB rejects it |
| 2 | Knowledge search AI ranking JSON parse failures | P2 | 2 | CW | 0 (background) | LLM returns malformed JSON from ranking prompt |
| 3 | Document schema: "FFP Task Orders" unrecognized | P2 | 2 | CW | 1 | Missing alias in `CONTRACT_TYPE_ALIASES` |
| 4 | Document schema: estimated_value string validation | P2 | 2 | CW | 1 | Non-numeric strings (currency, "TBD") fail Pydantic `float` |
| 5 | Bedrock document parser ValidationException | P2 | 2 | CW | 0 (test) | Model error during PDF Converse — may need retry/fallback |
| 6 | S3 Vectors SSL certificate failure | P3 | 0 | CW | 0 | Intermittent SSL handshake — already has graceful fallback |
| 7 | AccessDeniedException on web_search | P3 | 1 | CW | 0 (test) | IAM role may lack Bedrock access for web_search model |
| 8 | Keepalive InvalidSignatureException | P3 | 1 | CW | 0 | Credential clock skew — circuit breaker handled it |

## Noise Report

| Item | Count | Justification |
|------|-------|---------------|
| OTel "Failed to detach context" | 7 | Known OpenTelemetry async context handling — spans nest via Langfuse parent wrapper. Documented as noise in known patterns. |
| Orphan stream traces (Langfuse) | 7 | Client disconnect before span close — `eagle-stream-*` name, no sessionId, cost=0, output=null. Standard pattern. |
| web_fetch DNS failure (wind.example.com) | 1 | Test fixture — example.com domain confirms eval/test origin. |
| web_search timeout ("slow query") | 1 | Test fixture — coincides with test run at 14:47. |
| S3 NoSuchKey for package content | 1 | Missing document version for test package PKG-2026-0042 — test data cleanup artifact. |
| DeprecationWarning (datetime.utcnow) | 0 | Not observed in this window (previously common). |
