"""One-shot backfill of the S3 Vectors index from the shared KB corpus.

Lists documents under eagle-knowledge-base/approved/, chunks them with a
recursive character splitter, embeds each chunk via Bedrock Titan Embed Text
v2 (1024-dim), and upserts the vectors into an S3 Vectors index.

Run:
    AWS_PROFILE=eagle python scripts/backfill_s3_vectors.py \
        --bucket eagle-documents-695681773636-dev \
        --prefix eagle-knowledge-base/approved/ \
        --vector-bucket rh-eagle \
        --index eagle-kb-approved \
        [--dry-run]

--dry-run lists + chunks + token-counts without embedding or upserting.
Idempotent: put_vectors with the same key upserts in place, so re-running
is safe.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import io
import json
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import ClientError

# Allow `from app.*` when running from repo root.
SERVER_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER_DIR))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("backfill_s3_vectors")
logging.getLogger("botocore").setLevel(logging.WARNING)
logging.getLogger("boto3").setLevel(logging.WARNING)

REGION = "us-east-1"
EMBED_MODEL_ID = "amazon.titan-embed-text-v2:0"
EMBED_DIM = 1024
METADATA_TABLE = "eagle-document-metadata-dev"

# Chunking params — match RO's recursive char splitter
CHUNK_SIZE = 4000
CHUNK_OVERLAP = 400
SEPARATORS = ["\n\n", "\n", ". ", " ", ""]

# S3 Vectors metadata value limit — must stay well under ~2KB per key/value.
MAX_METADATA_VALUE_LEN = 1500

# Rough cost estimate: Titan v2 is $0.00002 / 1K tokens.
COST_PER_1K_TOKENS = 0.00002


@dataclass
class Chunk:
    s3_key: str
    chunk_index: int
    chunk_total: int
    char_start: int
    char_end: int
    text: str


@dataclass
class DocMeta:
    title: str = ""
    summary: str = ""
    document_type: str = ""
    primary_agent: str = ""
    primary_topic: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# Chunking
# ─────────────────────────────────────────────────────────────────────────────

def _split_text(text: str, size: int, overlap: int, seps: list[str]) -> list[tuple[int, int, str]]:
    """Recursive character splitter, inspired by langchain.

    Returns list of (char_start, char_end, chunk_text).
    """
    if len(text) <= size:
        return [(0, len(text), text)]

    # Try the first separator that produces a usable split.
    for sep in seps:
        if not sep:
            continue
        parts = text.split(sep)
        if len(parts) == 1:
            continue
        # Merge parts back up to ~size chars
        chunks: list[tuple[int, int, str]] = []
        current = ""
        current_start = 0
        cursor = 0
        for part in parts:
            piece = (sep if current else "") + part
            if len(current) + len(piece) > size and current:
                chunks.append((current_start, cursor, current))
                # Overlap: keep last `overlap` chars from previous chunk
                overlap_text = current[-overlap:] if overlap < len(current) else current
                current = overlap_text + piece
                current_start = cursor - len(overlap_text)
                cursor = cursor + len(piece)
            else:
                if not current:
                    current_start = cursor
                current += piece
                cursor += len(piece)
        if current:
            chunks.append((current_start, cursor, current))
        return chunks

    # Hard fallback: chop every `size` chars with `overlap`
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        chunks.append((start, end, text[start:end]))
        if end == len(text):
            break
        start = end - overlap
    return chunks


def chunk_document(s3_key: str, text: str) -> list[Chunk]:
    raw = _split_text(text, CHUNK_SIZE, CHUNK_OVERLAP, SEPARATORS)
    total = len(raw)
    return [
        Chunk(
            s3_key=s3_key,
            chunk_index=i,
            chunk_total=total,
            char_start=start,
            char_end=end,
            text=body,
        )
        for i, (start, end, body) in enumerate(raw)
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Document loading
# ─────────────────────────────────────────────────────────────────────────────

def fetch_text(s3_client, bucket: str, key: str) -> str | None:
    """Fetch and decode a supported document from S3. Returns None to skip."""
    lower = key.lower()
    try:
        obj = s3_client.get_object(Bucket=bucket, Key=key)
        body = obj["Body"].read()
    except ClientError as e:
        logger.warning("fetch_text: get_object failed key=%s err=%s", key, e)
        return None

    try:
        if lower.endswith((".txt", ".md", ".content.md")):
            return body.decode("utf-8", errors="replace")
        if lower.endswith(".json"):
            text = body.decode("utf-8", errors="replace")
            # Pretty-serialize structured docs so the embedding captures keys.
            try:
                parsed = json.loads(text)
                return json.dumps(parsed, indent=2)
            except json.JSONDecodeError:
                return text
        if lower.endswith(".docx"):
            from docx import Document
            doc = Document(io.BytesIO(body))
            return "\n".join(p.text for p in doc.paragraphs if p.text)
        if lower.endswith(".pdf"):
            try:
                from pypdf import PdfReader
                reader = PdfReader(io.BytesIO(body))
                return "\n\n".join(page.extract_text() or "" for page in reader.pages)
            except Exception as e:
                logger.warning("fetch_text: pdf parse failed key=%s err=%s", key, e)
                return None
        return None
    except Exception as e:
        logger.warning("fetch_text: parse failed key=%s err=%s", key, e)
        return None


def list_docs(s3_client, bucket: str, prefix: str) -> list[dict[str, Any]]:
    """Return metadata-lite listing for all eligible docs under the prefix."""
    paginator = s3_client.get_paginator("list_objects_v2")
    out: list[dict[str, Any]] = []
    all_keys: set[str] = set()
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            all_keys.add(obj["Key"])
            out.append({"key": obj["Key"], "size": obj["Size"]})

    eligible = []
    skipped_sidecar = 0
    skipped_ext = 0
    for entry in out:
        key = entry["key"]
        lower = key.lower()
        # Dedup: if a .docx has a sibling .content.md, prefer the .content.md
        if lower.endswith(".docx") and f"{key}.content.md" in all_keys:
            skipped_sidecar += 1
            continue
        if lower.endswith((".txt", ".md", ".json", ".docx", ".pdf")):
            eligible.append(entry)
        else:
            skipped_ext += 1

    # KB-only validation — reject keys outside eagle-knowledge-base/ to
    # prevent index contamination even if --prefix is broader.
    _KB_PREFIX = "eagle-knowledge-base/"
    pre_validate = len(eligible)
    eligible = [e for e in eligible if e["key"].startswith(_KB_PREFIX)]
    rejected = pre_validate - len(eligible)
    if rejected > 0:
        logger.warning(
            "list_docs: REJECTED %d docs outside %s (prefix=%s)",
            rejected, _KB_PREFIX, prefix,
        )

    logger.info(
        "list_docs: total=%d eligible=%d sidecar_skipped=%d ext_skipped=%d kb_rejected=%d",
        len(out), len(eligible), skipped_sidecar, skipped_ext, rejected,
    )
    return eligible


# ─────────────────────────────────────────────────────────────────────────────
# Metadata lookup (DynamoDB)
# ─────────────────────────────────────────────────────────────────────────────

def load_metadata_index(region: str) -> dict[str, DocMeta]:
    """Scan the metadata table once and index by s3_key."""
    table = boto3.Session().resource("dynamodb", region_name=region).Table(METADATA_TABLE)
    index: dict[str, DocMeta] = {}
    resp = table.scan()
    items = resp.get("Items", [])
    while "LastEvaluatedKey" in resp:
        resp = table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
        items.extend(resp.get("Items", []))
    for item in items:
        s3_key = item.get("s3_key") or item.get("document_id")
        if not s3_key:
            continue
        index[s3_key] = DocMeta(
            title=str(item.get("title", ""))[:MAX_METADATA_VALUE_LEN],
            summary=str(item.get("summary", ""))[:MAX_METADATA_VALUE_LEN],
            document_type=str(item.get("document_type", ""))[:MAX_METADATA_VALUE_LEN],
            primary_agent=str(item.get("primary_agent", ""))[:MAX_METADATA_VALUE_LEN],
            primary_topic=str(item.get("primary_topic", ""))[:MAX_METADATA_VALUE_LEN],
        )
    logger.info("load_metadata_index: %d DynamoDB metadata entries", len(index))
    return index


# ─────────────────────────────────────────────────────────────────────────────
# Embedding (Bedrock Titan v2)
# ─────────────────────────────────────────────────────────────────────────────

def embed_one(runtime, text: str) -> list[float] | None:
    try:
        body = json.dumps({
            "inputText": text[:30000],  # Titan v2 input cap
            "dimensions": EMBED_DIM,
            "normalize": True,
        })
        resp = runtime.invoke_model(
            modelId=EMBED_MODEL_ID,
            body=body,
            contentType="application/json",
            accept="application/json",
        )
        payload = json.loads(resp["body"].read())
        return payload.get("embedding")
    except ClientError as e:
        logger.warning("embed_one failed: %s", e)
        return None


def embed_chunks_parallel(runtime, chunks: list[Chunk], workers: int = 10) -> list[tuple[Chunk, list[float]]]:
    results: list[tuple[Chunk, list[float]]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(embed_one, runtime, c.text): c for c in chunks}
        for fut in concurrent.futures.as_completed(futures):
            chunk = futures[fut]
            emb = fut.result()
            if emb is not None:
                results.append((chunk, emb))
    return results


# ─────────────────────────────────────────────────────────────────────────────
# S3 Vectors — bucket/index creation and upsert
# ─────────────────────────────────────────────────────────────────────────────

def ensure_bucket_and_index(sv, vector_bucket: str, index: str) -> None:
    # Vector bucket
    try:
        sv.create_vector_bucket(vectorBucketName=vector_bucket)
        logger.info("created vector bucket: %s", vector_bucket)
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code in ("ConflictException", "BucketAlreadyExists"):
            logger.info("vector bucket exists: %s", vector_bucket)
        else:
            raise

    # Index
    try:
        sv.create_index(
            vectorBucketName=vector_bucket,
            indexName=index,
            dataType="float32",
            dimension=EMBED_DIM,
            distanceMetric="cosine",
        )
        logger.info("created index: %s", index)
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code in ("ConflictException",):
            logger.info("index exists: %s", index)
        else:
            raise


def put_vectors_batch(
    sv,
    vector_bucket: str,
    index: str,
    chunks_with_embeddings: list[tuple[Chunk, list[float]]],
    doc_metas: dict[str, DocMeta],
    batch_size: int = 100,
) -> int:
    total = 0
    for i in range(0, len(chunks_with_embeddings), batch_size):
        batch = chunks_with_embeddings[i : i + batch_size]
        vectors_payload = []
        for chunk, emb in batch:
            meta_src = doc_metas.get(chunk.s3_key, DocMeta(
                title=chunk.s3_key.rsplit("/", 1)[-1],
            ))
            # S3 Vectors metadata must be scalar strings/numbers/booleans
            metadata = {
                "s3_key": chunk.s3_key,
                "document_id": chunk.s3_key,
                "title": meta_src.title or chunk.s3_key.rsplit("/", 1)[-1],
                "summary": meta_src.summary,
                "document_type": meta_src.document_type,
                "primary_agent": meta_src.primary_agent,
                "primary_topic": meta_src.primary_topic,
                "chunk_index": chunk.chunk_index,
                "chunk_total": chunk.chunk_total,
                "char_start": chunk.char_start,
                "char_end": chunk.char_end,
            }
            # Drop empties so we don't bloat the index
            metadata = {k: v for k, v in metadata.items() if v not in ("", None)}
            vectors_payload.append({
                "key": f"{chunk.s3_key}::chunk{chunk.chunk_index}",
                "data": {"float32": emb},
                "metadata": metadata,
            })
        try:
            sv.put_vectors(
                vectorBucketName=vector_bucket,
                indexName=index,
                vectors=vectors_payload,
            )
            total += len(vectors_payload)
        except ClientError as e:
            logger.error("put_vectors batch failed: %s", e)
    return total


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bucket", default="eagle-documents-695681773636-dev")
    parser.add_argument("--prefix", default="eagle-knowledge-base/approved/")
    parser.add_argument("--vector-bucket", default="rh-eagle")
    parser.add_argument("--index", default="eagle-kb-approved")
    parser.add_argument("--dry-run", action="store_true", help="List + chunk, skip embed/upsert")
    parser.add_argument("--limit", type=int, default=0, help="Cap docs processed (0 = all)")
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=100)
    args = parser.parse_args()

    if not args.prefix.startswith("eagle-knowledge-base/"):
        logger.warning(
            "WARNING: --prefix %r is outside eagle-knowledge-base/. "
            "Non-KB documents will be filtered out during listing.",
            args.prefix,
        )

    t0 = time.time()

    session = boto3.Session()
    s3 = session.client("s3", region_name=REGION)
    sv = session.client("s3vectors", region_name=REGION)
    runtime = session.client("bedrock-runtime", region_name=REGION)

    # 1. Ensure bucket + index (unless dry-run)
    if not args.dry_run:
        ensure_bucket_and_index(sv, args.vector_bucket, args.index)

    # 2. List docs
    docs = list_docs(s3, args.bucket, args.prefix)
    if args.limit > 0:
        docs = docs[: args.limit]
    logger.info("processing %d docs", len(docs))

    # 3. Load metadata index
    try:
        doc_metas = load_metadata_index(REGION)
    except Exception as e:
        logger.warning("metadata index failed, continuing without enrichment: %s", e)
        doc_metas = {}

    # 4. Fetch + chunk
    all_chunks: list[Chunk] = []
    docs_indexed = 0
    docs_skipped = 0
    total_chars = 0
    t_fetch = time.time()
    for idx, entry in enumerate(docs):
        key = entry["key"]
        text = fetch_text(s3, args.bucket, key)
        if not text:
            docs_skipped += 1
            continue
        chunks = chunk_document(key, text)
        if not chunks:
            docs_skipped += 1
            continue
        docs_indexed += 1
        total_chars += len(text)
        all_chunks.extend(chunks)
        if (idx + 1) % 25 == 0:
            logger.info("  fetched %d/%d (chunks so far: %d)", idx + 1, len(docs), len(all_chunks))
    logger.info("fetch+chunk done in %.1fs: %d docs -> %d chunks (%.1f MB text)",
                time.time() - t_fetch, docs_indexed, len(all_chunks), total_chars / 1024 / 1024)

    # 5. Estimate cost
    est_tokens = total_chars / 4  # rough
    est_cost = (est_tokens / 1000) * COST_PER_1K_TOKENS
    logger.info("rough token estimate: %.0f tokens  rough cost: $%.4f", est_tokens, est_cost)

    if args.dry_run:
        logger.info("--dry-run: skipping embed + upsert")
        report = {
            "mode": "dry-run",
            "docs_listed": len(docs),
            "docs_indexed": docs_indexed,
            "docs_skipped": docs_skipped,
            "total_chunks": len(all_chunks),
            "total_chars": total_chars,
            "est_tokens": est_tokens,
            "est_cost_usd": est_cost,
            "wall_time_sec": time.time() - t0,
        }
        _write_report(report)
        return

    # 6. Embed in parallel
    logger.info("embedding %d chunks with %d workers...", len(all_chunks), args.workers)
    t_embed = time.time()
    chunks_with_embeddings = embed_chunks_parallel(runtime, all_chunks, workers=args.workers)
    embed_fail = len(all_chunks) - len(chunks_with_embeddings)
    logger.info("embedded %d/%d chunks in %.1fs (%d failed)",
                len(chunks_with_embeddings), len(all_chunks), time.time() - t_embed, embed_fail)

    # 7. Upsert to S3 Vectors
    logger.info("upserting vectors to %s/%s...", args.vector_bucket, args.index)
    t_put = time.time()
    upserted = put_vectors_batch(
        sv, args.vector_bucket, args.index,
        chunks_with_embeddings, doc_metas, batch_size=args.batch_size,
    )
    logger.info("upserted %d vectors in %.1fs", upserted, time.time() - t_put)

    # 8. Report
    report = {
        "mode": "real",
        "vector_bucket": args.vector_bucket,
        "index": args.index,
        "embed_model": EMBED_MODEL_ID,
        "docs_listed": len(docs),
        "docs_indexed": docs_indexed,
        "docs_skipped": docs_skipped,
        "total_chunks": len(all_chunks),
        "chunks_embedded": len(chunks_with_embeddings),
        "embed_failures": embed_fail,
        "vectors_upserted": upserted,
        "total_chars": total_chars,
        "est_tokens": est_tokens,
        "est_cost_usd": est_cost,
        "wall_time_sec": round(time.time() - t0, 1),
    }
    _write_report(report)
    logger.info("done in %.1fs", time.time() - t0)


def _write_report(report: dict) -> None:
    out = SERVER_DIR / "scripts" / "backfill_s3_vectors_report.json"
    out.write_text(json.dumps(report, indent=2, default=str))
    logger.info("wrote report: %s", out)
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
