"""Read-only export of public listings already recorded for one search run."""

from __future__ import annotations

import os
import re
import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from actions import Response, action

from ..utils.recorded_listings import read_observations

SCHEMA_VERSION = 1
MAX_LIMIT = 100
MAX_DESCRIPTION_LENGTH = 2_000
RUN_ID_PATTERN = re.compile(r"(?:parallel_)?search_[A-Za-z0-9_-]{1,96}\Z")

DatabaseError: type[Exception] = sqlite3.Error
if os.getenv("DATABASE_TYPE", "sqlite").lower() == "postgres":
    from psycopg2 import Error as _PostgresError

    DatabaseError = _PostgresError

def _public_text(value: Any, maximum: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    return text[:maximum] or None


def _public_url(value: Any) -> str | None:
    url = _public_text(value, 2_048)
    if url is None:
        return None
    try:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname != "www.linkedin.com" or not parsed.path.startswith("/jobs/") or parsed.username or parsed.password:
            return None
    except ValueError:
        return None
    return url


def _recorded_at(value: Any) -> str | None:
    if isinstance(value, (datetime, date)):
        if isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None:
            return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
        return value.isoformat()
    text = _public_text(value, 64)
    if text is None:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is not None and parsed.utcoffset() is not None:
        return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return parsed.isoformat()


def _read_public_rows(run_id: str, limit: int) -> list[dict[str, Any]]:
    columns = "job_id, title, company, job_url, location_raw, location_type, employment_type, date_posted, job_description, scraped_at, run_id"
    database_type = os.getenv("DATABASE_TYPE", "sqlite").lower()
    if database_type == "postgres":
        import psycopg2
        from psycopg2.extras import RealDictCursor

        from ..utils import db_postgres

        connection = psycopg2.connect(connect_timeout=3, **db_postgres._get_db_config())
        try:
            connection.set_session(readonly=True, autocommit=False)
            with connection.cursor() as timeout_cursor:
                timeout_cursor.execute("SELECT set_config('statement_timeout', %s, true)", ("2000ms",))
            observed = read_observations(connection, run_id, limit, postgres=True)
            if observed is not None:
                return observed
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("SELECT set_config('statement_timeout', %s, true)", ("2000ms",))
                cursor.execute(
                    f"SELECT {columns} FROM job_postings WHERE run_id = %s ORDER BY scraped_at ASC, job_id ASC LIMIT %s",
                    (run_id, limit),
                )
                return [dict(row) for row in cursor.fetchall()]
        finally:
            try:
                connection.rollback()
            finally:
                connection.close()

    if database_type != "sqlite":
        raise ValueError("Unsupported database backend")

    from ..utils.db_sqlite import get_db_path

    database_path = Path(get_db_path()).resolve()
    if not database_path.is_file():
        raise FileNotFoundError("Recorded listing database is unavailable")
    connection = sqlite3.connect(f"{database_path.as_uri()}?mode=ro", uri=True, timeout=2)
    connection.row_factory = sqlite3.Row
    try:
        observed = read_observations(connection, run_id, limit, postgres=False)
        if observed is not None:
            return observed
        rows = connection.execute(
            f"SELECT {columns} FROM job_postings WHERE run_id = ? ORDER BY scraped_at ASC, job_id ASC LIMIT ?",
            (run_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def _listing(row: dict[str, Any], run_id: str) -> dict[str, Any] | None:
    if row.get("run_id") != run_id:
        return None
    job_id = _public_text(row.get("job_id"), 200)
    title = _public_text(row.get("title"), 500)
    company = _public_text(row.get("company"), 500)
    if not job_id or not title or not company:
        return None
    return {
        "source_run_id": run_id,
        "external_id": job_id,
        "title": title,
        "company": company,
        "url": _public_url(row.get("job_url")),
        "location": _public_text(row.get("location_raw"), 500),
        "workplace_type": _public_text(row.get("location_type"), 100),
        "employment_type": _public_text(row.get("employment_type"), 200),
        "posted_at": _public_text(row.get("date_posted"), 64),
        "description": _public_text(row.get("job_description"), MAX_DESCRIPTION_LENGTH),
        "recorded_at": _recorded_at(row.get("scraped_at")),
    }


@action(is_consequential=False)
def export_recorded_public_listings(run_id: str, limit: int = 100) -> Response:
    """Export allowlisted public listing fields for one recorded search run.

    This action does not search, browse, enrich, score, or modify the peer DB.
    The peer has no persisted source-run completion marker, so status remains
    unknown unless this bounded response itself is truncated (partial).

    Args:
        run_id: Exact recorded search_ run identifier to export.
        limit: Maximum public listings to return, from 1 through 100.

    Returns:
        Public listings and the recorded run's bounded completeness status.
    """
    empty: list[dict[str, Any]] = []
    if not isinstance(run_id, str) or not RUN_ID_PATTERN.fullmatch(run_id):
        return Response(result={
            "schema_version": SCHEMA_VERSION,
            "provider": "linkedin-easy-apply",
            "run_id": "",
            "status": "unavailable",
            "completion_evidence": "not_persisted",
            "returned_count": 0,
            "truncated": False,
            "rejected_count": 0,
            "listings": empty,
            "error_code": "INVALID_RUN_ID",
        })
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        return Response(result={
            "schema_version": SCHEMA_VERSION,
            "provider": "linkedin-easy-apply",
            "run_id": run_id,
            "status": "unavailable",
            "completion_evidence": "not_persisted",
            "returned_count": 0,
            "truncated": False,
            "rejected_count": 0,
            "listings": empty,
            "error_code": "INVALID_LIMIT",
        })

    try:
        rows = _read_public_rows(run_id, limit + 1)
        listings = [item for row in rows if (item := _listing(row, run_id)) is not None]
    except (DatabaseError, FileNotFoundError, OSError, RuntimeError, ValueError):
        return Response(result={
            "schema_version": SCHEMA_VERSION,
            "provider": "linkedin-easy-apply",
            "run_id": run_id,
            "status": "unavailable",
            "completion_evidence": "not_persisted",
            "returned_count": 0,
            "truncated": False,
            "rejected_count": 0,
            "listings": empty,
            "error_code": "RECORDED_LISTING_READ_FAILED",
        })

    truncated = len(rows) > limit
    rejected_count = len(rows) - len(listings)
    bounded = listings[:limit]
    partial = truncated or rejected_count > 0
    return Response(result={
        "schema_version": SCHEMA_VERSION,
        "provider": "linkedin-easy-apply",
        "run_id": run_id,
        "status": "partial" if partial else "unknown",
        "completion_evidence": "not_persisted",
        "returned_count": len(bounded),
        "truncated": truncated,
        "rejected_count": rejected_count,
        "listings": bounded,
        "error_code": None,
    })
