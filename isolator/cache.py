"""Cache of ISO digests, so re-verifying a disk does not re-read every ISO.

The store lives on the host (~/.cache), never on the multiboot disk: anyone
able to alter an ISO there could alter a cache stored next to it. An entry is
reused only while the file keeps the same path, size and mtime; signatures
are still checked on every run, only the hashing is skipped.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable

from isolator.sums import file_digest


def default_store() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    return Path(base) / "isolator" / "digests.json"


class DigestCache:
    """`store=None` disables caching (every digest is computed)."""

    def __init__(self, store: Path | None, compute: Callable[[Path, str], str] = file_digest):
        self.store, self.compute = store, compute
        self.entries: dict[str, dict] = self._load()

    def _load(self) -> dict[str, dict]:
        if self.store is None:
            return {}
        try:
            data = json.loads(self.store.read_text())
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}  # missing or corrupt: start over, it is only a cache

    def digest(self, path: Path, algo: str) -> str:
        st = path.stat()
        key, stamp = str(path.resolve()), [st.st_size, st.st_mtime_ns]
        entry = self.entries.get(key)
        if not isinstance(entry, dict) or entry.get("stamp") != stamp:
            entry = self.entries[key] = {"stamp": stamp, "digests": {}}
        digests = entry["digests"]
        if algo not in digests:
            digests[algo] = self.compute(path, algo)
        return digests[algo]

    def save(self) -> None:
        if self.store is None:
            return
        self.store.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.store.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.entries, indent=1))
        os.replace(tmp, self.store)
