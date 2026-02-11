# Plan: Deploy NCI-EAGLE to AWS Lightsail Container Service

## Context
Deploy the EAGLE Next.js + FastAPI app as a public HTTPS service on AWS Lightsail Container Service. The app currently runs locally with `docker-compose.dev.yml`. Lightsail gives us a public URL with managed TLS for ~$10/month.

## Architecture
- **Service name**: `nci-eagle`
- **Power**: `small` (0.5 vCPU, 1 GB RAM, $10/mo) — enough for both containers
- **Scale**: 1 node
- **Two containers** sharing localhost:
  - `frontend` — Next.js standalone (port 3000, public endpoint)
  - `backend` — FastAPI/uvicorn (port 8000, private, reachable via localhost)
- **Result**: `https://nci-eagle.<id>.us-east-1.cs.amazonlightsail.com`

## Why This Works Without Code Changes
- `next.config.mjs` rewrites default to `http://localhost:8000` — matches Lightsail shared-localhost model
- All Next.js API routes (`/api/invoke`, `/api/cloudwatch`) read `FASTAPI_URL` at runtime, default `http://localhost:8000`
- Backend Dockerfile CMD already uses `--host 0.0.0.0 --port 8000`
- Frontend Dockerfile already builds standalone with `HOSTNAME=0.0.0.0`
- Cognito `NEXT_PUBLIC_*` vars are baked at build time from `client/.env.local` (already correct)
- Backend loads config from env vars when no `.env` file present (correct for containers)

## Steps

### Step 1: Create Lightsail Container Service
```bash
aws lightsail create-container-service \
  --service-name nci-eagle --power small --scale 1 --region us-east-1
```
Wait ~2 min for state `READY`.

### Step 2: Build Docker Images
```bash
# Frontend (from client/ directory)
docker build -t nci-eagle-frontend:latest ./client

# Backend (from repo root, uses Dockerfile.backend)
docker build -t nci-eagle-backend:latest -f Dockerfile.backend .
```

### Step 3: Push Images to Lightsail
```bash
aws lightsail push-container-image --service-name nci-eagle --label frontend --image nci-eagle-frontend:latest
aws lightsail push-container-image --service-name nci-eagle --label backend --image nci-eagle-backend:latest
```
Each returns an image ref like `:nci-eagle.frontend.1` — used in deployment JSON.

### Step 4: Create Deployment
Create `scripts/lightsail-deployment.json` with:
- **backend container**: image ref, env vars (USE_BEDROCK=true, AWS creds, Cognito config, table names), port 8000
- **frontend container**: image ref, env vars (FASTAPI_URL=http://localhost:8000, Cognito config, AWS creds for CloudWatch), port 3000
- **publicEndpoint**: frontend on port 3000, health check on `/` with codes `200-399`

AWS credentials: Use existing credentials from `~/.aws/credentials` as container env vars. Both containers need them (backend for Bedrock/S3/DynamoDB/CloudWatch, frontend for CloudWatch SDK).

### Step 5: Deploy
```bash
aws lightsail create-container-service-deployment \
  --service-name nci-eagle --cli-input-json file://scripts/lightsail-deployment.json
```
Poll until state `ACTIVE` (~3-5 min).

### Step 6: Create Deploy Script
Create `scripts/deploy-lightsail.sh` that automates steps 2-5 with flags:
- `--create` — first-time service creation
- `--deploy` — build, push, deploy
- `--status` — check current state + URL
- `--logs` — fetch container logs

## Files Created/Modified

| File | Action |
|------|--------|
| `scripts/deploy-lightsail.sh` | New — deployment automation script |
| `scripts/lightsail-deployment.json` | New — deployment config (secrets as env vars) |
| `.gitignore` | Add `scripts/lightsail-deployment.json` (contains secrets) |

**No application code changes needed** — existing Dockerfiles, configs, and env var defaults all align with Lightsail's shared-localhost model.

## Verification
1. `curl https://<url>/` — returns HTML (Next.js home page)
2. `curl https://<url>/api/invoke` — returns JSON (FastAPI health)
3. Open in browser — Cognito login works (HTTPS required, provided by Lightsail)
4. Login with `hoquemi@nih.gov` / `Eagle@NCI2026!` — chat functional
5. Navigate to `/admin/eval/` — eval viewer loads with test traces

## Cost
~$10-12/month total (Lightsail $10 + minimal S3/DynamoDB/CloudWatch usage)
