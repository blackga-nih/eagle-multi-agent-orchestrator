"""Score baseline_{version}_results.json via Bedrock converse.

Adapts run_demo.py's scoring logic for the single-turn baseline suite.
Each question is a fresh session, so there is no multi-turn context hint.

Usage:
    python score_baseline.py --version v17
    python score_baseline.py --json scripts/baseline_v17_results.json --out scripts/baseline_v17_scores.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def parse_eagle_docs(response: str) -> list[str]:
    docs: list[str] = []
    seen = set()
    for m in re.finditer(
        r"eagle-knowledge-base/approved/([\w-]+/[\w-]+/[\w._-]+\.\w+)", response
    ):
        path = m.group(1).rstrip("`")
        if path not in seen:
            seen.add(path)
            docs.append(path)
    return docs


_SCORING_PROMPT = """You are scoring one question of an EAGLE federal-acquisition chatbot against a reference produced by the predecessor Research Optimizer (RO). Each baseline question is a fresh single-turn session with no prior context.

Question {q_num}. This is a COLD single-turn call — EAGLE has no prior session context. For any factual regulatory question, EAGLE should call at least one tool (`research`, `query_compliance_matrix`, `search_far`, etc.) BEFORE committing to specific claims.

USER QUESTION:
{user_message}

RO REFERENCE RESPONSE (gold standard):
{reference}

EAGLE RESPONSE (candidate):
{candidate}

TOOLS EAGLE CALLED: {tools_called}
(An empty list is a red flag for any question that demands specific FAR sections, dollar thresholds, case law, or regulatory claims — but acceptable for design/workflow questions like "how should a CO sequence X".)

PRE-COMPUTED SOURCE OVERLAP HINT:
- EAGLE cited {eagle_doc_count} KB docs
- RO cited {ref_doc_count} KB docs (derived from RO response body)
- Overlap: {overlap_count} shared docs ({overlap_pct:.0%} of RO)

=================================================================
SCORING RULES (read carefully — the four dimensions are INDEPENDENT)
=================================================================

Score each dimension 0-5 as an INTEGER. EAGLE can match or exceed the
reference — if EAGLE is more thorough or more actionable than the
RO reference, give it 5/5 on that dimension. Do not artificially cap scores.

**accuracy** — factual correctness ONLY. Does every specific claim hold up?
  - 5: All FAR/RFO/AA/threshold/vehicle/case claims are correct and
       verifiable. No hallucinated section numbers or invented authorities.
  - 4: Content is correct; one minor or recoverable imprecision (e.g.,
       rounded dollar figure, slightly-off date).
  - 3: Content is correct but lacks specificity (vague FAR references
       like "under FAR Part 13" without the subsection).
  - 2: At least one material factual error that a CO would flag.
  - 1: Multiple factual errors or a fabricated primary citation
       (FAR section that doesn't exist, fake case number, wrong AA
       number, invented Class Deviation).
  - 0: Fundamental wrong answer or completely fabricated.
  NOTE: "Did not call a tool" is NOT an accuracy penalty. Only score
  accuracy on the CONTENT of the claims made.

**completeness** — topic coverage vs RO AND vs what a CO needs.
  - 5: Covers everything the RO covers AND adds value beyond it.
  - 4: Covers all main aspects the RO covered; minor edges missing.
  - 3: Covers the core question; misses 1-2 meaningful sub-topics.
  - 2: Addresses the question partially; major aspects missing.
  - 1: Tangential or shallow.
  - 0: Declines the question or answers the wrong question.

**sources** — grounding quality. Did EAGLE reference primary KB sources?
  - 5: Cites specific KB files or FAR sections that match or exceed the
       RO's citations. Overlap ≥60% OR EAGLE cites equivalent alternative
       primary sources.
  - 4: Solid citation coverage; overlap 30-60% with RO.
  - 3: Some citations present; overlap 10-30% OR cites general sources
       without specific file paths.
  - 2: Few citations, mostly general.
  - 1: No citations but claims are consistent with public knowledge.
  - 0: No citations AND response contains specific claims that should
       have been grounded (FAR/AA/threshold numbers with no source).

