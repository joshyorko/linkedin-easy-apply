"""Append-only public observations, independent of mutable peer job/profile state.

No backfill: overwritten historical observations cannot be reconstructed.
"""
from __future__ import annotations

import json
from typing import Any

PUBLIC_COLUMNS = (
    "job_id", "title", "company", "job_url", "location_raw", "location_type",
    "employment_type", "date_posted", "job_description", "scraped_at", "run_id",
)


def append_observations(connection: Any, records: list[dict[str, Any]], *, postgres: bool) -> None:
    """Write in the job upsert's transaction; never replace an earlier observation."""
    marker = "%s" if postgres else "?"
    cursor = connection.cursor()
    try:
        if postgres:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext(current_schema()), 1246254163)")
        cursor.execute("""CREATE TABLE IF NOT EXISTS search_observations (
            run_id TEXT NOT NULL, job_id TEXT NOT NULL, public_json TEXT NOT NULL,
            PRIMARY KEY (run_id, job_id))""")
        for record in records:
            if not record.get("run_id") or not record.get("job_id"):
                continue
            public = {key: record.get(key) for key in PUBLIC_COLUMNS}
            cursor.execute(
                f"INSERT INTO search_observations (run_id, job_id, public_json) "
                f"VALUES ({marker}, {marker}, {marker}) ON CONFLICT (run_id, job_id) DO NOTHING",
                (record["run_id"], record["job_id"], json.dumps(public, default=str)),
            )
    finally:
        cursor.close()


def read_observations(connection: Any, run_id: str, limit: int, *, postgres: bool) -> list[dict[str, Any]] | None:
    """None means no retained observations; caller may expose legacy rows as unknown."""
    cursor = connection.cursor()
    try:
        if postgres:
            cursor.execute("SELECT to_regclass('search_observations')")
            exists = cursor.fetchone()[0] is not None
        else:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='search_observations'")
            exists = cursor.fetchone() is not None
        if not exists:
            return None
        marker = "%s" if postgres else "?"
        cursor.execute(
            f"SELECT public_json FROM search_observations WHERE run_id = {marker} "
            f"ORDER BY job_id ASC LIMIT {marker}", (run_id, limit),
        )
        rows = [json.loads(row[0]) for row in cursor.fetchall()]
        if rows:
            return rows
        # A durable empty run has no legacy job row to fall back to.
        if postgres:
            cursor.execute("SELECT to_regclass('search_runs')")
        else:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='search_runs'")
        table = cursor.fetchone()
        if table and table[0] is not None:
            cursor.execute(f"SELECT 1 FROM search_runs WHERE run_id = {marker}", (run_id,))
            if cursor.fetchone() is not None:
                return []
        return None
    finally:
        cursor.close()
