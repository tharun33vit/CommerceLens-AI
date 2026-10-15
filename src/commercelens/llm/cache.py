"""
Review Intelligence Response Cache
==================================
Provides persistent, deterministic response caching keyed by normalized source text,
model version, and prompt version to ensure reproducible, idempotent execution
and prevent redundant API token expenditure.
"""

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


def compute_content_hash(text: str, model_name: str, prompt_version: str) -> str:
    """
    Computes a deterministic SHA-256 hash identifying the input text,
    model configuration, and prompt template version.
    """
    payload = f"{text.strip()}||{model_name.strip()}||{prompt_version.strip()}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class ReviewAnalysisCache:
    """
    File-backed atomic cache for LLM review analysis outputs.
    Stores one JSON file per content hash.
    """

    def __init__(self, cache_dir: Optional[Path] = None):
        if cache_dir is None:
            self.cache_dir = Path("reports/review_intelligence/.cache")
        else:
            self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_path(self, content_hash: str) -> Path:
        return self.cache_dir / f"{content_hash}.json"

    def get(self, content_hash: str) -> Optional[Dict[str, Any]]:
        """Retrieve cached analysis if available and valid."""
        path = self._get_path(content_hash)
        if not path.is_file():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def set(self, content_hash: str, data: Dict[str, Any]) -> None:
        """Atomically persist analysis output to cache."""
        path = self._get_path(content_hash)
        tmp_path = self.cache_dir / f"{content_hash}.tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, path)
        except Exception:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass

    def count(self) -> int:
        """Return the number of cached items."""
        return len(list(self.cache_dir.glob("*.json")))

    def clear(self) -> int:
        """Clear all cached responses and return count of deleted files."""
        count = 0
        for p in self.cache_dir.glob("*.json"):
            try:
                p.unlink()
                count += 1
            except Exception:
                pass
        return count
