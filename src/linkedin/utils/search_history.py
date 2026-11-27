"""Durable search identity and receipts; Runtime completion is not search coverage."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from .recorded_listings import append_observations


class SearchOptions(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)
    query: str = Field(min_length=1, max_length=500)
    mode: Literal["standard", "parallel"] = "standard"
    max_jobs: int = Field(default=25, ge=1, le=100)
    parallel_workers: int = Field(default=3, ge=1, le=3)
    headless: bool = True
    remote: bool = False
    hybrid: bool = False
    onsite: bool = False
    easy_apply_only: bool = False
    snapshot_easy_apply: bool = False


def new_run_id(mode: str) -> str:
    if mode not in ("standard", "parallel"):
        raise ValueError("Unsupported search mode")
    prefix = "parallel_search" if mode == "parallel" else "search"
    return f"{prefix}_{uuid4().hex}"


@contextmanager
def connection() -> Iterator[tuple[Any, str]]:
    postgres = os.getenv("DATABASE_TYPE", "sqlite").lower() == "postgres"
    if postgres:
        import psycopg2

        from .db_postgres import _get_db_config
        conn = psycopg2.connect(connect_timeout=3, **_get_db_config())
    else:
        if os.getenv("DATABASE_TYPE", "sqlite").lower() != "sqlite":
            raise ValueError("Unsupported database backend")
        from pathlib import Path

        from .db_sqlite import get_db_path
        Path(get_db_path()).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(get_db_path(), timeout=10)
    try:
        with conn.cursor() if postgres else _sqlite_cursor(conn) as cursor:
            if postgres:
                # IF NOT EXISTS alone races on PostgreSQL's type catalog at first use.
                cursor.execute("SELECT pg_advisory_xact_lock(hashtext(current_schema()), 1246254163)")
            cursor.execute("""CREATE TABLE IF NOT EXISTS search_runs (
                request_key TEXT PRIMARY KEY, run_id TEXT NOT NULL UNIQUE,
                query_fingerprint TEXT NOT NULL, receipt_json TEXT NOT NULL)""")
        append_observations(conn, [], postgres=postgres)
        yield conn, "%s" if postgres else "?"
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def _sqlite_cursor(conn: Any) -> Iterator[Any]:
    cursor = conn.cursor()
    try:
        yield cursor
    finally:
        cursor.close()


def _validate_key(request_key: str) -> None:
    if not isinstance(request_key, str) or not 1 <= len(request_key) <= 128 or any(
        not (char.isascii() and (char.isalnum() or char in "-_.:")) for char in request_key
    ):
        raise ValueError("Invalid discovery request key")


def begin(request_key: str, options: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    _validate_key(request_key)
    normalized = SearchOptions.model_validate(options).model_dump()
    fingerprint = hashlib.sha256(json.dumps(normalized, sort_keys=True).encode()).hexdigest()
    receipt = {
        "schema_version": 1, "request_key": request_key,
        "run_id": new_run_id(normalized["mode"]), "query_fingerprint": fingerprint,
        "scope": "bounded_search", "options": normalized,
        "execution_state": "running", "durability": "unknown", "coverage": "bounded_unknown",
        "persisted_count": 0, "attempted_count": 0, "extracted_count": 0,
        "started_at": datetime.now(UTC).isoformat(), "finished_at": None,
        "error_code": None,
    }
    with connection() as (conn, marker):
        cursor = conn.cursor()
        cursor.execute(
            f"INSERT INTO search_runs VALUES ({marker}, {marker}, {marker}, {marker}) "
            "ON CONFLICT (request_key) DO NOTHING",
            (request_key, receipt["run_id"], fingerprint, json.dumps(receipt)),
        )
        created = cursor.rowcount == 1
        cursor.execute(f"SELECT query_fingerprint, receipt_json FROM search_runs WHERE request_key = {marker}", (request_key,))
        row = cursor.fetchone()
        if row[0] != fingerprint:
            raise ValueError("Discovery request key conflict")
        return json.loads(row[1]), created


def lookup(request_key: str) -> dict[str, Any] | None:
    _validate_key(request_key)
    with connection() as (conn, marker):
        cursor = conn.cursor()
        cursor.execute(f"SELECT receipt_json FROM search_runs WHERE request_key = {marker}", (request_key,))
        row = cursor.fetchone()
        return json.loads(row[0]) if row else None


def finish(run_id: str, *, attempted: int, extracted: int, failed: bool = False) -> dict[str, Any]:
    if not 0 <= extracted <= attempted:
        raise ValueError("Invalid search counts")
    with connection() as (conn, marker):
        cursor = conn.cursor()
        cursor.execute(f"SELECT receipt_json FROM search_runs WHERE run_id = {marker}", (run_id,))
        row = cursor.fetchone()
        if row is None:
            raise ValueError("Unknown search run")
        old = row[0]
        receipt = json.loads(old)
        if receipt["execution_state"] != "running":
            raise ValueError("Search run is terminal")
        cursor.execute(f"SELECT COUNT(*) FROM search_observations WHERE run_id = {marker}", (run_id,))
        persisted = cursor.fetchone()[0]
        complete = persisted == extracted == attempted
        receipt.update(
            execution_state="failed" if failed else "completed" if complete else "partial",
            durability="unknown" if failed else "complete" if complete else "partial",
            attempted_count=attempted, extracted_count=extracted, persisted_count=persisted,
            finished_at=datetime.now(UTC).isoformat(), error_code="SEARCH_FAILED" if failed else None,
        )
        cursor.execute(
            f"UPDATE search_runs SET receipt_json = {marker} WHERE run_id = {marker} AND receipt_json = {marker}",
            (json.dumps(receipt), run_id, old),
        )
        if cursor.rowcount != 1:
            raise ValueError("Search receipt changed concurrently")
        return receipt


# Only the execution adapter establishes this context. No caller-supplied run ID
# can attach new browser work to another request's durable receipt.
from contextvars import ContextVar

_active_run: ContextVar[str | None] = ContextVar("peer_search_run", default=None)


def execution_run_id(mode: str) -> str:
    return _active_run.get() or new_run_id(mode)


def execute(request_key: str, options: dict[str, Any], engine: Any) -> dict[str, Any]:
    receipt, created = begin(request_key, options)
    if not created:
        return receipt
    token = _active_run.set(receipt["run_id"])
    try:
        response = engine(receipt["options"])
        result = response.result if isinstance(response.result, dict) else response.model_dump()
        attempted = result["attempted_count"]
        extracted = result["total_jobs"]
        if type(attempted) is not int or type(extracted) is not int:
            raise ValueError("Invalid engine result counts")
        return finish(receipt["run_id"], attempted=attempted, extracted=extracted)
    except BaseException:
        finish(receipt["run_id"], attempted=0, extracted=0, failed=True)
        raise
    finally:
        _active_run.reset(token)
