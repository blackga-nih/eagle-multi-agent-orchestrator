"""Scan Langfuse observations for reads of approved/agents/*.txt prompts.

Queries the public Langfuse API for all traces + observations in the given
window, then searches input/output/metadata blobs for the 10 agent-prompt
filenames that live in s3://eagle-documents-.../eagle-knowledge-base/approved/agents/.
Prints per-file hit counts broken down by observation name (tool/agent),
plus whether the reference appeared in input vs output.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*_a, **_k):
        return None


REPO = Path(__file__).resolve().parents[1]
ENV = REPO / "server" / ".env"

AGENT_FILES = [
    "00-supervisor.txt",
    "01-policy-supervisor.txt",
    "02-legal.txt",
    "03-tech.txt",
    "04-market.txt",
    "05-public.txt",
    "06-policy-librarian.txt",
    "07-policy-analyst.txt",
    "08-COMPLIANCE.txt",
    "09-FINANCIAL.txt",
]

AGENT_FOLDER_MARKER = "approved/agents/"


def parse_window(w: str) -> datetime:
    now = datetime.now(timezone.utc)
    if w == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    m = re.match(r"^(\d+)([hd])$", w)
    if not m:
        raise SystemExit(f"bad window '{w}'")
    n, u = int(m.group(1)), m.group(2)
    return now - (timedelta(hours=n) if u == "h" else timedelta(days=n))


def creds() -> tuple[str, str, str]:
    load_dotenv(ENV)
    pub = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    sec = os.getenv("LANGFUSE_SECRET_KEY", "")
    host = os.getenv("LANGFUSE_HOST", "https://us.cloud.langfuse.com")
    if not pub or not sec:
        raise SystemExit(f"missing LANGFUSE_* in {ENV}")
    return pub, sec, host


async def paged(c: httpx.AsyncClient, url: str, params: dict, headers: dict, label: str) -> list:
    out = []
    page = 1
    while True:
        p = {**params, "page": page, "limit": 100}
        r = await c.get(url, params=p, headers=headers)
        r.raise_for_status()
        j = r.json()
        data = j.get("data", [])
        if not data:
            break
        out.extend(data)
        meta = j.get("meta", {})
        tp = meta.get("totalPages", 1)
        print(f"  [{label}] page {page}/{tp} -> {len(data)} (cum={len(out)})", file=sys.stderr)
        if page >= tp or page >= 50:
            break
        page += 1
    return out


async def fetch(from_ts: str) -> tuple[list, list]:
    pub, sec, host = creds()
    auth = "Basic " + base64.b64encode(f"{pub}:{sec}".encode()).decode()
    h = {"Authorization": auth}
    async with httpx.AsyncClient(timeout=180) as c:
        traces = await paged(c, f"{host}/api/public/traces", {"fromTimestamp": from_ts}, h, "traces")
        obs = await paged(c, f"{host}/api/public/observations", {"fromStartTime": from_ts}, h, "obs")
    return traces, obs


def stringify(v) -> str:
    if v is None:
        return ""
    if isinstance(v, (dict, list)):
        try:
            return json.dumps(v, default=str)
        except Exception:
            return str(v)
    return str(v)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", default="7d", help="today | 1h | 24h | 7d | 30d")
    args = ap.parse_args()

    from_ts = parse_window(args.window).isoformat()
    print(f"Window: since {from_ts}", file=sys.stderr)

    traces, obs = asyncio.run(fetch(from_ts))
    print(f"Fetched {len(traces)} traces / {len(obs)} observations", file=sys.stderr)

    # Per-file breakdown by observation NAME and where it appeared.
    # key: filename -> { obs_name -> {"input": n, "output": n, "metadata": n} }
    per_file: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))

    # Which traces fetched/loaded each file
    file_traces: dict[str, set[str]] = defaultdict(set)

    # What tool names ever mentioned the agents/ folder
    folder_tool_names: Counter = Counter()

    for o in obs:
        inp = stringify(o.get("input"))
        out = stringify(o.get("output"))
        meta = stringify(o.get("metadata"))
        name = (o.get("name") or "<unnamed>").strip() or "<unnamed>"
        tid = o.get("traceId", "") or ""

        folder_here = False
        for f in AGENT_FILES:
            hit_in = f in inp
            hit_out = f in out
            hit_meta = f in meta
            if hit_in or hit_out or hit_meta:
                if hit_in:
                    per_file[f][name]["input"] += 1
                if hit_out:
                    per_file[f][name]["output"] += 1
                if hit_meta:
                    per_file[f][name]["metadata"] += 1
                if tid:
                    file_traces[f].add(tid)
                folder_here = True
        if folder_here or AGENT_FOLDER_MARKER in inp or AGENT_FOLDER_MARKER in out:
            folder_tool_names[name] += 1

    print("\n=== WHICH OBSERVATIONS (tool/agent names) REFERENCE AGENT PROMPT FILES ===")
    for f in AGENT_FILES:
        entries = per_file.get(f, {})
        if not entries:
            print(f"\n  {f}: NEVER referenced in input/output/metadata")
            continue
        total_traces = len(file_traces[f])
        print(f"\n  {f}  — touched in {total_traces} trace(s)")
        # Sort by total mentions desc
        rows = sorted(
            entries.items(),
            key=lambda kv: kv[1]["input"] + kv[1]["output"] + kv[1]["metadata"],
            reverse=True,
        )
        for obs_name, c in rows:
            print(
                f"    {obs_name:<40} input={c['input']:<3} output={c['output']:<3} metadata={c['metadata']:<3}"
            )

    print("\n=== Observation names that ever mention 'approved/agents/' ===")
    for name, n in folder_tool_names.most_common(30):
        print(f"  {name:<50} {n}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
