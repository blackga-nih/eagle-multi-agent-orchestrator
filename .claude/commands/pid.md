---
description: "Use when managing local dev processes — find what's on ports 3000/8000, kill stuck processes, restart services. Trigger keywords: port in use, kill process, restart server, PID."
allowed-tools: Bash
argument-hint: "[status|kill <port>|restart <service>]"
---

# PID Manager

Manage local development processes — find, kill, and restart services on specific ports.

## Instructions

When the user invokes `/pid`, perform the requested action. If no specific action is given, default to `status`.

### Actions

**status** (default) — Show what's running on EAGLE dev ports:
```bash
netstat -ano | grep -E ':3000|:3001|:3002|:8000|:8003|:8080' | grep LISTENING
```
Then for each PID found, identify the process:
```bash
tasklist //FI "PID eq <pid>" //FO TABLE //NH
```
Report a table: `| Port | PID | Process | Status |`

**kill <port|all>** — Kill the process on a specific port, or all EAGLE dev ports:
- Find the PID: `netstat -ano | grep ':<port>' | grep LISTENING`
- Kill it: `taskkill //F //PID <pid>`
- If `all`, kill processes on ports 3000, 3001, 3002, 8000, 8003, 8080
- After killing, clean up stale lock files:
  - `cmd //c "del /f C:\\Users\\blackga\\Desktop\\eagle\\sm_eagle\\client\\.next\\trace"` (if Next.js was killed)
  - Wait 2 seconds before restarting anything

**start <frontend|backend|both>** — Start EAGLE dev servers:
- **frontend**: `cd C:/Users/blackga/Desktop/eagle/sm_eagle/client && npm run dev` (background, timeout 600s)
- **backend**: `cd C:/Users/blackga/Desktop/eagle/sm_eagle/server && AWS_PROFILE=eagle python -m uvicorn app.main:app --reload --port 8000` (background, timeout 600s)
- **both**: Start both in parallel

**restart <frontend|backend|both>** — Kill then start. Always:
1. Kill the relevant port(s) first
2. Clean stale files (`.next/trace` for frontend)
3. Wait 2 seconds
4. Start fresh

**free <port>** — Kill whatever is on that specific port (any port number).

### Port Map
| Service | Default Port |
|---------|-------------|
| Next.js frontend | 3000 |
| FastAPI backend | 8000 |
| FastAPI backend (alt) | 8003 |

### Rules
- Always use `taskkill //F //PID` (double slashes for MINGW bash)
- Always use `cmd //c "del /f ..."` for Windows file locks
- Use `run_in_background` for start commands with 600s timeout
- Report results clearly — what was killed, what was started, on which port
- If a port has multiple PIDs (e.g. parent + child), kill all of them

$ARGUMENTS
