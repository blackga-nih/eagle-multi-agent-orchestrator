"""
_remote_post_deploy_smoke.py — laptop-side driver for `just dev-smoke-deployed`.

Round-trip:
  1. Confirm the devbox EC2 is running (start if stopped).
  2. Read deployed ALB URLs from CloudFormation (EagleComputeStack outputs).
  3. SSM-sync the repo on the devbox so post_deploy_smoke.py reflects the
     harness checked into source.
  4. Stage post_deploy_smoke.py via base64-over-SSM (mirrors Q4/Q5 pattern)
     so iterating on the harness doesn't require a commit-and-push.
  5. SSM send-command: invoke `python -m tests.post_deploy_smoke
     --backend-url ... --frontend-url ... --scenario ... --upload`.
  6. Cat the JSON result back from the devbox over SSM.

Exits 0 if the smoke passed; 1 otherwise (matches the orchestrator's exit).

This is a recipe-internal utility — invoke via `just dev-smoke-deployed`.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path

import boto3

REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
DEVBOX_STACK = "eagle-ec2-dev"
COMPUTE_STACK = "EagleComputeStack"          # dev compute (default)
COMPUTE_STACK_QA = "EagleComputeStackQA"     # qa compute (when --env=qa)
REPO_DIR = "/home/ec2-user/eagle"
REMOTE_OUT = "/tmp/post_deploy_smoke.json"
REMOTE_ORCH = f"{REPO_DIR}/server/tests/post_deploy_smoke.py"


def _cfn_outputs(stack_name: str) -> dict[str, str]:
    cf = boto3.client("cloudformation", region_name=REGION)
    desc = cf.describe_stacks(StackName=stack_name)["Stacks"][0]
    return {o["OutputKey"]: o["OutputValue"] for o in desc.get("Outputs", [])}


def _devbox_instance_id() -> str:
    outs = _cfn_outputs(DEVBOX_STACK)
    return outs["InstanceId"]


def _ensure_running(iid: str) -> None:
    ec2 = boto3.client("ec2", region_name=REGION)
    state = ec2.describe_instances(InstanceIds=[iid])["Reservations"][0]["Instances"][0]["State"]["Name"]
    if state == "running":
        return
    if state != "stopped":
        sys.exit(f"Devbox is in state '{state}' — wait or fix manually.")
    print(f"Starting devbox {iid}...")
    ec2.start_instances(InstanceIds=[iid])
    ec2.get_waiter("instance_running").wait(InstanceIds=[iid])
    print("Devbox started; waiting 15s for SSM agent...")
    time.sleep(15)


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


def _print_block(title: str, body: str, max_chars: int = 4000) -> None:
    print(f"--- {title} ---")
    if not body:
        print("(empty)")
        return
    if len(body) > max_chars:
        print(body[:max_chars])
        print(f"... [{len(body) - max_chars} chars truncated]")
    else:
        print(body)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--env", default="dev", choices=["dev", "qa"])
    p.add_argument("--scenario", default="research_source_transparency")
    p.add_argument("--auth", action="store_true",
                   help="Pass --auth to the orchestrator (uses EAGLE_TEST_EMAIL/PASSWORD).")
    p.add_argument("--no-upload", action="store_true",
                   help="Skip S3 upload; useful for fast iteration.")
    p.add_argument("--out", default="/tmp/post_deploy_smoke.json",
                   help="Local path to save the result JSON pulled back from devbox.")
    p.add_argument("--timeout", type=int, default=900,
                   help="Per-step SSM timeout (seconds). Default 900s — backend "
                        "research probe + 240s frontend wait + auth round-trip.")
    args = p.parse_args()

    iid = _devbox_instance_id()
    _ensure_running(iid)

    # 1) Read deployed ALB URLs from the compute stack
    compute_stack = COMPUTE_STACK_QA if args.env == "qa" else COMPUTE_STACK
    outs = _cfn_outputs(compute_stack)
    backend_url = outs["BackendUrl"]
    frontend_url = outs["FrontendUrl"]
    print(f"=== {args.env} compute stack outputs ===")
    print(f"    backend  = {backend_url}")
    print(f"    frontend = {frontend_url}")

    # 2) git sync — pull whatever is on origin/main so the rest of the repo
    #    stays current (skill files, etc.). The orchestrator file itself is
    #    staged separately in step 3 in case we're iterating before commit.
    print("\n=== Phase 1: git sync ===")
    sync = _ssm_run(
        iid,
        [
            "set -e",
            f"cd {REPO_DIR}",
            "git fetch origin main",
            "git checkout main",
            "git reset --hard origin/main",
            "git rev-parse --short HEAD",
        ],
        "post-deploy-smoke: git sync",
        timeout=180,
    )
    _print_block("git sync stdout", sync.get("StandardOutputContent", ""))
    if sync["Status"] != "Success":
        _print_block("git sync stderr", sync.get("StandardErrorContent", ""))
        return 1

    # 3) Stage the orchestrator over SSM. base64-encoded payload.
    orch_local = Path(__file__).resolve().parent.parent / "server" / "tests" / "post_deploy_smoke.py"
    if not orch_local.exists():
        sys.exit(f"missing orchestrator: {orch_local}")
    encoded = base64.b64encode(orch_local.read_bytes()).decode()
    print(f"\n=== Phase 2: stage orchestrator ({len(encoded)} b64 chars) ===")
    stage = _ssm_run(
        iid,
        [
            f"mkdir -p {REPO_DIR}/server/tests",
            f"echo {encoded} | base64 -d > {REMOTE_ORCH}",
            f"wc -l {REMOTE_ORCH}",
        ],
        "post-deploy-smoke: stage orchestrator",
        timeout=120,
    )
    _print_block("stage stdout", stage.get("StandardOutputContent", ""))
    if stage["Status"] != "Success":
        _print_block("stage stderr", stage.get("StandardErrorContent", ""))
        return 1

    # 4) Ensure playwright is installed on the devbox (idempotent).
    print("\n=== Phase 3: ensure playwright + httpx on devbox ===")
    deps = _ssm_run(
        iid,
        [
            f"cd {REPO_DIR}/server",
            "python3 -m pip install --quiet 'httpx>=0.27' 'playwright>=1.40' boto3 2>&1 | tail -5",
            "python3 -m playwright install chromium 2>&1 | tail -5",
        ],
        "post-deploy-smoke: deps",
        timeout=600,
    )
    _print_block("deps stdout", deps.get("StandardOutputContent", ""), max_chars=2000)

    # 5) Run the smoke
    upload_flag = "" if args.no_upload else "--upload"
    auth_flag = "--auth" if args.auth else ""
    # Forward selected env vars from laptop → devbox so the orchestrator's
    # frontend sign-in step can fill credentials. We ONLY forward the names
    # we know about; never sweep the laptop env. Values are inlined into the
    # SSM command (visible in CloudTrail) — fine for dev-only test creds,
    # NEVER pass real prod creds this way.
    forward = {}
    for key in ("EAGLE_TEST_EMAIL", "EAGLE_TEST_PASSWORD", "COGNITO_CLIENT_ID"):
        v = os.environ.get(key)
        if v:
            # Single-quote escape: replace ' with '"'"'
            esc = v.replace("'", "'\"'\"'")
            forward[key] = f"'{esc}'"
    env_prefix = " ".join(f"{k}={v}" for k, v in forward.items())
    if env_prefix:
        env_prefix += " "
    cmd = (
        f"cd {REPO_DIR}/server && "
        f"AWS_DEFAULT_REGION={REGION} "
        f"{env_prefix}"
        f"python3 -m tests.post_deploy_smoke "
        f"--backend-url {backend_url} "
        f"--frontend-url {frontend_url} "
        f"--scenario {args.scenario} "
        f"--out {REMOTE_OUT} "
        f"{upload_flag} {auth_flag}"
    )
    # Don't print the full cmd — it contains the forwarded credentials.
    redacted = cmd
    for key in forward:
        redacted = redacted.replace(forward[key], "'***'")
    print(f"\n=== Phase 4: run smoke ===\n    {redacted}")
    run = _ssm_run(iid, [cmd], "post-deploy-smoke: run", timeout=args.timeout)
    _print_block("smoke stdout", run.get("StandardOutputContent", ""), max_chars=8000)
    if run.get("StandardErrorContent"):
        _print_block("smoke stderr", run["StandardErrorContent"], max_chars=2000)

    # 6) Pull JSON back
    print("\n=== Phase 5: fetch result.json ===")
    fetch = _ssm_run(iid, [f"cat {REMOTE_OUT}"], "post-deploy-smoke: fetch", timeout=60)
    if fetch["Status"] != "Success":
        _print_block("fetch stderr", fetch.get("StandardErrorContent", ""))
        return 1

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(fetch.get("StandardOutputContent", ""))
    print(f"    wrote {out_path}")

    try:
        parsed = json.loads(out_path.read_text())
    except json.JSONDecodeError:
        print("WARN: result JSON unparseable; smoke likely failed before writing.")
        return 1

    passed = parsed.get("passed", False)
    print(f"\n=== overall: {'PASS' if passed else 'FAIL'} ===")
    if parsed.get("s3_prefix"):
        print(f"    artifacts: {parsed['s3_prefix']}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
