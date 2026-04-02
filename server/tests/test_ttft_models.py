"""TTFT (Time To First Token) probe for all Bedrock models.

Sends a minimal converse() call to each Claude and Nova model available in
the NCI account and measures how long it takes to receive the first response.
Models that fail or exceed the TTFT budget are flagged.

Run:
  AWS_PROFILE=eagle pytest tests/test_ttft_models.py -v -s
  AWS_PROFILE=eagle pytest tests/test_ttft_models.py -v -s -k "sonnet_46"
"""

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import boto3
import pytest
from botocore.config import Config

# ── Config ───────────────────────────────────────────────────────────

REGION = os.getenv("AWS_REGION", "us-east-1")
TTFT_BUDGET = float(os.getenv("EAGLE_TTFT_TIMEOUT", "15"))

_has_aws_creds = bool(
    os.environ.get("AWS_ACCESS_KEY_ID")
    or os.environ.get("AWS_PROFILE")
    or os.environ.get("AWS_SESSION_TOKEN")
)

# All Claude and Nova models to test.
# Keys are human-friendly IDs used in test parametrization.
MODELS = {
    # Claude family
    "sonnet_46": "us.anthropic.claude-sonnet-4-6",
    "sonnet_45": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "sonnet_40": "us.anthropic.claude-sonnet-4-20250514-v1:0",
    "haiku_45": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    # Nova family
    "nova_pro": "us.amazon.nova-pro-v1:0",
    "nova_lite": "us.amazon.nova-lite-v1:0",
    "nova_micro": "us.amazon.nova-micro-v1:0",
    "nova_2_lite": "us.amazon.nova-2-lite-v1:0",
}

_client_config = Config(
    connect_timeout=5,
    read_timeout=30,
    retries={"max_attempts": 1},
)


def _probe_model(model_id: str) -> dict:
    """Send a trivial converse() and return timing + result metadata."""
    client = boto3.client(
        "bedrock-runtime",
        region_name=REGION,
        config=_client_config,
    )
    start = time.perf_counter()
    error = None
    output_text = None
    try:
        resp = client.converse(
            modelId=model_id,
            messages=[{"role": "user", "content": [{"text": "Say hello in one word."}]}],
            inferenceConfig={"maxTokens": 10},
        )
        output_text = resp["output"]["message"]["content"][0]["text"]
    except Exception as exc:
        error = str(exc)
    elapsed = time.perf_counter() - start

    return {
        "model_id": model_id,
        "elapsed_s": round(elapsed, 2),
        "output": output_text,
        "error": error,
        "within_budget": elapsed <= TTFT_BUDGET,
    }


# ── Individual model tests ──────────────────────────────────────────


@pytest.mark.skipif(not _has_aws_creds, reason="AWS credentials required")
@pytest.mark.parametrize("model_name,model_id", list(MODELS.items()), ids=list(MODELS.keys()))
def test_ttft_individual(model_name, model_id):
    """Each model must respond within the TTFT budget with no errors."""
    result = _probe_model(model_id)

    # Print result for -s output
    status = "OK" if not result["error"] else "FAIL"
    print(f"\n  {model_name:15s} ({model_id})")
    print(f"    Status:  {status}")
    print(f"    TTFT:    {result['elapsed_s']}s (budget: {TTFT_BUDGET}s)")
    if result["output"]:
        print(f"    Output:  {result['output'][:80]}")
    if result["error"]:
        print(f"    Error:   {result['error'][:200]}")

    assert result["error"] is None, (
        f"{model_name} ({model_id}) returned error: {result['error'][:300]}"
    )
    assert result["within_budget"], (
        f"{model_name} ({model_id}) TTFT {result['elapsed_s']}s exceeds budget {TTFT_BUDGET}s"
    )


# ── Parallel sweep (all models at once) ─────────────────────────────


@pytest.mark.skipif(not _has_aws_creds, reason="AWS credentials required")
def test_ttft_all_models_parallel():
    """Probe all models in parallel and report a summary table."""
    results = {}
    with ThreadPoolExecutor(max_workers=len(MODELS), thread_name_prefix="ttft") as pool:
        futures = {
            pool.submit(_probe_model, model_id): name
            for name, model_id in MODELS.items()
        }
        for future in as_completed(futures):
            name = futures[future]
            results[name] = future.result()

    # Print summary table
    print("\n" + "=" * 80)
    print(f"  TTFT Probe Summary — budget: {TTFT_BUDGET}s")
    print("=" * 80)
    print(f"  {'Model':<15s} {'Model ID':<50s} {'TTFT':>6s}  {'Status'}")
    print(f"  {'-'*15} {'-'*50} {'-'*6}  {'-'*10}")

    failures = []
    for name in MODELS:
        r = results[name]
        status = "OK" if not r["error"] and r["within_budget"] else "FAIL"
        flag = "" if status == "OK" else " <<<"
        print(f"  {name:<15s} {r['model_id']:<50s} {r['elapsed_s']:>5.1f}s  {status}{flag}")
        if r["error"]:
            print(f"  {'':>15s} error: {r['error'][:120]}")
        if status == "FAIL":
            failures.append(name)

    print("=" * 80)
    ok_count = len(MODELS) - len(failures)
    print(f"  {ok_count}/{len(MODELS)} models passed")
    if failures:
        print(f"  FAILED: {', '.join(failures)}")
    print("=" * 80)

    assert not failures, (
        f"{len(failures)} model(s) failed TTFT probe: {', '.join(failures)}"
    )
