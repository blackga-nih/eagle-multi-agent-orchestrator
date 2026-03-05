---
description: Test the EAGLE login/auth flow — valid credentials, invalid credentials, dev mode bypass, post-login redirect
argument-hint: [url]
---

# EAGLE Login Flow Test

Test the full authentication flow: demo credentials displayed correctly, valid login succeeds and redirects, invalid login shows error, post-login state is correct.

## Variables

| Variable | Value | Description |
| -------- | ----- | ----------- |
| SKILL | `claude-bowser` | Uses your real Chrome |
| MODE | `headed` | Visible browser |
| URL | `{PROMPT}` or `http://localhost:3000` | Base URL |

If {PROMPT} contains a URL use it, otherwise default to `http://localhost:3000`.

## Workflow

### Phase 1: Load Login Page

1. Navigate to `{URL}/login`
2. Wait up to 10 seconds for the page to load
3. Take a screenshot — save as `login-initial.png`
4. Verify the login page loaded. Look for:
   - EAGLE logo (dark blue "E" in a gradient box)
   - Email input field (placeholder: "you@nih.gov")
   - Password input field
   - "Sign in" button
5. If already redirected away from `/login` (auto-authenticated in dev mode), note it and skip to Phase 4

### Phase 2: Verify Demo Credentials Panel

6. Look for the "Demo Credentials" section at the bottom of the card
7. Verify it shows **two** credential rows:
   - **Standard User**: `testuser@example.com` / `EagleTest2024!` — labeled "basic tier"
   - **Admin User**: `admin@example.com` / `EagleAdmin2024!` — labeled "premium tier"
8. Take a screenshot — save as `login-demo-creds.png`

### Phase 3: Test Invalid Credentials

9. Click the email field and type `invalid@example.com`
10. Click the password field and type `WrongPassword123`
11. Click the "Sign in" button
12. Wait up to 5 seconds for a response
13. Take a screenshot — save as `login-invalid.png`
14. Verify an error banner appears (red background) with an error message
15. Verify the user is **not** redirected away from `/login`

### Phase 4: Clear Fields and Log In with Valid Credentials

16. Clear both fields (select all + delete or use fill)
17. Fill email with `testuser@example.com`
18. Fill password with `EagleTest2024!`
19. Take a screenshot before submitting — save as `login-before-submit.png`
20. Click the "Sign in" button
21. Watch for:
    - Spinner on the button ("Signing in...")
    - Both fields become disabled during submission

### Phase 5: Verify Post-Login State

22. Wait up to 10 seconds for redirect to complete
23. Take a screenshot — save as `login-post-auth.png`
24. Verify the user has been redirected to `/` or `/chat` (NOT still on `/login`)
25. Verify the EAGLE chat UI is visible (sidebar with "New Chat" button, input textarea)
26. Verify the user identity is shown somewhere in the sidebar (user avatar, tier badge, or email)
27. Check for no error banners or auth failure messages

### Phase 6: Verify Session Persistence

28. Navigate back to `{URL}/login`
29. Wait up to 5 seconds
30. Verify the browser **redirects away from `/login`** automatically (already authenticated)
31. Take a screenshot — save as `login-session-persist.png`

### Phase 7: Report Results

Report **PASS** or **FAIL** for each check:

| Check | Expected | Actual | Result |
|-------|----------|--------|--------|
| Login page loaded | Form visible with email + password fields | | |
| Demo credentials shown | Both users with emails, passwords, tier labels | | |
| Invalid login error | Red error banner, stays on /login | | |
| Valid login spinner | Button shows "Signing in..." + fields disabled | | |
| Post-login redirect | Redirected to /chat or / (not /login) | | |
| Chat UI visible | Sidebar + input textarea present | | |
| User identity shown | Avatar, tier, or email visible | | |
| Session persistence | /login auto-redirects when already authenticated | | |

**Overall result**: PASS only if ALL checks pass.

If any check fails, include:
- Exact error message shown (if any)
- URL the browser ended up on
- Any console errors visible
- Whether the spinner appeared before redirect
