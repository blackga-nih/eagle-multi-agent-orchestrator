"""
File-based cache for LLM vision judge results.

Keys: SHA-256 hash of screenshot PNG bytes.
Values: JSON files containing JudgmentResult.

Cache directory: data/e2e-judge/cache/
TTL: 7 days (configurable via E2E_JUDGE_CACHE_TTL_DAYS).
"""

import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional


@dataclass
class JudgmentResult:
    """Structured evaluation from the vision judge."""

    verdict: Literal["pass", "fail", "warning"]
    confidence: float  # 0.0-1.0
    reasoning: str
    ui_quality_score: int  # 1-10
    issues: list[str] = field(default_factory=list)
    timestamp: str = ""
    model_id: str = ""
    cached: bool = False
    step_name: str = ""
    journey: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


def compute_sha256(data: bytes) -> str:
    """Compute SHA-256 hex digest of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def compute_file_sha256(filepath: str) -> str:
    """Compute SHA-256 of a file on disk."""
    with open(filepath, "rb") as f:
        return compute_sha256(f.read())


class JudgeCache:
    """File-based cache keyed by screenshot SHA-256.

    Each cached judgment is stored as {sha256}.json in the cache directory.
    Expired entries (older than TTL) are treated as cache misses.
    """

    def __init__(self, cache_dir: str = None, ttl_days: int = None):
        if cache_dir is None:
            repo_root = Path(__file__).resolve().parent.parent.parent
            cache_dir = str(repo_root / "data" / "e2e-judge" / "cache")
        self.cache_dir = cache_dir
        self.ttl_seconds = (ttl_days or int(os.getenv("E2E_JUDGE_CACHE_TTL_DAYS", "7"))) * 86400
        os.makedirs(self.cache_dir, exist_ok=True)

    def _path(self, sha256: str) -> str:
        return os.path.join(self.cache_dir, f"{sha256}.json")

    def get(self, sha256: str) -> Optional[JudgmentResult]:
        """Look up a cached judgment. Returns None on miss or expiry."""
        path = self._path(sha256)
        if not os.path.exists(path):
            return None

        # Check TTL
        age = time.time() - os.path.getmtime(path)
        if age > self.ttl_seconds:
            return None

        try:
            with open(path, "r") as f:
                data = json.load(f)
            result = JudgmentResult(**data)
            result.cached = True
            return result
        except (json.JSONDecodeError, TypeError, KeyError):
            return None

    def put(self, sha256: str, judgment: JudgmentResult) -> None:
        """Store a judgment in the cache."""
        path = self._path(sha256)
        with open(path, "w") as f:
            json.dump(asdict(judgment), f, indent=2)

    def purge(self) -> int:
        """Remove all cached judgments. Returns count of files removed."""
        count = 0
        for fname in os.listdir(self.cache_dir):
            if fname.endswith(".json"):
                os.remove(os.path.join(self.cache_dir, fname))
                count += 1
        return count

    def stats(self) -> dict:
        """Return cache statistics."""
        files = [f for f in os.listdir(self.cache_dir) if f.endswith(".json")]
        total = len(files)
        expired = 0
        for f in files:
            age = time.time() - os.path.getmtime(os.path.join(self.cache_dir, f))
            if age > self.ttl_seconds:
                expired += 1
        return {"total": total, "active": total - expired, "expired": expired}