**actionability** — can a CO use this today?
  - 5: Concrete next steps, decision tables, checklists, worked examples,
       or a complete drafted document section. Better or equal to RO.
  - 4: Clear guidance with a few specifics.
  - 3: General direction with some procedure but no concrete artifacts.
  - 2: Vague advice, mostly "consult your policy office".
  - 1: Philosophical or advisory with no forward motion.
  - 0: Asks clarifying questions when the user explicitly asked for output,
       or returns an error / no substantive content.

CROSS-DIMENSION GUARDRAILS:
  - If EAGLE's content is factually correct but uncited, accuracy can
    still be 4-5 while sources is 1-3. Do NOT drag accuracy down just
    because sources is low.
  - If EAGLE delivers BETTER actionability than the RO (e.g., adds a
    decision table the RO lacks), actionability gets 5/5 regardless
    of whether sources is weaker.
  - If EAGLE hit the output token limit and returned a graceful error
    message ("I hit the model's per-turn output limit"), score all four
    as 0-1 — a system failure masked as a response.
  - The verdict is based on TOTAL score: >16 → "EAGLE > RO",
    12-16 → "EAGLE = RO", <12 → "EAGLE < RO".

Return ONLY a JSON object (no markdown fencing):

{{
  "accuracy": 0-5,
  "completeness": 0-5,
  "sources": 0-5,
  "actionability": 0-5,
  "verdict": "EAGLE > RO" or "EAGLE = RO" or "EAGLE < RO",
  "reasoning": "3-4 sentences. Name the single biggest win and single biggest gap. Separate content quality from grounding quality explicitly."
}}"""


def _build_bedrock_client():
    import boto3
    from botocore.config import Config

    try:
        from dotenv import load_dotenv
        _env_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "..", "..", "..", "server", ".env",
        )
        if os.path.exists(_env_path):
            load_dotenv(_env_path, override=False)
    except Exception:
        pass

    region = os.environ.get("AWS_REGION", "us-east-1")
    cfg = Config(
        connect_timeout=30,
        read_timeout=180,
        retries={"max_attempts": 2, "mode": "adaptive"},
    )

    try:
        server_app_path = os.path.abspath(
            os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "..", "..", "..", "..", "server",
            )
        )
        if server_app_path not in sys.path:
            sys.path.insert(0, server_app_path)
        from app.aws_session import get_shared_session  # type: ignore
        session = get_shared_session()
        return session.client("bedrock-runtime", region_name=region, config=cfg)
    except Exception:
        import boto3
        return boto3.client("bedrock-runtime", region_name=region, config=cfg)


def score_question(bedrock_client, q_result: dict) -> dict:
    model_id = os.environ.get(
        "BASELINE_JUDGE_MODEL", "us.anthropic.claude-sonnet-4-6"
    )

    eagle_docs = set(parse_eagle_docs(q_result.get("response", "")))
    ref_docs = set(parse_eagle_docs(q_result.get("ro_response", "")))
    overlap = eagle_docs & ref_docs
    overlap_pct = len(overlap) / max(len(ref_docs), 1)

    tools_list = q_result.get("tools") or []
    tools_called_str = ", ".join(tools_list) if tools_list else "(none)"

    q_num = q_result.get("q_num", 0)

    prompt = _SCORING_PROMPT.format(
        q_num=q_num,
        user_message=q_result.get("question", "")[:2000],
        reference=q_result.get("ro_response", "")[:8000],
        candidate=q_result.get("response", "")[:8000],
        tools_called=tools_called_str,
        eagle_doc_count=len(eagle_docs),
        ref_doc_count=len(ref_docs),
        overlap_count=len(overlap),
        overlap_pct=overlap_pct,
    )

    try:
        response = bedrock_client.converse(
            modelId=model_id,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 1400, "temperature": 0},
        )
        output_text = response["output"]["message"]["content"][0]["text"].strip()

        if output_text.startswith("```"):
            output_text = re.sub(r"^```(?:json)?\s*", "", output_text)
            output_text = re.sub(r"\s*```$", "", output_text)

        try:
            data = json.loads(output_text)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", output_text, re.DOTALL)
            if not m:
                raise
            data = json.loads(m.group())

        acc = int(data.get("accuracy", 0))
        comp = int(data.get("completeness", 0))
        src = int(data.get("sources", 0))
        act = int(data.get("actionability", 0))

        return {
            "q_num": q_num,
            "acc": acc,
            "comp": comp,
            "src": src,
            "act": act,
            "total": acc + comp + src + act,
            "verdict": data.get("verdict", "EAGLE = RO"),
            "reasoning": data.get("reasoning", ""),
            "overlap_pct": round(overlap_pct, 2),
            "eagle_docs": sorted(eagle_docs),
            "ref_docs": sorted(ref_docs),
            "model": model_id,
        }
    except Exception as e:
        print(f"[score] Q{q_num} scoring failed: {e}")
        return {
            "q_num": q_num,
            "acc": 0,
            "comp": 0,
            "src": 0,
            "act": 0,
            "total": 0,
            "verdict": "scoring-failed",
            "reasoning": f"Bedrock scoring error: {e}",
            "overlap_pct": round(overlap_pct, 2),
            "eagle_docs": sorted(eagle_docs),
            "ref_docs": sorted(ref_docs),
            "model": model_id,
        }


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", help="Version label (e.g., v17)")
    parser.add_argument("--json", help="Results JSON path")
    parser.add_argument("--out", help="Output scores JSON path")
    parser.add_argument("--parallel", type=int, default=5)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent.parent.parent.parent

    if args.json:
        json_path = Path(args.json)
    elif args.version:
        json_path = repo_root / "scripts" / f"baseline_{args.version.lower()}_results.json"
    else:
        print("ERROR: pass --version or --json")
        sys.exit(1)

    if not json_path.exists():
        print(f"ERROR: {json_path} not found")
        sys.exit(1)

    if args.out:
        out_path = Path(args.out)
    elif args.version:
        out_path = repo_root / "scripts" / f"baseline_{args.version.lower()}_scores.json"
    else:
        out_path = json_path.with_name(json_path.stem.replace("_results", "_scores") + ".json")

    print(f"Reading: {json_path}")
    with open(json_path, "r", encoding="utf-8") as f:
        results = json.load(f)

    questions = [(int(k), v) for k, v in results.items() if isinstance(v, dict) and "q_num" in v]
    questions.sort(key=lambda x: x[0])
    print(f"Loaded {len(questions)} questions")

    client = _build_bedrock_client()

    loop = asyncio.get_running_loop()
    executor = ThreadPoolExecutor(max_workers=args.parallel)

    async def score_one(row: int, qr: dict):
        print(f"[score] Q{qr.get('q_num')} submitting...")
        score = await loop.run_in_executor(executor, score_question, client, qr)
        print(f"[score] Q{qr.get('q_num')}: {score['total']}/20 — {score['verdict']}")
        return row, score

    tasks = [score_one(row, qr) for row, qr in questions]
    done = await asyncio.gather(*tasks)
    executor.shutdown(wait=False)

    scores = {str(qr.get("q_num")): score for (row, score), (_, qr) in zip(done, questions)}

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(scores, f, indent=2, ensure_ascii=False)

    total = sum(s.get("total", 0) for s in scores.values())
    max_score = len(scores) * 20
    wins = sum(1 for s in scores.values() if "> RO" in s.get("verdict", ""))
    ties = sum(1 for s in scores.values() if "= RO" in s.get("verdict", ""))
    losses = sum(1 for s in scores.values() if "< RO" in s.get("verdict", ""))

    print(f"\n{'='*60}")
    print(f"TOTAL: {total}/{max_score}")
    print(f"Wins: {wins} | Ties: {ties} | Losses: {losses}")
    print(f"Scores saved: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
