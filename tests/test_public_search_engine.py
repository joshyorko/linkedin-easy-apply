"""Exercise the real serial engine without network, accounts, or form capture."""
from unittest.mock import MagicMock

from linkedin.search_actions import search
from linkedin.server_actions import search_discovery
from linkedin.utils import db_sqlite


def test_public_search_runs_serial_engine_and_replays_without_browser(tmp_path, monkeypatch):
    import threading

    monkeypatch.setenv("DATABASE_TYPE", "sqlite")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "search.sqlite"))
    monkeypatch.setattr(db_sqlite, "_connections", threading.local())
    monkeypatch.chdir(tmp_path)
    page = MagicMock()
    page.url = "https://www.linkedin.com/jobs/search/"
    page.get_by_role.return_value.count.return_value = 1
    page.get_by_role.return_value.first.count.return_value = 1
    for name in ("setup_logging", "cleanup_logging", "log_success", "log_warning", "log_error",
                 "log_section_start", "log_section_end", "log_metric", "capture_screenshot", "embed_html_table"):
        monkeypatch.setattr(search, name, lambda *args, **kwargs: None)
    monkeypatch.setattr(search, "configure_browser", lambda **kwargs: None)
    monkeypatch.setattr(search.browser, "goto", lambda url: page)
    monkeypatch.setattr(search.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(search, "_collect_job_ids_with_pagination", lambda page, maximum: ["123"])
    from linkedin.utils.responses import LinkedInJob

    def extract(page, job_id, run_id, **options):
        assert options["snapshot_easy_apply"] is False
        return LinkedInJob(job_id=job_id, run_id=run_id, title="Synthetic", company="Example")

    monkeypatch.setattr(search, "_extract_from_job_page", extract)
    receipt = search_discovery.start_public_search("serial-engine", "Synthetic").result
    assert receipt["execution_state"] == "completed"
    assert receipt["attempted_count"] == receipt["persisted_count"] == 1
    monkeypatch.setattr(search.browser, "goto", lambda url: (_ for _ in ()).throw(AssertionError("replay browsed")))
    assert search_discovery.start_public_search("serial-engine", "Synthetic").result == receipt
    result = search_discovery.public_search_results("serial-engine").result
    assert result["listings"][0]["external_id"] == "123"
    db_sqlite.get_connection().close()
