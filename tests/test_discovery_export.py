import sqlite3
from datetime import UTC, datetime

from linkedin.server_actions import discovery


def test_exports_only_public_allowlisted_fields_and_marks_run_unknown(monkeypatch):
    monkeypatch.setattr(
        discovery,
        "_read_public_rows",
        lambda run_id, _limit: [{
            "run_id": run_id,
            "job_id": "12345",
            "title": "Platform Engineer",
            "company": "Example Co",
            "job_url": "https://www.linkedin.com/jobs/view/12345",
            "location_raw": "Remote, US",
            "location_type": "Remote",
            "employment_type": "Full-time",
            "date_posted": "2026-10-20",
            "job_description": "Build reliable systems.",
            "scraped_at": datetime(2026, 10, 20, tzinfo=UTC),
            "answers_json": '{"name":"private"}',
            "fit_score": 1.0,
            "raw_html": "private markup",
            "form_elements": {"private": True},
        }],
    )

    payload = discovery.export_recorded_public_listings("search_20261020_fixture").result

    assert payload["status"] == "unknown"
    assert payload["completion_evidence"] == "not_persisted"
    assert payload["run_id"] == "search_20261020_fixture"
    assert payload["returned_count"] == 1
    assert payload["rejected_count"] == 0
    assert set(payload["listings"][0]) == {
        "source_run_id", "external_id", "title", "company", "url", "location",
        "workplace_type", "employment_type", "posted_at", "description", "recorded_at",
    }
    assert "private" not in str(payload)


def test_empty_run_is_unknown_not_complete_empty(monkeypatch):
    monkeypatch.setattr(discovery, "_read_public_rows", lambda _run_id, _limit: [])

    payload = discovery.export_recorded_public_listings("search_20261020_empty").result

    assert payload["status"] == "unknown"
    assert payload["returned_count"] == 0
    assert payload["rejected_count"] == 0
    assert payload["listings"] == []


def test_non_linkedin_job_url_is_omitted(monkeypatch):
    monkeypatch.setattr(discovery, "_read_public_rows", lambda run_id, _limit: [{
        "run_id": run_id, "job_id": "12345", "title": "Engineer", "company": "Example",
        "job_url": "https://example.com/jobs/12345",
    }])

    payload = discovery.export_recorded_public_listings("search_20261020_url").result

    assert payload["listings"][0]["url"] is None
    assert payload["status"] == "unknown"


def test_truncation_is_partial_and_run_identity_is_checked(monkeypatch):
    monkeypatch.setattr(
        discovery,
        "_read_public_rows",
        lambda run_id, limit: [
            {"run_id": run_id, "job_id": str(index), "title": "Engineer", "company": "Example"}
            for index in range(limit)
        ],
    )

    payload = discovery.export_recorded_public_listings("search_20261020_many", limit=2).result

    assert payload["status"] == "partial"
    assert payload["truncated"] is True
    assert payload["returned_count"] == 2
    assert all(item["source_run_id"] == "search_20261020_many" for item in payload["listings"])

    monkeypatch.setattr(discovery, "_read_public_rows", lambda run_id, _limit: [
        {"run_id": run_id, "job_id": "bad", "title": "", "company": "Example"},
    ])
    rejected = discovery.export_recorded_public_listings("search_20261020_many").result
    assert rejected["status"] == "partial"
    assert rejected["rejected_count"] == 1


def test_invalid_scope_and_database_failure_do_not_look_like_empty_success(monkeypatch):
    invalid = discovery.export_recorded_public_listings("search_anything/else").result
    assert invalid["status"] == "unavailable"
    assert invalid["error_code"] == "INVALID_RUN_ID"

    monkeypatch.setattr(discovery, "_read_public_rows", lambda _run_id, _limit: (_ for _ in ()).throw(RuntimeError("private")))
    failed = discovery.export_recorded_public_listings("search_20261020_failure").result
    assert failed["status"] == "unavailable"
    assert failed["error_code"] == "RECORDED_LISTING_READ_FAILED"
    assert failed["rejected_count"] == 0
    assert "private" not in str(failed)


def test_reads_real_sqlite_rows_without_changing_database_bytes(monkeypatch, tmp_path):
    database_path = tmp_path / "recorded-listings.sqlite"
    with sqlite3.connect(database_path) as connection:
        connection.execute("""
            CREATE TABLE job_postings (
                job_id TEXT, title TEXT, company TEXT, job_url TEXT, location_raw TEXT,
                location_type TEXT, employment_type TEXT, date_posted TEXT,
                job_description TEXT, scraped_at TEXT, run_id TEXT, answers_json TEXT
            )
        """)
        connection.execute("""
            INSERT INTO job_postings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "98765", "Platform Engineer", "Example Co", "https://www.linkedin.com/jobs/view/98765",
            "Remote, US", "Remote", "Full-time", "2026-10-20", "Build stable systems.",
            "2026-10-20T12:00:00Z", "search_20261020_sqlite", '{"private":"answer"}',
        ))
    original_bytes = database_path.read_bytes()
    monkeypatch.setenv("DATABASE_TYPE", "sqlite")
    monkeypatch.setenv("SQLITE_PATH", str(database_path))

    payload = discovery.export_recorded_public_listings("search_20261020_sqlite").result

    assert payload["status"] == "unknown"
    assert payload["returned_count"] == 1
    assert payload["listings"][0]["external_id"] == "98765"
    assert payload["listings"][0]["recorded_at"] == "2026-10-20T12:00:00Z"
    assert "private" not in str(payload)
    assert database_path.read_bytes() == original_bytes


def test_missing_sqlite_database_is_not_created_and_unsupported_backend_is_unavailable(monkeypatch, tmp_path):
    missing_path = tmp_path / "must-not-be-created.sqlite"
    monkeypatch.setenv("DATABASE_TYPE", "sqlite")
    monkeypatch.setenv("SQLITE_PATH", str(missing_path))

    missing = discovery.export_recorded_public_listings("search_20261020_missing").result

    assert missing["status"] == "unavailable"
    assert missing["error_code"] == "RECORDED_LISTING_READ_FAILED"
    assert not missing_path.exists()

    monkeypatch.setenv("DATABASE_TYPE", "mysql")
    unsupported = discovery.export_recorded_public_listings("search_20261020_unsupported").result
    assert unsupported["status"] == "unavailable"
    assert unsupported["error_code"] == "RECORDED_LISTING_READ_FAILED"


def test_export_action_registers_with_runtime_parameter_validation():
    import json
    import subprocess
    import sys
    from pathlib import Path

    source = Path(discovery.__file__).resolve()
    result = subprocess.run(
        [sys.executable, "-m", "actions", "list", str(source)],
        capture_output=True, text=True, timeout=30, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    actions = json.loads(result.stdout)
    exported = next(action for action in actions if action["name"] == "export_recorded_public_listings")
    assert set(exported["input_schema"]["properties"]) == {"run_id", "limit"}
