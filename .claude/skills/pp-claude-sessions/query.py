"""pp-claude-sessions — Printing-Press-shaped CLI for Claude Code session JSONLs.

Read-only query interface over a directory of scrubbed `*.jsonl` session files
(typically `session-history/jsonl/` inside a claude-handoff bundle, but works on
any `~/.claude/projects/<encoded>/` dir too).

Stdlib-only. Python 3.10+.

Shape mirrors the printing-press CLI conventions:
- subcommand-first
- `--agent` expands to `--json --compact --no-input --no-color --yes`
- response envelope `{"meta": {...}, "results": ...}`
- `--select` dotted-path projection
- `--deliver` sinks: stdout (default), file:<path>, webhook:<url>
- `which` discovery for natural-language capability lookup
- exit codes: 0 ok, 2 usage, 3 not found, 5 read error, 10 config
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_NOT_FOUND = 3
EXIT_READ = 5
EXIT_CONFIG = 10

DEFAULT_SRC_CANDIDATES = [
    Path("session-history/jsonl"),
    Path("./jsonl"),
]


# ---------- helpers ----------

def find_src(explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit)
        if not p.is_dir():
            die(EXIT_CONFIG, f"--src directory not found: {p}")
        return p
    for cand in DEFAULT_SRC_CANDIDATES:
        if cand.is_dir():
            return cand
    die(EXIT_CONFIG, "no --src given and no default session-history/jsonl dir found")


def list_jsonls(src: Path) -> list[Path]:
    return sorted(src.glob("*.jsonl"))


def iter_lines(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                yield json.loads(raw)
            except json.JSONDecodeError:
                continue


def msg_text(entry: dict[str, Any], include_tools: bool = False) -> str:
    """Extract human-readable text from a user/assistant entry.

    By default returns prose only. With include_tools=True also embeds the
    raw `input` (Bash command, Edit args, etc.) and tool_result bodies — needed
    for forensic search across what was actually executed.
    """
    msg = entry.get("message")
    if not isinstance(msg, dict):
        return ""
    content = msg.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            t = item.get("type")
            if t == "text":
                parts.append(item.get("text", ""))
            elif t == "thinking":
                continue
            elif t == "tool_use":
                name = item.get("name", "?")
                if include_tools:
                    payload = json.dumps(item.get("input", {}), ensure_ascii=False)
                    parts.append(f"[tool_use: {name}] {payload}")
                else:
                    parts.append(f"[tool_use: {name}]")
            elif t == "tool_result":
                content_inner = item.get("content", "")
                if isinstance(content_inner, list):
                    for c in content_inner:
                        if isinstance(c, dict) and "text" in c:
                            parts.append(c["text"])
                elif isinstance(content_inner, str):
                    parts.append(content_inner)
        return "\n".join(p for p in parts if p)
    return ""


def session_summary(path: Path) -> dict[str, Any]:
    """Cheap metadata for a session — read fully but minimally."""
    msg_count = 0
    user_count = 0
    asst_count = 0
    tool_count = 0
    first_user: str | None = None
    first_ts: str | None = None
    last_ts: str | None = None
    git_branch: str | None = None
    cwd: str | None = None

    for entry in iter_lines(path):
        t = entry.get("type")
        ts = entry.get("timestamp")
        if ts:
            last_ts = ts
            if first_ts is None:
                first_ts = ts
        if t == "user":
            msg_count += 1
            user_count += 1
            if first_user is None:
                text = msg_text(entry)
                if text:
                    first_user = text[:120].replace("\n", " ")
        elif t == "assistant":
            msg_count += 1
            asst_count += 1
            msg = entry.get("message") or {}
            for item in msg.get("content") or []:
                if isinstance(item, dict) and item.get("type") == "tool_use":
                    tool_count += 1
        if git_branch is None and entry.get("gitBranch"):
            git_branch = entry["gitBranch"]
        if cwd is None and entry.get("cwd"):
            cwd = entry["cwd"]

    return {
        "session_id": path.stem,
        "file": str(path),
        "messages": msg_count,
        "user_messages": user_count,
        "assistant_messages": asst_count,
        "tool_uses": tool_count,
        "first_timestamp": first_ts,
        "last_timestamp": last_ts,
        "git_branch": git_branch,
        "cwd": cwd,
        "first_user_message": first_user,
    }


# ---------- response envelope ----------

def envelope(results: Any, source: str = "local", reason: str = "") -> dict[str, Any]:
    return {
        "meta": {
            "source": source,
            "scanned_at": datetime.now(timezone.utc).isoformat(),
            "reason": reason,
        },
        "results": results,
    }


def project_select(obj: Any, paths: list[str]) -> Any:
    """Keep only dotted-path fields. Works on dicts; over a list, applies element-wise."""
    if isinstance(obj, list):
        return [project_select(x, paths) for x in obj]
    if not isinstance(obj, dict):
        return obj
    out: dict[str, Any] = {}
    for p in paths:
        head, _, rest = p.partition(".")
        if head not in obj:
            continue
        if rest:
            out[head] = project_select(obj[head], [rest])
        else:
            out[head] = obj[head]
    return out


def deliver(payload: dict[str, Any], sink: str, compact: bool) -> int:
    text = json.dumps(payload, separators=(",", ":")) if compact else json.dumps(payload, indent=2)
    if sink == "stdout":
        print(text)
        return EXIT_OK
    if sink.startswith("file:"):
        path = Path(sink[5:])
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
        return EXIT_OK
    if sink.startswith("webhook:"):
        url = sink[8:]
        ct = "application/x-ndjson" if compact else "application/json"
        req = urllib.request.Request(url, data=text.encode("utf-8"), headers={"Content-Type": ct}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                if 200 <= resp.status < 300:
                    return EXIT_OK
                print(f"webhook {url} → HTTP {resp.status}", file=sys.stderr)
                return EXIT_READ
        except urllib.error.URLError as e:
            print(f"webhook {url} → {e}", file=sys.stderr)
            return EXIT_READ
    print(f"unknown --deliver sink scheme: {sink}. supported: stdout, file:<path>, webhook:<url>", file=sys.stderr)
    return EXIT_USAGE


def die(code: int, msg: str) -> None:
    print(msg, file=sys.stderr)
    sys.exit(code)


# ---------- subcommands ----------

def cmd_list(args: argparse.Namespace) -> int:
    src = find_src(args.src)
    files = list_jsonls(src)
    if not files:
        die(EXIT_NOT_FOUND, f"no *.jsonl files in {src}")
    summaries = []
    for f in files:
        s = session_summary(f)
        if args.limit and len(summaries) >= args.limit:
            break
        summaries.append(s)
    payload = envelope(summaries, source="local", reason=f"scanned {len(files)} files in {src}")
    return finalize(payload, args)


def cmd_show(args: argparse.Namespace) -> int:
    src = find_src(args.src)
    target = src / f"{args.session_id}.jsonl"
    if not target.is_file():
        # fuzzy: try prefix match
        matches = [f for f in list_jsonls(src) if f.stem.startswith(args.session_id)]
        if len(matches) == 1:
            target = matches[0]
        elif len(matches) > 1:
            die(EXIT_USAGE, f"ambiguous session-id prefix '{args.session_id}'; matches: {[m.stem for m in matches]}")
        else:
            die(EXIT_NOT_FOUND, f"session not found: {args.session_id} (in {src})")
    msgs: list[dict[str, Any]] = []
    for entry in iter_lines(target):
        t = entry.get("type")
        if t not in {"user", "assistant"} and not args.all:
            continue
        text = msg_text(entry)
        if not text and not args.all:
            continue
        msgs.append({
            "role": t,
            "timestamp": entry.get("timestamp"),
            "uuid": entry.get("uuid"),
            "text": text,
        })
        if args.limit and len(msgs) >= args.limit:
            break
    payload = envelope({"session_id": target.stem, "messages": msgs}, source="local")
    return finalize(payload, args)


def cmd_search(args: argparse.Namespace) -> int:
    src = find_src(args.src)
    pattern = args.pattern
    try:
        rx = re.compile(pattern, re.IGNORECASE if not args.case else 0)
    except re.error as e:
        die(EXIT_USAGE, f"invalid regex: {e}")
    hits: list[dict[str, Any]] = []
    for f in list_jsonls(src):
        for entry in iter_lines(f):
            t = entry.get("type")
            if t not in {"user", "assistant"}:
                continue
            text = msg_text(entry, include_tools=args.include_tools)
            if not text:
                continue
            for m in rx.finditer(text):
                start = max(0, m.start() - args.context)
                end = min(len(text), m.end() + args.context)
                hits.append({
                    "session_id": f.stem,
                    "role": t,
                    "timestamp": entry.get("timestamp"),
                    "uuid": entry.get("uuid"),
                    "match": m.group(0),
                    "context": text[start:end],
                })
                if args.limit and len(hits) >= args.limit:
                    payload = envelope(hits, source="local", reason=f"truncated at limit {args.limit}")
                    return finalize(payload, args)
                break  # one hit per entry, full content already in `context`
    payload = envelope(hits, source="local", reason=f"{len(hits)} hits for /{pattern}/")
    return finalize(payload, args)


def cmd_tools(args: argparse.Namespace) -> int:
    src = find_src(args.src)
    counts: Counter[str] = Counter()
    per_session: dict[str, Counter[str]] = defaultdict(Counter)
    for f in list_jsonls(src):
        for entry in iter_lines(f):
            if entry.get("type") != "assistant":
                continue
            msg = entry.get("message") or {}
            for item in msg.get("content") or []:
                if isinstance(item, dict) and item.get("type") == "tool_use":
                    name = item.get("name", "?")
                    counts[name] += 1
                    per_session[f.stem][name] += 1
    results = {
        "total_tool_uses": sum(counts.values()),
        "distinct_tools": len(counts),
        "by_tool": dict(counts.most_common()),
    }
    if args.by_session:
        results["by_session"] = {sid: dict(c.most_common()) for sid, c in per_session.items()}
    return finalize(envelope(results, source="local"), args)


def cmd_stats(args: argparse.Namespace) -> int:
    src = find_src(args.src)
    files = list_jsonls(src)
    total_msgs = 0
    total_user = 0
    total_asst = 0
    total_tools = 0
    first_ts: str | None = None
    last_ts: str | None = None
    branches: Counter[str] = Counter()
    for f in files:
        s = session_summary(f)
        total_msgs += s["messages"]
        total_user += s["user_messages"]
        total_asst += s["assistant_messages"]
        total_tools += s["tool_uses"]
        if s["first_timestamp"]:
            first_ts = min(first_ts, s["first_timestamp"]) if first_ts else s["first_timestamp"]
        if s["last_timestamp"]:
            last_ts = max(last_ts, s["last_timestamp"]) if last_ts else s["last_timestamp"]
        if s["git_branch"]:
            branches[s["git_branch"]] += 1
    return finalize(envelope({
        "sessions": len(files),
        "total_messages": total_msgs,
        "user_messages": total_user,
        "assistant_messages": total_asst,
        "tool_uses": total_tools,
        "first_timestamp": first_ts,
        "last_timestamp": last_ts,
        "top_branches": dict(branches.most_common(10)),
    }, source="local"), args)


CAPABILITY_INDEX = [
    (("list", "enumerate", "all sessions", "sessions"), "list", "Enumerate all sessions with metadata"),
    (("show", "view", "open session", "read"), "show", "Pretty-print a session's messages"),
    (("search", "grep", "find text", "lookup"), "search", "Substring/regex search across all sessions"),
    (("tools", "tool use", "tool count", "which tools"), "tools", "Count tool invocations grouped by tool"),
    (("stats", "summary", "overview", "totals"), "stats", "Overall counts and date range across all sessions"),
    (("when was", "date", "timeline"), "stats", "Date range comes from `stats`"),
    (("recent", "latest"), "list", "`list` is sorted; use --limit and read from the tail"),
]


def cmd_which(args: argparse.Namespace) -> int:
    q = " ".join(args.query).lower().strip()
    if not q:
        die(EXIT_USAGE, "which: empty query")
    scored: list[tuple[int, str, str]] = []
    for keywords, cmd, desc in CAPABILITY_INDEX:
        score = sum(1 for kw in keywords if kw in q)
        if score:
            scored.append((score, cmd, desc))
    scored.sort(reverse=True)
    if not scored:
        print(json.dumps({"query": q, "matches": []}, indent=2))
        return EXIT_USAGE  # printing-press uses exit 2 for "no confident match"
    out = [{"command": c, "description": d, "score": s} for s, c, d in scored]
    print(json.dumps({"query": q, "matches": out}, indent=2))
    return EXIT_OK


def cmd_doctor(args: argparse.Namespace) -> int:
    checks: list[dict[str, Any]] = []
    py = sys.version_info
    checks.append({"check": "python>=3.10", "ok": py >= (3, 10), "value": f"{py.major}.{py.minor}.{py.micro}"})
    try:
        src = find_src(args.src)
        files = list_jsonls(src)
        checks.append({"check": "src dir found", "ok": True, "value": str(src)})
        checks.append({"check": "jsonl files present", "ok": bool(files), "value": len(files)})
        if files:
            first = files[0]
            try:
                # try reading a few lines
                count = sum(1 for _ in iter_lines(first))
                checks.append({"check": "first file parseable", "ok": count > 0, "value": f"{count} entries"})
            except Exception as e:
                checks.append({"check": "first file parseable", "ok": False, "value": str(e)})
    except SystemExit:
        checks.append({"check": "src dir found", "ok": False, "value": "no default dir; pass --src"})
    all_ok = all(c["ok"] for c in checks)
    return finalize(envelope({"all_ok": all_ok, "checks": checks}, source="local"), args)


def cmd_feedback(args: argparse.Namespace) -> int:
    home = Path.home() / ".pp-claude-sessions"
    home.mkdir(exist_ok=True)
    log = home / "feedback.jsonl"
    if args.action == "add":
        text = args.text
        if args.stdin:
            text = sys.stdin.read().strip()
        if not text:
            die(EXIT_USAGE, "feedback: empty entry")
        entry = {"ts": datetime.now(timezone.utc).isoformat(), "note": text}
        with log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
        print(json.dumps({"stored": str(log), "entry": entry}, indent=2))
        return EXIT_OK
    if args.action == "list":
        if not log.exists():
            return finalize(envelope([], source="local", reason="no feedback yet"), args)
        entries = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines() if l.strip()]
        if args.limit:
            entries = entries[-args.limit:]
        return finalize(envelope(entries, source="local"), args)
    die(EXIT_USAGE, "feedback action must be 'add' or 'list'")
    return EXIT_USAGE  # unreachable


# ---------- finalize ----------

def finalize(payload: dict[str, Any], args: argparse.Namespace) -> int:
    if args.select:
        paths = [p.strip() for p in args.select.split(",") if p.strip()]
        # results may be a list or a dict — project both
        payload["results"] = project_select(payload["results"], paths)
    return deliver(payload, args.deliver, args.compact)


# ---------- argparse ----------

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="pp-claude-sessions",
        description="Read-only CLI for Claude Code session JSONLs (printing-press shape).",
    )
    ap.add_argument("--version", action="version", version="pp-claude-sessions 0.1.0")
    ap.add_argument("--src", help="Directory containing *.jsonl session files (default: ./session-history/jsonl/)")
    # printing-press style global flags
    ap.add_argument("--agent", action="store_true", help="Expand to --json --compact --no-input --no-color --yes")
    ap.add_argument("--json", action="store_true", help="Output JSON (default; here for compat)")
    ap.add_argument("--compact", action="store_true", help="Compact JSON (one line, no indent)")
    ap.add_argument("--no-color", action="store_true", help="Disable color (no-op; reserved)")
    ap.add_argument("--no-input", action="store_true", help="Refuse to prompt (no-op; this CLI never prompts)")
    ap.add_argument("--yes", action="store_true", help="Auto-confirm (no-op; reserved)")
    ap.add_argument("--select", help="Comma-separated dotted paths to keep in `results`")
    ap.add_argument("--deliver", default="stdout", help="Output sink: stdout | file:<path> | webhook:<url>")
    ap.add_argument("--dry-run", action="store_true", help="Show what would run without doing it")

    sub = ap.add_subparsers(dest="cmd", required=False)

    p_list = sub.add_parser("list", help="Enumerate sessions with metadata")
    p_list.add_argument("--limit", type=int, default=0)

    p_show = sub.add_parser("show", help="Pretty-print a session")
    p_show.add_argument("session_id", help="Full session UUID or unique prefix")
    p_show.add_argument("--all", action="store_true", help="Include non user/assistant entries")
    p_show.add_argument("--limit", type=int, default=0)

    p_search = sub.add_parser("search", help="Regex/substring search across all sessions")
    p_search.add_argument("pattern")
    p_search.add_argument("--case", action="store_true", help="Case-sensitive (default: insensitive)")
    p_search.add_argument("--context", type=int, default=80, help="Chars of context around each match")
    p_search.add_argument("--limit", type=int, default=0)
    p_search.add_argument("--include-tools", action="store_true", help="Search inside tool_use inputs (Bash commands, Edit args, etc.) — forensic mode")

    p_tools = sub.add_parser("tools", help="Count tool invocations across sessions")
    p_tools.add_argument("--by-session", action="store_true")

    sub.add_parser("stats", help="Overall counts and date range")

    p_which = sub.add_parser("which", help="Map natural-language capability to a command")
    p_which.add_argument("query", nargs="+")

    sub.add_parser("doctor", help="Verify environment + src dir is readable")

    p_fb = sub.add_parser("feedback", help="Local feedback log (add/list)")
    p_fb.add_argument("action", choices=["add", "list"])
    p_fb.add_argument("text", nargs="?", default="")
    p_fb.add_argument("--stdin", action="store_true")
    p_fb.add_argument("--limit", type=int, default=0)

    return ap


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)

    if args.agent:
        args.json = True
        args.compact = True
        args.no_color = True
        args.no_input = True
        args.yes = True

    if not args.cmd:
        ap.print_help(sys.stderr)
        return EXIT_USAGE

    if args.dry_run:
        plan = {"cmd": args.cmd, "args": {k: v for k, v in vars(args).items() if k not in {"cmd"}}}
        print(json.dumps(plan, indent=2))
        return EXIT_OK

    dispatch = {
        "list": cmd_list,
        "show": cmd_show,
        "search": cmd_search,
        "tools": cmd_tools,
        "stats": cmd_stats,
        "which": cmd_which,
        "doctor": cmd_doctor,
        "feedback": cmd_feedback,
    }
    handler = dispatch[args.cmd]
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
