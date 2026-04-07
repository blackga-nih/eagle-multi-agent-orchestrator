"""Test prompt caching: send 2 queries back-to-back, measure cache_read tokens.

Query 1 should show cache_creation > 0, cache_read = 0 (cold start).
Query 2 (same session) should show cache_read > 0 (warm hit).
Then query Langfuse to confirm observations match.
"""
import asyncio
import json
import sys
import time
import uuid

import httpx

sys.stdout.reconfigure(encoding="utf-8")

SERVER = "http://localhost:8000"
TENANT = "dev-tenant"

QUERIES = [
    "What is the simplified acquisition threshold under FAC 2025-06?",
    "What about the micro-purchase threshold?",
]


async def send_query(client: httpx.AsyncClient, session_id: str, message: str, label: str):
    """Send a chat query and capture usage/cache stats."""
    print(f"\n{'='*70}")
    print(f"{label}: {message}")
    print(f"Session: {session_id}")
    print(f"{'='*70}")

    start = time.time()
    resp = await client.post(
        f"{SERVER}/api/chat",
        json={"message": message, "session_id": session_id},
        headers={
            "X-User-Id": "cache-test",
            "X-Tenant-Id": TENANT,
            "X-User-Email": "cache-test@eval.test",
            "X-User-Tier": "advanced",
        },
        timeout=120.0,
    )
    elapsed = time.time() - start
    data = resp.json()

    usage = data.get("usage", {})
    model = data.get("model", "unknown")
    response = data.get("response", "")
    tools = data.get("tools_called", [])

    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    cache_create = usage.get("cache_creation_input_tokens", 0)
    cache_read = usage.get("cache_read_input_tokens", 0)

    # Also check nested cache_creation structure
    cache_creation_detail = usage.get("cache_creation", {})
    ephemeral_5m = cache_creation_detail.get("ephemeral_5m_input_tokens", 0)
    ephemeral_1h = cache_creation_detail.get("ephemeral_1h_input_tokens", 0)

    print(f"\nCompleted in {elapsed:.1f}s | Model: {model}")
    print(f"Tools: {tools}")
    print(f"Response: {len(response):,} chars")
    print()
    print(f"  Token Usage:")
    print(f"    input_tokens:                {input_tokens:>8,}")
    print(f"    output_tokens:               {output_tokens:>8,}")
    print(f"    cache_creation_input_tokens: {cache_create:>8,}")
    print(f"    cache_read_input_tokens:     {cache_read:>8,}")
    print(f"    ephemeral_5m_input_tokens:   {ephemeral_5m:>8,}")
    print(f"    ephemeral_1h_input_tokens:   {ephemeral_1h:>8,}")

    return {
        "label": label,
        "elapsed_s": round(elapsed, 1),
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_creation_input_tokens": cache_create,
        "cache_read_input_tokens": cache_read,
        "ephemeral_5m": ephemeral_5m,
        "ephemeral_1h": ephemeral_1h,
        "tools": tools,
        "response_chars": len(response),
        "full_usage": usage,
    }


async def main():
    print("EAGLE Prompt Cache Verification Test")
    print(f"Server: {SERVER}")
    print(f"Tenant: {TENANT}")
    print()

    # Check server health
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(f"{SERVER}/api/health", timeout=5)
            h = r.json()
            print(f"Server OK: {h.get('service')} {h.get('version')}")
        except Exception as e:
            print(f"Server not reachable: {e}")
            sys.exit(1)

    # Use same session for both queries so conversation context grows
    session_id = str(uuid.uuid4())
    results = []

    async with httpx.AsyncClient() as client:
        for i, query in enumerate(QUERIES):
            label = f"Query {i+1} ({'COLD - expect cache_creation > 0' if i == 0 else 'WARM - expect cache_read > 0'})"
            result = await send_query(client, session_id, query, label)
            results.append(result)

    # ── Summary ──
    print(f"\n{'='*70}")
    print("CACHE VERIFICATION SUMMARY")
    print(f"{'='*70}")
    print(f"{'Query':<8} {'Input':>8} {'CacheCreate':>12} {'CacheRead':>10} {'Output':>8} {'Time':>6}")
    print("-" * 60)
    for r in results:
        print(
            f"{r['label'][:7]:<8} "
            f"{r['input_tokens']:>8,} "
            f"{r['cache_creation_input_tokens']:>12,} "
            f"{r['cache_read_input_tokens']:>10,} "
            f"{r['output_tokens']:>8,} "
            f"{r['elapsed_s']:>5.1f}s"
        )

    # ── Verdict ──
    print()
    q1 = results[0]
    q2 = results[1]

    cache_create_ok = q1["cache_creation_input_tokens"] > 0
    cache_read_ok = q2["cache_read_input_tokens"] > 0

    if cache_create_ok and cache_read_ok:
        saved_tokens = q2["cache_read_input_tokens"]
        # Cache reads are billed at 10% of normal input rate
        savings_pct = round(saved_tokens / (saved_tokens + q2["input_tokens"]) * 90, 1) if (saved_tokens + q2["input_tokens"]) > 0 else 0
        print(f"PASS: Prompt caching is WORKING")
        print(f"  Q1 created cache: {q1['cache_creation_input_tokens']:,} tokens")
        print(f"  Q2 read from cache: {q2['cache_read_input_tokens']:,} tokens")
        print(f"  Effective cost savings on Q2: ~{savings_pct}% of cached portion")
    elif cache_create_ok and not cache_read_ok:
        print(f"PARTIAL: Cache created on Q1 ({q1['cache_creation_input_tokens']:,} tokens) but Q2 didn't read from it")
        print(f"  This may indicate the cache TTL expired between queries or model routing changed")
    elif not cache_create_ok and not cache_read_ok:
        print(f"FAIL: No caching detected on either query")
        print(f"  cache_creation_input_tokens = 0 on both calls")
        print(f"  Check that CacheConfig is enabled and Bedrock supports caching for this model")
    else:
        print(f"UNEXPECTED: cache_read > 0 on Q1 (prior session may have primed cache)")

    # ── Check Langfuse ──
    print(f"\n{'='*70}")
    print("LANGFUSE VERIFICATION")
    print(f"{'='*70}")
    try:
        import os
        host = os.getenv("LANGFUSE_HOST", "https://us.cloud.langfuse.com")
        pk = os.getenv("LANGFUSE_PUBLIC_KEY", "pk-lf-47021a72-2b4e-4c38-8421-6ab06aef0f5c")
        sk = os.getenv("LANGFUSE_SECRET_KEY", "sk-lf-dbad2023-eede-420c-82e6-2ddec00fb7bb")

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{host}/api/public/observations",
                auth=(pk, sk),
                params={"limit": 5, "type": "GENERATION"},
                timeout=30,
            )
            obs = resp.json().get("data", [])
            print(f"Latest {len(obs)} Langfuse generations:")
            for o in obs[:5]:
                ts = (o.get("startTime") or "?")[:19]
                usage = o.get("usage", {}) or {}
                ud = o.get("usageDetails", {}) or {}
                inp = usage.get("input", 0) or 0
                cr = ud.get("cacheReadInputTokens", 0) or 0
                cw = ud.get("cacheWriteInputTokens", 0) or 0
                print(f"  {ts} | in={inp:>8,} | cache_write={cw:>8,} | cache_read={cr:>8,}")
    except Exception as e:
        print(f"  Langfuse check failed: {e}")

    # Save results
    out_path = "scripts/prompt_cache_test_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
