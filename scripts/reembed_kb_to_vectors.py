"""Re-embed the EAGLE knowledge base into a managed S3 Vectors bucket.

The legacy `rh-eagle` vectors bucket is being decommissioned in favor of
per-env managed buckets (e.g. `eagle-kb-vectors-{acct}-dev`). This script
walks `eagle-documents-{acct}-{env}/eagle-knowledge-base/approved/`,
embeds every text file via Titan Embed Text v2, and writes the vectors
(plus metadata) into the new bucket's index.

Idempotent on re-runs:
  * Vector keys are stable hashes of `(s3_key, chunk_index)` so re-running
    overwrites in place rather than duplicating.

Run:
    python scripts/reembed_kb_to_vectors.py
    python scripts/reembed_kb_to_vectors.py --dry-run
    python scripts/reembed_kb_to_vectors.py --target-bucket eagle-kb-vectors-695681773636-qa --limit 10

Defaults assume:
    --profile eagle  (AWS SSO profile for NIH.NCI.CBIIT.EAGLE.NONPROD account 695681773636)
    --region us-east-1
    --source-bucket eagle-documents-{ACCOUNT_FROM_PROFILE}-dev
    --target-bucket eagle-kb-vectors-{ACCOUNT_FROM_PROFILE}-dev
    --target-index eagle-kb-approved
    --embed-model amazon.titan-embed-text-v2:0
    --embed-dim 1024
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import logging
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

LOG = logging.getLogger("reembed")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ─── Defaults ────────────────────────────────────────────────────────────────

DEFAULT_PROFILE = "eagle"
DEFAULT_REGION = "us-east-1"
DEFAULT_PREFIX = "eagle-knowledge-base/approved/"
DEFAULT_INDEX = "eagle-kb-approved"
DEFAULT_EMBED_MODEL = "amazon.titan-embed-text-v2:0"
DEFAULT_EMBED_DIM = 1024
CHUNK_SIZE = 1500  # chars
CHUNK_OVERLAP = 200  # chars
PUT_BATCH_SIZE = 100  # S3 Vectors PutVectors API limit per call (cap at 500; stay conservative)
MAX_TITAN_INPUT_CHARS = 8000  # Titan v2 inputText cap


# ─── Helpers ─────────────────────────────────────────────────────────────────


@dataclasses.dataclass
class Chunk:
    s3_key: str
    chunk_index: int
    text: str
    title: str

    def vector_key(self) -> str:
        """Stable, idempotent vector key — hash of (s3_key, chunk_index)."""
        h = hashlib.sha256(f"{self.s3_key}#{self.chunk_index}".encode()).hexdigest()
        # S3 Vectors keys must be ≤ 64 chars and [a-zA-Z0-9_-]; sha256 hex is 64.
        return h[:60]

    def metadata(self) -> dict:
        return {
            "s3_key": self.s3_key,
            "chunk_index": self.chunk_index,
            "title": self.title,
            "document_id": self.s3_key,
        }


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Fixed-size sliding-window chunker. Stops at clean boundaries when possible."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]

    chunks: list[str] = []
    pos = 0
    while pos < len(text):
        end = min(pos + size, len(text))
        chunk = text[pos:end]
        # Try to end on a paragraph or sentence boundary if we're not at EOF.
        if end < len(text):
            for sep in ("\n\n", "\n", ". "):
                idx = chunk.rfind(sep)
                if idx > size // 2:
                    chunk = chunk[: idx + len(sep)]
                    end = pos + len(chunk)
                    break
        chunks.append(chunk.strip())
        if end >= len(text):
            break
        pos = max(end - overlap, pos + 1)
    return [c for c in chunks if c]


def derive_account(profile: str) -> str:
    """Resolve AWS account number for the given SSO profile."""
    sess = boto3.Session(profile_name=profile)
    sts = sess.client("sts")
    return sts.get_caller_identity()["Account"]


# ─── S3 source iteration ─────────────────────────────────────────────────────


def iter_kb_objects(
    s3, bucket: str, prefix: str, limit: int | None = None
) -> Iterator[tuple[str, str]]:
    """Yield (s3_key, content_str) for every text object under prefix."""
    paginator = s3.get_paginator("list_objects_v2")
    count = 0
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []) or []:
            key = obj["Key"]
            # Only embed text-like content. .docx / .xlsx / .pdf require extraction
            # — out of scope for this script.
            if not key.endswith((".txt", ".md", ".content.md")):
                continue
            try:
                body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
            except ClientError as e:
                LOG.warning("get_object failed for %s: %s", key, e)
                continue
            try:
                text = body.decode("utf-8")
            except UnicodeDecodeError:
                text = body.decode("utf-8", errors="replace")
            yield key, text
            count += 1
            if limit is not None and count >= limit:
                return


# ─── Embedding ────────────────────────────────────────────────────────────────


def embed_one(bedrock, text: str, model_id: str, dimensions: int) -> list[float] | None:
    """Embed a single chunk via Titan v2. Returns None on failure."""
    if not text:
        return None
    body = json.dumps(
        {
            "inputText": text[:MAX_TITAN_INPUT_CHARS],
            "dimensions": dimensions,
            "normalize": True,
        }
    )
    try:
        resp = bedrock.invoke_model(
            modelId=model_id,
            body=body,
            contentType="application/json",
            accept="application/json",
        )
        payload = json.loads(resp["body"].read())
        return payload.get("embedding")
    except ClientError as e:
        LOG.warning("embed_one failed: %s", e)
        return None


# ─── Vector writing ──────────────────────────────────────────────────────────


def put_batch(s3v, bucket: str, index: str, batch: list[dict]) -> int:
    """PutVectors with retry. Returns count written."""
    if not batch:
        return 0
    for attempt in range(3):
        try:
            s3v.put_vectors(vectorBucketName=bucket, indexName=index, vectors=batch)
            return len(batch)
        except ClientError as e:
            wait = 2 ** attempt
            LOG.warning("put_vectors attempt %d failed: %s (retry in %ds)", attempt + 1, e, wait)
            time.sleep(wait)
    LOG.error("put_vectors gave up after 3 attempts for batch of %d", len(batch))
    return 0


# ─── Main ────────────────────────────────────────────────────────────────────


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--profile", default=DEFAULT_PROFILE)
    p.add_argument("--region", default=DEFAULT_REGION)
    p.add_argument("--source-bucket", help="default: eagle-documents-{account}-dev")
    p.add_argument("--source-prefix", default=DEFAULT_PREFIX)
    p.add_argument("--target-bucket", help="default: eagle-kb-vectors-{account}-dev")
    p.add_argument("--target-index", default=DEFAULT_INDEX)
    p.add_argument("--embed-model", default=DEFAULT_EMBED_MODEL)
    p.add_argument("--embed-dim", type=int, default=DEFAULT_EMBED_DIM)
    p.add_argument("--limit", type=int, help="Embed only N source documents (testing)")
    p.add_argument("--dry-run", action="store_true", help="Skip put_vectors writes")
    args = p.parse_args()

    sess = boto3.Session(profile_name=args.profile, region_name=args.region)
    account = derive_account(args.profile)
    LOG.info("Using AWS account %s, region %s, profile %s", account, args.region, args.profile)

    src_bucket = args.source_bucket or f"eagle-documents-{account}-dev"
    tgt_bucket = args.target_bucket or f"eagle-kb-vectors-{account}-dev"

    LOG.info("Source : s3://%s/%s", src_bucket, args.source_prefix)
    LOG.info("Target : %s / index %s", tgt_bucket, args.target_index)
    LOG.info("Model  : %s (dim %d)", args.embed_model, args.embed_dim)
    LOG.info("Mode   : %s", "DRY-RUN (no writes)" if args.dry_run else "WRITE")

    s3 = sess.client("s3")
    bedrock = sess.client("bedrock-runtime")
    s3v = sess.client("s3vectors")

    # 1. Walk source bucket; chunk + embed; write in batches.
    docs_processed = 0
    chunks_total = 0
    chunks_embedded = 0
    chunks_written = 0
    embed_failures = 0
    write_failures = 0

    pending: list[dict] = []

    for s3_key, text in iter_kb_objects(s3, src_bucket, args.source_prefix, args.limit):
        docs_processed += 1
        title = Path(s3_key).name
        chunks = chunk_text(text)
        chunks_total += len(chunks)

        for idx, chunk_str in enumerate(chunks):
            ch = Chunk(s3_key=s3_key, chunk_index=idx, text=chunk_str, title=title)
            embedding = embed_one(bedrock, ch.text, args.embed_model, args.embed_dim)
            if embedding is None:
                embed_failures += 1
                continue
            chunks_embedded += 1
            pending.append(
                {
                    "key": ch.vector_key(),
                    "data": {"float32": embedding},
                    "metadata": ch.metadata(),
                }
            )
            if len(pending) >= PUT_BATCH_SIZE:
                if args.dry_run:
                    chunks_written += len(pending)
                else:
                    written = put_batch(s3v, tgt_bucket, args.target_index, pending)
                    chunks_written += written
                    write_failures += len(pending) - written
                pending = []

        if docs_processed % 25 == 0:
            LOG.info(
                "progress: docs=%d chunks=%d embedded=%d written=%d failures=%d/%d (embed/write)",
                docs_processed,
                chunks_total,
                chunks_embedded,
                chunks_written,
                embed_failures,
                write_failures,
            )

    # Flush trailing batch.
    if pending:
        if args.dry_run:
            chunks_written += len(pending)
        else:
            written = put_batch(s3v, tgt_bucket, args.target_index, pending)
            chunks_written += written
            write_failures += len(pending) - written

    LOG.info("=" * 60)
    LOG.info("DONE")
    LOG.info("  docs processed : %d", docs_processed)
    LOG.info("  chunks total   : %d", chunks_total)
    LOG.info("  chunks embedded: %d", chunks_embedded)
    LOG.info("  chunks written : %d (dry-run=%s)", chunks_written, args.dry_run)
    LOG.info("  embed failures : %d", embed_failures)
    LOG.info("  write failures : %d", write_failures)

    return 0 if (embed_failures == 0 and write_failures == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
