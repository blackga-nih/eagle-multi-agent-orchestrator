---
title: Debug "Submit Feedback" Not Working on Dev Server
status: placeholder
created: 2026-03-27
branch: dev-greg-20260324
---

# Feedback Submit — Debug Plan

## Problem
"Submit feedback still isn't working" on deployed dev server.

## What We Know
- **Backend is healthy**: All 10 feedback POSTs in last 24h returned 200 OK, data written to DynamoDB
- **0 requests on current container** (`7488fb2537b`) since it started at ~12:20 — requests may not be reaching the backend
- Both ECS services RUNNING on commit `b6c3ffd`
- `FASTAPI_URL` set correctly in frontend container
- No feedback code changes on this branch vs main
- Duplicate routes in `main.py` + `routers/feedback.py` (both work, but should consolidate)
- OTel 401 noise only — no actionable errors in CloudWatch

## Open Questions (need user input)
1. Which feedback flow? Ctrl+J modal (general) vs thumbs up/down (per-message)?
2. What does the user see? Modal not opening? Error message? Silent fail? Success but no data in admin?
3. Browser console errors?

## TODO When We Return
- [ ] Clarify failure mode with user
- [ ] If modal not opening: check Ctrl+J conflicts, FeedbackModal render
- [ ] If auth error: check Cognito token flow in deployed frontend
- [ ] If silent fail: add client-side logging, check Next.js proxy `/api/feedback` route
- [ ] If data missing from admin: admin page only shows per-message feedback, not general — may need to add general feedback view
- [ ] Consolidate duplicate feedback routes (main.py:2126 vs routers/feedback.py)
