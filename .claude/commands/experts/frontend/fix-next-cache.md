---
type: expert-file
file-type: command
domain: frontend
tags: [expert, frontend, nextjs, cache, fix, dev-server]
description: "Fix stale .next cache issues — kills zombie Next.js processes, clears locked trace files, and restarts the dev server cleanly."
---

# Fix .next Cache Issues

When the Next.js dev server fails with `EPERM: operation not permitted, open '.next/trace'` or returns HTTP 500, stale node processes are holding locks on `.next/` files.

## Steps

1. **Find stale Next.js processes** — look for `next dev`, `start-server.js`, `next-devtools-mcp`:

```bash
# In the client/ directory
tasklist 2>/dev/null | grep node
```

Then identify which are Next.js (not Claude Code):

```bash
for pid in $(tasklist 2>/dev/null | grep node | awk '{print $2}'); do
  cmd=$(wmic process where "processid=$pid" get commandline 2>/dev/null | grep -i next | head -1)
  if [ -n "$cmd" ]; then echo "KILL PID $pid — $cmd"; fi
done
```

2. **Kill the stale Next.js processes**:

```bash
# Use MSYS_NO_PATHCONV=1 to prevent Git Bash from mangling /F /PID flags
MSYS_NO_PATHCONV=1 taskkill /F /PID <pid>
```

3. **Clear the locked file** — usually `.next/trace`:

```bash
# Wait a moment for file handles to release
sleep 2
# Try rename first (safer than delete)
mv .next/trace .next/trace.old 2>/dev/null
# If that fails, the whole directory:
mv .next .next-bak-$(date +%s) 2>/dev/null
```

4. **Restart**:

```bash
cd /c/Users/blackga/Desktop/eagle/sm_eagle && just dev-frontend
# Or for both backend + frontend:
just dev-local
```

## Automated Version

Run this to do all steps automatically:

```bash
cd /c/Users/blackga/Desktop/eagle/sm_eagle/client

# 1. Find and kill stale Next.js node processes
for pid in $(tasklist 2>/dev/null | grep node | awk '{print $2}'); do
  is_next=$(wmic process where "processid=$pid" get commandline 2>/dev/null | grep -ic next)
  is_claude=$(wmic process where "processid=$pid" get commandline 2>/dev/null | grep -ic claude)
  if [ "$is_next" -gt 0 ] && [ "$is_claude" -eq 0 ]; then
    echo "Killing stale Next.js process PID $pid"
    MSYS_NO_PATHCONV=1 taskkill /F /PID $pid 2>/dev/null
  fi
done

# 2. Wait for file handles to release
sleep 3

# 3. Clear locked trace file
mv .next/trace .next/trace.old 2>/dev/null

# 4. Restart
cd /c/Users/blackga/Desktop/eagle/sm_eagle && just dev-frontend
```

## Root Cause

The `.next/trace` file is a write stream opened by Next.js at startup. When the dev server crashes or is killed without cleanup, the file handle leaks and Windows keeps it locked until the owning process is fully terminated. The `just dev-frontend` recipe kills processes by port (`netstat` + `taskkill`), but sometimes the Next.js worker processes spawn on random ports and escape cleanup.

## Key Gotcha: Git Bash + taskkill

On Git Bash (MSYS2), `taskkill /F /PID 1234` fails because MSYS converts `/F` to a file path. Always prefix with:

```bash
MSYS_NO_PATHCONV=1 taskkill /F /PID <pid>
```
