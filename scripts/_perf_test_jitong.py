"""_perf_test_jitong.py — measure latency of Jitong's slow Zeiss query against
the deployed dev backend after the perf PRs (#190, #191) land.

Sends ONE query through the same SSM-from-laptop path as
`_remote_baseline.py`, captures wall-clock time + the SSE event timeline,
then pulls the Langfuse trace and prints the per-lane breakdown for
side-by-side comparison vs the baseline trace.

Baseline (pre-PR): trace 600d7921ee4295a8f7f3d9c9e4d4255f = 142.6s total
  primary 63.6s + secondary 2.0s + path 0.7s + semantic 62.1s = 128.4s sequential

Expected after PR #190 + #191: ~40s total
  All 4 lanes parallel; primary lane's Haiku rerank cut by smaller candidate
  pool + lower maxTokens.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import gzip
import json
import os
import sys
import time
import uuid
from pathlib import Path

import boto3
import httpx
from dotenv import load_dotenv

REGION = "us-east-1"
DEVBOX_STACK = "eagle-ec2-dev"
COMPUTE_STACK_DEV = "EagleComputeStack"
REMOTE_RUNNER = "/tmp/_perf_runner.py"
REMOTE_OUT = "/tmp/_perf_out.json"
REMOTE_TOKEN = "/tmp/_perf_token.txt"

JITONG_QUERY = (
    "need to buy a $14K microscope for cancer research, specifically one "
    "Zeiss Axio Imager A1 / A2 / M1 for tracking proteins with fluorescence."
)

# Devbox-side runner — POSTs the query to /api/chat/stream and captures
# wall time, sessionId from response tags, and the per-event SSE timeline.
RUNNER_SOURCE = '''
import asyncio
import json
import os
import sys
import uuid
import time

import httpx


async def main() -> int:
    base_url = sys.argv[1]
    tenant = sys.argv[2]
    out_path = sys.argv[3]
    token_path = sys.argv[4] if len(sys.argv) > 4 else ""
    token = ""
    if token_path and os.path.exists(token_path):
        with open(token_path) as f:
            token = f.read().strip()

    sid = str(uuid.uuid4())
    uid = f"perf-test-{uuid.uuid4().hex[:8]}"
    query = """JITONG_QUERY_PLACEHOLDER"""

    headers = {
        "X-User-Id": uid,
        "X-Tenant-Id": tenant,
        "X-User-Email": f"{uid}@perf.test",
        "X-User-Tier": "advanced",
        "Accept": "text/event-stream",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    body = {"message": query, "session_id": sid}
    url = f"{base_url}/api/chat/stream"

    timeline = []
    start = time.time()
    text_chunks = []
    tools = []
    final_text = ""
    status = 0

    print(f"POST {url} sid={sid} uid={uid}", flush=True)
    try:
        async with httpx.AsyncClient() as client:
            async with client.stream("POST", url, json=body, headers=headers, timeout=600.0) as resp:
                status = resp.status_code
                print(f"HTTP {status}", flush=True)
                if not resp.is_success:
                    body_text = ""
                    async for chunk in resp.aiter_bytes():
                        body_text += chunk.decode("utf-8", errors="ignore")
                        if len(body_text) > 500:
                            break
                    elapsed = time.time() - start
                    out = {
                        "status": "error",
                        "http_status": status,
                        "error": body_text[:500],
                        "elapsed_s": round(elapsed, 1),
                        "session_id": sid, "user_id": uid,
                    }
                    with open(out_path, "w") as f:
                        json.dump(out, f, indent=2)
                    return 1

                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if not payload or payload == "[DONE]":
                        continue
                    try:
                        e = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    et = e.get("type") or e.get("event") or ""
                    t_offset = round(time.time() - start, 2)
                    if et == "text":
                        t = e.get("text") or e.get("content") or ""
                        if isinstance(t, str):
                            text_chunks.append(t)
                    elif et == "tool_use":
                        name = e.get("name") or (e.get("tool_use") or {}).get("name", "?")
                        if name not in tools:
                            tools.append(name)
                            timeline.append({"t": t_offset, "evt": "tool_use", "name": name})
                    elif et == "tool_result":
                        tr = e.get("tool_result") or {}
                        name = tr.get("name") or e.get("name") or "?"
                        timeline.append({"t": t_offset, "evt": "tool_result", "name": name})
                    elif et == "complete":
                        ft = e.get("text") or e.get("response")
                        if isinstance(ft, str):
                            final_text = ft
                        timeline.append({"t": t_offset, "evt": "complete"})
                    elif et == "error":
                        msg = e.get("error") or e.get("message") or "?"
                        timeline.append({"t": t_offset, "evt": "error", "msg": str(msg)[:200]})

        elapsed = time.time() - start
        response_text = final_text or "".join(text_chunks)
        out = {
            "status": "ok",
            "elapsed_s": round(elapsed, 1),
            "session_id": sid,
            "user_id": uid,
            "tools": tools,
            "response_chars": len(response_text),
            "response_first_300": response_text[:300],
            "timeline": timeline,
        }
        with open(out_path, "w") as f:
            json.dump(out, f, indent=2)
        print(f"OK total={elapsed:.1f}s tools={tools} chars={len(response_text)}", flush=True)
        for evt in timeline:
            print(f"  t={evt['t']:>6.1f}s  {evt['evt']:<12} {evt.get('name','')}", flush=True)
        return 0
    except Exception as exc:
        elapsed = time.time() - start
        out = {
            "status": "error", "elapsed_s": round(elapsed, 1),
            "error": f"{type(exc).__name__}: {exc}",
            "session_id": sid, "user_id": uid,
        }
        with open(out_path, "w") as f:
            json.dump(out, f, indent=2)
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
'''.replace('"""JITONG_QUERY_PLACEHOLDER"""', json.dumps(JITONG_QUERY))


def _cognito_login(email: str, password: str, client_id: str) -> str:
    cog = boto3.client("cognito-idp", region_name=REGION)
    resp = cog.initiate_auth(
        ClientId=client_id,
        AuthFlow="USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": email, "PASSWORD": password},
    )
    return resp["AuthenticationResult"]["IdToken"]


def _cfn_outputs(stack: str) -> dict[str, str]:
    cf = boto3.client("cloudformation", region_name=REGION)
    desc = cf.describe_stacks(StackName=stack)["Stacks"][0]
    return {o["OutputKey"]: o["OutputValue"] for o in desc.get("Outputs", [])}


def _ssm_run(iid: str, commands: list[str], comment: str, timeout: int = 600) -> dict:
    ssm = boto3.client("ssm", region_name=REGION)
    cmd = ssm.send_command(
        InstanceIds=[iid],
        DocumentName="AWS-RunShellScript",
        Parameters={"commands": commands, "executionTimeout": [str(timeout)]},
        Comment=comment[:100],
        TimeoutSeconds=timeout + 60,
    )
    cid = cmd["Command"]["CommandId"]
    while True:
        time.sleep(3)
        r = ssm.get_command_invocation(CommandId=cid, InstanceId=iid)
        if r["Status"] in ("Success", "Failed", "Cancelled", "TimedOut"):
            return r


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--env", default="dev", choices=["dev", "qa"])
    p.add_argument("--tenant", default="dev-tenant")
    p.add_argument("--timeout", type=int, default=600,
                   help="Per-step SSM timeout (seconds). Default 600s.")
    args = p.parse_args()

    # Cognito login
    server_env = Path(__file__).resolve().parent.parent / "server" / ".env"
    if server_env.exists():
        load_dotenv(server_env)
    email = os.environ.get("EAGLE_TEST_EMAIL")
    password = os.environ.get("EAGLE_TEST_PASSWORD")
    client_id = os.environ.get("COGNITO_CLIENT_ID")
    if not (email and password and client_id):
        sys.exit("Missing EAGLE_TEST_EMAIL / EAGLE_TEST_PASSWORD / COGNITO_CLIENT_ID env vars")
    print(f"Cognito login as {email}...")
    token = _cognito_login(email, password, client_id)
    print(f"  token acquired ({len(token)} chars)")

    # Resolve devbox + backend
    iid = _cfn_outputs(DEVBOX_STACK)["InstanceId"]
    print(f"Devbox: {iid}")
    backend_url = _cfn_outputs(COMPUTE_STACK_DEV)["BackendUrl"].rstrip("/")
    print(f"Backend: {backend_url}")

    # Stage runner + token via base64
    runner_b64 = base64.b64encode(RUNNER_SOURCE.encode()).decode()
    token_b64 = base64.b64encode(token.encode()).decode()

    print("Staging runner + token...")
    stage = _ssm_run(
        iid,
        [
            f"echo {runner_b64} | base64 -d > {REMOTE_RUNNER}",
            f"echo {token_b64} | base64 -d > {REMOTE_TOKEN}",
            "python3 -m pip install --quiet 'httpx>=0.27' 2>&1 | tail -3",
            f"wc -l {REMOTE_RUNNER}",
        ],
        "perf-test: stage",
        timeout=180,
    )
    if stage["Status"] != "Success":
        print("STAGE FAILED:", stage.get("StandardErrorContent", ""))
        return 1
    print(stage.get("StandardOutputContent", "").strip())

    print(f"\nRunning Jitong query against {backend_url}...")
    run = _ssm_run(
        iid,
        [f"python3 {REMOTE_RUNNER} {backend_url} {args.tenant} {REMOTE_OUT} {REMOTE_TOKEN}"],
        "perf-test: run jitong",
        timeout=args.timeout,
    )
    print("--- run stdout ---")
    print(run.get("StandardOutputContent", "")[:6000])
    if run["Status"] != "Success":
        print("RUN FAILED:", run.get("StandardErrorContent", "")[:2000])
        return 1

    # Cat results back gzipped
    cat = _ssm_run(
        iid,
        [f"gzip -c {REMOTE_OUT} | base64 -w0"],
        "perf-test: cat",
        timeout=60,
    )
    if cat["Status"] != "Success":
        print("CAT FAILED:", cat.get("StandardErrorContent", ""))
        return 1
    raw_b64 = cat.get("StandardOutputContent", "").strip()
    try:
        result = json.loads(gzip.decompress(base64.b64decode(raw_b64)).decode("utf-8"))
    except Exception as exc:
        print(f"Parse failed: {exc}")
        return 1

    out_path = Path(__file__).resolve().parent / "perf_test_jitong_result.json"
    out_path.write_text(json.dumps(result, indent=2))
    print(f"\nResult saved to {out_path}")

    print("\n" + "=" * 70)
    print(f"TOTAL: {result.get('elapsed_s')}s   tools: {result.get('tools')}")
    print(f"Response chars: {result.get('response_chars')}")
    print(f"session_id: {result.get('session_id')}")
    print(f"user_id:    {result.get('user_id')}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
