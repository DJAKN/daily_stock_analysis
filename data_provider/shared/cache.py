# -*- coding: utf-8 -*-
"""
SQLite-backed persistent key-value cache for data providers.

Thread-safe. Uses WAL journal mode for concurrent read/write.
The cache persists across GitHub Actions runs via ``actions/cache@v4``.
"""

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Optional

_DEFAULT_DB_PATH = os.path.join(".", "data", "provider_cache.db")

_CREATE_TABLE = """\
CREATE TABLE IF NOT EXISTS cache_entries (
    key         TEXT PRIMARY KEY,
    data        TEXT NOT NULL,
    meta        TEXT,
    fetched_at  TEXT NOT NULL,
    provider    TEXT,
    hits        INTEGER DEFAULT 0
);
"""

_UPSERT = """\
INSERT INTO cache_entries (key, data, meta, fetched_at, provider, hits)
VALUES (?, ?, ?, ?, ?, 0)
ON CONFLICT(key) DO UPDATE SET
    data       = excluded.data,
    meta       = excluded.meta,
    fetched_at = excluded.fetched_at,
    provider   = excluded.provider,
    hits       = 0;
"""

_SELECT = "SELECT data, meta, fetched_at, provider, hits FROM cache_entries WHERE key = ?;"

_SELECT_META = "SELECT meta FROM cache_entries WHERE key = ?;"

_INCREMENT_HITS = "UPDATE cache_entries SET hits = hits + 1 WHERE key = ?;"

_DELETE = "DELETE FROM cache_entries WHERE key = ?;"


class ProviderCache:
    """SQLite-backed persistent key-value cache.

    Parameters
    ----------
    db_path : str or None
        Path to the SQLite database file. Falls back to the
        ``PROVIDER_CACHE_DIR`` env var (treated as directory) or
        ``./data/provider_cache.db``.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        if db_path is None:
            cache_dir = os.environ.get("PROVIDER_CACHE_DIR")
            if cache_dir:
                db_path = os.path.join(cache_dir, "provider_cache.db")
            else:
                db_path = _DEFAULT_DB_PATH

        self._db_path = db_path
        self._lock = threading.Lock()

        # Ensure parent directory exists
        parent = os.path.dirname(db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute(_CREATE_TABLE)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def put(
        self,
        key: str,
        data: dict,
        provider: str,
        meta: Optional[dict] = None,
    ) -> None:
        """Insert or update a cache entry."""
        now = datetime.now(timezone.utc).isoformat()
        data_json = json.dumps(data, ensure_ascii=False)
        meta_json = json.dumps(meta, ensure_ascii=False) if meta is not None else None
        with self._lock:
            self._conn.execute(_UPSERT, (key, data_json, meta_json, now, provider))
            self._conn.commit()

    def get(self, key: str) -> Optional[dict]:
        """Return cached entry or None. Increments hit counter."""
        return self._get_entry(key, stale=False)

    def get_stale(self, key: str) -> Optional[dict]:
        """Return cached entry marked as stale (for fallback). Increments hit counter."""
        return self._get_entry(key, stale=True)

    def get_meta(self, key: str) -> Optional[dict]:
        """Return only the metadata for *key*, or None."""
        with self._lock:
            cur = self._conn.execute(_SELECT_META, (key,))
            row = cur.fetchone()
        if row is None:
            return None
        meta_raw = row[0]
        if meta_raw is None:
            return None
        return json.loads(meta_raw)

    def delete(self, key: str) -> None:
        """Remove a cache entry."""
        with self._lock:
            self._conn.execute(_DELETE, (key,))
            self._conn.commit()

    def close(self) -> None:
        """Close the underlying database connection."""
        with self._lock:
            self._conn.close()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_entry(self, key: str, *, stale: bool) -> Optional[dict]:
        with self._lock:
            cur = self._conn.execute(_SELECT, (key,))
            row = cur.fetchone()
            if row is None:
                return None
            self._conn.execute(_INCREMENT_HITS, (key,))
            self._conn.commit()

        data_raw, meta_raw, fetched_at, provider, _hits = row
        return {
            "data": json.loads(data_raw),
            "meta": json.loads(meta_raw) if meta_raw else None,
            "fetched_at": fetched_at,
            "provider": provider,
            "stale": stale,
        }
