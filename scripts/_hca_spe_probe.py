"""Targeted probe: does HCA_SPE_Approval_Thresholds_Updated.txt show up
when the prompt is *explicitly* about JEFO approval thresholds?

If YES → the file is in the index, just out-ranked on Q4's broader prompt.
        Fix: re-tag/re-chunk for better recall on IDIQ-related queries,
        or raise EAGLE-254's cap-at-8.
If NO  → the file may be missing from the index entirely, or the
        chunker is splitting it in ways that destroy semantic density.
        Fix: re-upload with restructure.

Sends N copies of a threshold-focused prompt. Reuses the SSM round-trip
pattern from _q4_determinism_probe.py. Lighter version — just dumps
sources and HCA SPE presence per run.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import boto3

REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
INSTANCE = "i-0390c06d166d18926"
DEV_ALB = "internal-EagleC-Backe-TxWVQRPzHFsO-1219239040.us-east-1.elb.amazonaws.com"

# Prompt that should hit HCA SPE if it's in the index. Specifically references
# "approval level", "$20M", "$90M", "JEFO" — exactly the thresholds the
# HCA_SPE_Approval_Thresholds_Updated.txt file documents.
THRESHOLD_PROMPT = (
    "I'm placing a $25M sole-source order on a multi-award IDIQ and need to "
    "prepare a JEFO. What's the approval authority for orders at this dollar "
    "value? Walk me through the full approval threshold table: what's the "
    "limit for CO certification, when does it escalate to the Competition "
    "Advocate, when to HCA, and when to SPE? Cite the specific dollar "
    "thresholds and any HHS Class Deviation 2026-01 (RFO) updates."
)


def ssm_run(cmds: list[str], timeout: int = 600) -> dict:
    ssm = boto3.client("ssm", region_name=REGION)
    cmd = ssm.send_command(
        InstanceIds=[INSTANCE],
        DocumentName="AWS-RunShellScript",
        Parameters={"commands": cmds, "executionTimeout": [str(timeout)]},
        TimeoutSeconds=timeout + 60,
    )
    cid = cmd["Command"]["CommandId"]
    while True:
        time.sleep(3)
        r = ssm.get_command_invocation(CommandId=cid, InstanceId=INSTANCE)
        if r["Status"] in ("Success", "Failed", "Cancelled", "TimedOut"):
            return r


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=3, help="Number of runs (default 3)")
    args = p.parse_args()

    n = args.n
    base_url = f"http://{DEV_ALB}"
    print(f"Targeted HCA SPE probe → {base_url}/api/chat × {n}")
    print(f"Prompt: {THRESHOLD_PROMPT[:160]}...")

    # Phase 1: fire N curls
    body = json.dumps({"message": THRESHOLD_PROMPT, "session_id": "hca-spe-probe"})
    payload_lit = body.replace("'", "'\\''")  # safe single-quoting

    cmds = [
        "rm -f /tmp/hca_probe_*.json",
        "echo === START ===",
    ]
    for i in range(1, n + 1):
        cmds += [
            f"echo --- run {i} ---",
            f"START=$(date +%s)",
            f"HTTP=$(curl -s -o /tmp/hca_probe_{i:02d}.json --max-time 240 "
            f"-w '%{{http_code}}' -H 'Content-Type: application/json' "
            f"-d '{payload_lit}' {base_url}/api/chat)",
            f"END=$(date +%s)",
            f"echo run={i} http=$HTTP wall=$((END-START))s "
            f"size=$(wc -c < /tmp/hca_probe_{i:02d}.json)",
        ]
    cmds += ["echo === END ==="]

    print()
    print(f"=== Phase 1: {n} sequential curls ===")
    r = ssm_run(cmds, timeout=300 * n + 60)
    print(r.get("StandardOutputContent", ""))
    if r["Status"] != "Success":
        print("STDERR:", r.get("StandardErrorContent", "")[:1000])
        return 1

    # Phase 2: per-run, dump cited sources (just the filename lines)
    print()
    print("=== Phase 2: per-run cited sources ===")
    pull_cmds = ["echo === BEGIN ==="]
    for i in range(1, n + 1):
        pull_cmds += [
            f"echo --- RUN {i:02d} ---",
            f"FN=/tmp/hca_probe_{i:02d}.json",
            f"if [ ! -f $FN ]; then echo MISSING; continue; fi",
            f"SIZE=$(wc -c < $FN)",
            f"echo size=$SIZE",
            f"if [ $SIZE -lt 200 ]; then echo BODY:; cat $FN; echo; continue; fi",
            f"echo CITED_FILES:",
            f"jq -r .response $FN 2>/dev/null | grep -oE '[A-Za-z][A-Za-z0-9_\\-]*\\.(txt|docx|md)' | sort -u",
            f"echo HCA_SPE_PRESENT:",
            f"jq -r .response $FN 2>/dev/null | grep -c 'HCA_SPE' || echo 0",
            f"echo --- end {i:02d} ---",
        ]
    pull_cmds += ["echo === END ==="]
    r = ssm_run(pull_cmds, timeout=120)
    print(r.get("StandardOutputContent", ""))
    if r["Status"] != "Success":
        print("STDERR:", r.get("StandardErrorContent", "")[:500])
    return 0


if __name__ == "__main__":
    sys.exit(main())
