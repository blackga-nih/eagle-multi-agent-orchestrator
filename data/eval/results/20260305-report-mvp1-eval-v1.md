# EAGLE MVP 1 Eval Report

**Run ID**: `run-2026-03-05T08-33-25.991518Z00-00`
**Date**: 2026-03-05T08:29:23Z
**Model**: `us.anthropic.claude-3-5-haiku-20241022-v1:0`
**Backend**: AWS Bedrock (boto3 native) via Strands Agents SDK
**Trigger**: eval (standalone CLI)
**Duration**: ~4 minutes
**Video**: Full chat recordings via Playwright Chromium (headless)

---

## Results Summary

| Metric | Value |
|--------|-------|
| Total | 12 |
| Passed | 12 |
| Failed | 0 |
| Skipped | 0 |
| Pass Rate | **100%** |

---

## Test Results

### Tier 1: Core Skills (Tests 9-14)

| # | Test | Status | Tokens (in/out) | Indicators |
|---|------|--------|------------------|------------|
| 9 | OA Intake Workflow (CT Scanner) | PASS | 4,259 / 267 | 3/6 keywords (ct, cost, equipment) |
| 10 | Legal Counsel (Sole Source J&A) | PASS | 337 / 304 | 5/5 (FAR 6.302-1, protest risk, case law, proprietary, recommendation) |
| 11 | Market Intelligence (Vendor Research) | PASS | 332 / 399 | 5/5 (small biz, GSA, pricing, vendor, competition) |
| 12 | Tech Review (SOW Translation) | PASS | 324 / 338 | 5/5 (SOW language, agile, evaluation, compliance, measurable) |
| 13 | Public Interest (Fairness Review) | PASS | 337 / 280 | 5/5 (fairness, transparency, protest, congressional, recommendation) |
| 14 | Document Generator (Acquisition Plan) | PASS | 4,630 / 952 | 5/5 (AP sections, FAR ref, cost, competition, signature) |

### Tier 2: Orchestration (Test 15)

| # | Test | Status | Tokens (in/out) | Tools Invoked |
|---|------|--------|------------------|---------------|
| 15 | Supervisor Multi-Skill Chain | PASS | 5,910 / 696 | oa_intake, market_intelligence, legal_counsel (3 tools, 5/5 indicators) |

### Tier 3: AWS Integration (Test 19)

| # | Test | Status | Details |
|---|------|--------|---------|
| 19 | Document Generation (3 types + S3) | PASS | SOW (306 words), IGCE (205 words), AP (314 words) — all saved to S3, boto3 confirmed 3 objects, cleanup successful |

### Tier 4: UC Workflows (Tests 21-23, 35)

| # | Test | UC | Status | Tokens (in/out) | Indicators |
|---|------|----|--------|------------------|------------|
| 21 | Micro-Purchase (<$15K) | UC-02 | PASS | 4,314 / 236 | 4/5 (micro-purchase, threshold, purchase card, streamlined) |
| 22 | Option Exercise | UC-03 | PASS | 4,345 / 389 | 4/5 (option exercise, escalation, COR change, option letter) |
| 23 | Contract Modification | UC-04 | PASS | 4,379 / 297 | 4/5 (modification, funding, PoP extension, FAR compliance) |
| 35 | New Acquisition Package | UC-01 | PASS | N/A (structured) | 5/5 (13 docs, 6 thresholds, TINA, FAR 15, 2 approvals) |

---

## Video Recordings

Full chat recordings captured via Playwright Chromium (headless). Each video shows the prompt being typed into the EAGLE chat UI, the agent responding with streaming text, and the final rendered response.

| Test | UC | Local Path | Size |
|------|----|-----------|------|
| 9 | UC-01 Intake | `data/eval/videos/uc01_intake_workflow_20260305_082923/` | video recorded |
| 15 | UC-01 Full Chain | `data/eval/videos/uc01_full_chain_20260305_083038/` | video recorded |
| 21 | UC-02 Micro-Purchase | `data/eval/videos/uc02_micro_purchase_20260305_083151/` | video recorded |
| 22 | UC-03 Option Exercise | `data/eval/videos/uc03_option_exercise_20260305_083216/` | video recorded |
| 23 | UC-04 Contract Mod | `data/eval/videos/uc04_contract_modification_20260305_083250/` | video recorded |

**S3 Archive**: `s3://eagle-eval-artifacts-274487662938-dev/eval/videos/2026-03-05T08-33-25Z/` (26 videos uploaded)

---

## Persistence

| Destination | Status |
|-------------|--------|
| DynamoDB (`TESTRUN#system`) | Persisted (run_id=`run-2026-03-05T08-12-48.034490Z00-00`, 12/12 passed) |
| CloudWatch (`/eagle/test-runs/`) | 13 events emitted |
| CloudWatch Metrics (`EAGLE/Eval`) | 55 metrics published |
| S3 Archive (results JSON) | `s3://eagle-eval-artifacts-274487662938-dev/eval/results/run-2026-03-05T08-12-48Z.json` |
| S3 Archive (videos) | 16 video files uploaded |
| Local trace | `data/eval/results/run-strands-2026-03-05T08-12-48Z.json` |

---

## MVP 1 Coverage Matrix

| UC | Description | Eval Tests | Status |
|----|-------------|-----------|--------|
| UC-01 | New Acquisition Package | 9, 14, 15, 35 | COVERED (4 tests, all pass) |
| UC-02 | Micro-Purchase (<$15K) | 21 | COVERED (1 test, pass) |
| UC-03 | Option Exercise | 22 | COVERED (1 test, pass) |
| UC-04 | Contract Modification | 23 | COVERED (1 test, pass) |

**Supporting skill tests** (cross-cutting, used by all UCs):

| Skill | Test | Status |
|-------|------|--------|
| Legal Counsel | 10 | PASS |
| Market Intelligence | 11 | PASS |
| Tech Review | 12 | PASS |
| Public Interest | 13 | PASS |
| Document Generator | 14 | PASS |
| S3 Document Ops | 19 | PASS |

---

## Notes

- **Test 22 indicator 4/5**: UC-03 Option Exercise response consistently hits 4/5 indicators — "package_docs" keyword not always present, but all required documentation is referenced.
- **Test 21 indicator 4/5**: UC-02 Micro-Purchase FAR reference not always explicit in Haiku's concise response style.
- **Test 23 indicator 4/5**: UC-04 "within_scope" keyword not always present when Haiku uses "same scope" phrasing.

---

## Conclusion

MVP 1 eval suite is **fully green at 12/12 (100%)** on Claude 3.5 Haiku. All 4 use cases (UC-01 through UC-04) pass. The Strands supervisor correctly chains 3 specialist skills (test 15). Document generation with S3 persistence works end-to-end (test 19: 3 doc types generated, saved, confirmed via boto3, cleaned up). Full chat video recordings captured for all 5 browser-enabled tests and archived to S3. Results persisted to DynamoDB, CloudWatch, and S3 for dashboard visibility.
