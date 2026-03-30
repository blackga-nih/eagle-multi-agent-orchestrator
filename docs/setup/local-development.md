# Checklist A: Local Development

Run the full stack on your laptop using Docker Compose. No cloud account required for the app itself — you only need AWS credentials for DynamoDB session storage and optionally Bedrock.

## A0 — Prerequisites

- [ ] **Docker Desktop** installed and running
- [ ] **Python 3.11+** and **Node.js 20+**
- [ ] **`just`** task runner: `cargo install just` or `brew install just` or `winget install just`
- [ ] **Playwright Chromium**: `cd client && npx playwright install chromium`

## A1 — Configure Environment

```bash
cp .env.example .env
```

Minimum settings for local dev (edit `.env`):

```bash
ANTHROPIC_API_KEY=sk-ant-...       # Direct Anthropic API (no Bedrock needed)
USE_BEDROCK=false
DEV_MODE=true                       # Skips Cognito auth — use for local only
REQUIRE_AUTH=false
EAGLE_SESSIONS_TABLE=eagle          # Still needs AWS credentials for DynamoDB
AWS_DEFAULT_REGION=us-east-1
```

> **DynamoDB note**: Session storage still uses the real `eagle` DynamoDB table.
> Set `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` in `.env`, or configure `aws configure`.

### Using AWS SSO for Bedrock

If you're using AWS SSO (Single Sign-On) for credentials, you can mount your AWS credentials directory into the Docker container:

1. **Login to AWS SSO:**
   ```bash
   aws sso login --profile <your-profile>
   ```

2. **Verify credentials work:**
   ```bash
   just check-sso
   ```

3. **Start the stack with SSO:**
   ```bash
   # Uses default AWS profile
   just dev-sso

   # Or specify a profile
   just dev-sso <profile-name>
   ```

   For detached mode:
   ```bash
   just dev-up-sso [profile-name]
   ```

The Docker container will mount your `~/.aws` directory (or `%USERPROFILE%\.aws` on Windows) so it can use your SSO credentials to access Bedrock and other AWS services.

> **Windows Note**: If `${HOME}/.aws` doesn't resolve correctly, set `AWS_CONFIG_DIR` environment variable:
> ```bash
> export AWS_CONFIG_DIR=C:/Users/YourUsername/.aws
> just dev-sso
> ```

## A2 — Start the Stack

```bash
just dev-up
```

This builds both containers, starts them detached, then polls `localhost:8000/health` until the backend is ready (up to 60s). You should see:

```
Backend ready (HTTP 200)
```

## A3 — Open in Browser

Open **http://localhost:3000** — you should see the EAGLE landing page with a green **"Connected"** indicator in the top-right header. That indicator only appears when the frontend successfully called the backend on startup.

## A4 — Run Tests

Start with smoke, then use case workflows:

```bash
# Full local validation gate (recommended before committing)
just validate       # L1-L5: lint → unit → CDK synth → docker stack → smoke mid (auto teardown)

# Or run individually:

# Smoke — pages load and backend is reachable (headless, fast)
just smoke          # nav + home page (~14s)
just smoke mid      # all pages including admin, documents, workflows (~22s)
just smoke full     # all pages + basic agent response check (~27s)

# E2E Use Cases — complete acquisition workflows (headed, visible browser)
just e2e intake     # describe acquisition → agent returns pathway + document list
just e2e doc        # request SOW → agent generates document structure
just e2e far        # ask FAR question → agent returns regulation reference
just e2e full       # all three workflows in sequence
```

`just e2e full` opens a Chromium window and walks through three real acquisition scenarios end-to-end — proof the AI pipeline, agent routing, and domain knowledge are all working.

## A5 — Tear Down

```bash
just dev-down
```
