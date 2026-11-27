"""Exercise supported SQLite helpers with isolated synthetic storage."""
import threading

import pytest

from linkedin.utils import db_sqlite


@pytest.fixture
def database(monkeypatch, tmp_path):
    path = tmp_path / "helpers.sqlite"
    monkeypatch.setenv("SQLITE_PATH", str(path))
    monkeypatch.setattr(db_sqlite, "_connections", threading.local())
    yield path
    connection = getattr(db_sqlite._connections, "connection", None)
    if connection is not None:
        connection.close()


def test_database_path_respects_explicit_configuration(database):
    assert db_sqlite.get_db_path() == str(database)


def test_update_answers_persists_both_supported_answer_fields(database):
    db_sqlite.write_jobs([{"job_id": "synthetic", "title": "Example", "company": "Example"}])
    assert db_sqlite.update_answers_json("synthetic", '{"field":"synthetic"}') is True
    row = db_sqlite.read_job_by_id("synthetic")
    assert row["answers_json"] == {"field": "synthetic"}
    assert row["enriched_dataset"] == {"field": "synthetic"}
