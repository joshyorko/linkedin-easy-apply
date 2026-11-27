"""Durable run results must not change when a job is rediscovered."""
import os
import threading
from uuid import uuid4

import pytest
from linkedin.server_actions import discovery
from linkedin.utils import db_sqlite


@pytest.fixture(params=["sqlite", "postgres"])
def database(request, monkeypatch, tmp_path):
    if request.param == "postgres":
        import psycopg2
        from linkedin.utils import db_postgres
        url = os.getenv("JHT_PEER_TEST_DATABASE_URL")
        if not url:
            pytest.skip("JHT_PEER_TEST_DATABASE_URL required for peer PostgreSQL proof")
        schema = "peer_history_" + uuid4().hex
        with psycopg2.connect(url) as admin, admin.cursor() as cursor:
            cursor.execute(f'CREATE SCHEMA "{schema}"')
        monkeypatch.setenv("DATABASE_TYPE", "postgres")
        monkeypatch.setenv("DATABASE_URL", url + f"?options=-csearch_path%3D{schema}")
        monkeypatch.setattr(db_postgres, "_connection_pool", None)
        try:
            yield db_postgres
        finally:
            if db_postgres._connection_pool:
                db_postgres._connection_pool.closeall()
            with psycopg2.connect(url) as admin, admin.cursor() as cursor:
                cursor.execute(f'DROP SCHEMA "{schema}" CASCADE')
    else:
        monkeypatch.setenv("DATABASE_TYPE", "sqlite")
        monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "peer.sqlite"))
        monkeypatch.setattr(db_sqlite, "_connections", threading.local())
        yield db_sqlite
        db_sqlite.get_connection().close()


def test_rediscovery_preserves_each_runs_public_snapshot(database):
    for run, title in [("search_A", "First"), ("search_B", "Second"), ("search_C", "Third")]:
        database.write_jobs([{"job_id": "123", "run_id": run, "title": title,
                              "company": "Synthetic", "job_description": "Public only",
                              "answers_json": "PRIVATE"}])
    for run, title in [("search_A", "First"), ("search_B", "Second"), ("search_C", "Third")]:
        result = discovery.export_recorded_public_listings(run).result
        assert result["returned_count"] == 1
        assert result["listings"][0]["title"] == title
        assert "PRIVATE" not in str(result)
    assert database.read_job_by_id("123")["title"] == "Third"


def test_parallel_run_can_export(database):
    database.write_jobs([{"job_id": "123", "run_id": "parallel_search_fixture",
                          "title": "Synthetic", "company": "Example"}])
    result = discovery.export_recorded_public_listings("parallel_search_fixture").result
    assert result["returned_count"] == 1
    assert result["error_code"] is None


def test_duplicate_write_does_not_change_observation(database):
    row = {"job_id": "123", "run_id": "search_A", "title": "Original", "company": "Synthetic"}
    database.write_jobs([row])
    database.write_jobs([{**row, "title": "Changed"}])
    assert discovery.export_recorded_public_listings("search_A").result["listings"][0]["title"] == "Original"


def test_snapshot_failure_rolls_back_job_change(database, monkeypatch):
    from linkedin.utils import recorded_listings
    row = {"job_id": "123", "run_id": "search_A", "title": "Original", "company": "Synthetic"}
    database.write_jobs([row])
    def fail(*args, **kwargs):
        raise RuntimeError("synthetic disk failure")
    monkeypatch.setattr(recorded_listings, "append_observations", fail)
    with pytest.raises(RuntimeError):
        database.write_jobs([{**row, "run_id": "search_B", "title": "Uncommitted"}])
    assert database.read_job_by_id("123")["title"] == "Original"


def test_new_ids_are_unique_and_both_modes_are_exportable(database):
    from linkedin.utils import search_history
    ids = [search_history.new_run_id(mode) for mode in ("standard", "parallel") for _ in range(1000)]
    assert len(set(ids)) == 2000
    assert all(discovery.RUN_ID_PATTERN.fullmatch(value) for value in ids)


def test_zero_result_receipt_survives_reconnect_and_duplicate_request(database):
    from linkedin.utils import search_history as history
    options = {"query": "Synthetic", "mode": "standard", "max_jobs": 2}
    run, created = history.begin("synthetic-zero", options)
    assert created
    finished = history.finish(run["run_id"], attempted=0, extracted=0)
    assert finished["execution_state"] == "completed"
    assert finished["persisted_count"] == 0
    assert finished["durability"] == "complete"
    assert finished["coverage"] == "bounded_unknown"
    replay, created = history.begin("synthetic-zero", options)
    assert not created
    assert replay == history.lookup("synthetic-zero")
    assert replay["run_id"] == run["run_id"]
    with pytest.raises(ValueError, match="conflict"):
        history.begin("synthetic-zero", {**options, "query": "Changed"})


def test_partial_persistence_and_failed_run_are_distinct(database):
    from linkedin.utils import search_history as history
    run, _ = history.begin("synthetic-partial", {"query": "Synthetic", "mode": "parallel"})
    database.write_jobs([{"job_id": "123", "run_id": run["run_id"], "title": "One", "company": "Synthetic"}])
    finished = history.finish(run["run_id"], attempted=3, extracted=2)
    assert finished["execution_state"] == "partial"
    assert finished["persisted_count"] == 1
    assert finished["durability"] == "partial"
    failed, _ = history.begin("synthetic-failure", {"query": "Synthetic", "mode": "standard"})
    result = history.finish(failed["run_id"], attempted=0, extracted=0, failed=True)
    assert result["execution_state"] == "failed"
    assert result["durability"] == "unknown"
    assert history.lookup("absent") is None
    with pytest.raises(ValueError, match="terminal"):
        history.finish(failed["run_id"], attempted=0, extracted=0)


def test_execution_reuses_receipt_without_repeating_search(database):
    from actions import Response
    from linkedin.utils import search_history as history
    calls = []
    def engine(options):
        run_id = history.execution_run_id(options["mode"])
        calls.append(run_id)
        database.write_jobs([{"job_id": "123", "run_id": run_id, "title": "Synthetic", "company": "Example"}])
        return Response(result={"attempted_count": 1, "total_jobs": 1})
    first = history.execute("synthetic-request", {"query": "Synthetic"}, engine)
    second = history.execute("synthetic-request", {"query": "Synthetic"}, engine)
    assert len(calls) == 1
    assert first == second
    assert first["persisted_count"] == 1
    assert first["execution_state"] == "completed"


def test_lost_response_and_inflight_request_do_not_restart_browser(database):
    from linkedin.utils import search_history as history
    run, _ = history.begin("accepted-before-disconnect", {"query": "Synthetic"})
    def forbidden(options):
        raise AssertionError("must reconcile, not rerun")
    result = history.execute("accepted-before-disconnect", {"query": "Synthetic"}, forbidden)
    assert result["run_id"] == run["run_id"]
    assert result["execution_state"] == "running"


def test_failed_execution_is_durable_and_cannot_be_retried_by_replay(database):
    from linkedin.utils import search_history as history
    def failed(options):
        raise RuntimeError("private browser diagnostic")
    with pytest.raises(RuntimeError):
        history.execute("failed-execution", {"query": "Synthetic"}, failed)
    result = history.execute("failed-execution", {"query": "Synthetic"}, failed)
    assert result["execution_state"] == "failed"
    assert result["error_code"] == "SEARCH_FAILED"
    assert "private" not in str(result)


@pytest.mark.parametrize("bad", [{"max_jobs": 101}, {"parallel_workers": 0}, {"query": " "},
                                   {"allow_submit": True}, {"enrich_jobs": True}, {"mode": "arbitrary"}])
def test_invalid_discovery_cannot_start_execution(database, bad):
    from linkedin.utils import search_history as history
    def forbidden(options):
        raise AssertionError("invalid requests must not invoke a browser")
    with pytest.raises(ValueError):
        history.execute("invalid", {"query": "Synthetic", **bad}, forbidden)
    assert history.lookup("invalid") is None


def test_fixed_actions_expose_only_public_results_and_durable_status(database, monkeypatch):
    from actions import Response
    from linkedin.server_actions import search_discovery
    from linkedin.utils import search_history as history
    def browser_engine(options):
        assert options["easy_apply_only"] is False
        run_id = history.execution_run_id(options["mode"])
        database.write_jobs([{"job_id": "123", "run_id": run_id, "title": "Synthetic", "company": "Example",
                              "answers_json": "PRIVATE ANSWER", "job_description": "Public description"}])
        return Response(result={"attempted_count": 1, "total_jobs": 1})
    monkeypatch.setattr(search_discovery, "_run_engine", browser_engine)
    first = search_discovery.start_public_search("request-1", "Synthetic", mode="parallel").result
    replay = search_discovery.start_public_search("request-1", "Synthetic", mode="parallel").result
    assert replay == first
    status = search_discovery.public_search_status("request-1").result
    assert status == first
    results = search_discovery.public_search_results("request-1").result
    assert results["receipt"] == first
    assert results["listings"][0]["title"] == "Synthetic"
    assert results["listings"][0]["source_run_id"] == first["run_id"]
    assert "PRIVATE" not in str(results)
    assert results["rejected_count"] == 0
    assert search_discovery.public_search_status("absent").result == {"error_code": "SEARCH_NOT_FOUND"}


def test_concurrent_first_delivery_has_one_execution_owner(database):
    from concurrent.futures import ThreadPoolExecutor

    from linkedin.utils import search_history as history
    def start(_index):
        return history.begin("concurrent-key", {"query": "Synthetic"})
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(start, range(6)))
    assert sum(created for _receipt, created in results) == 1
    assert len({receipt["run_id"] for receipt, _created in results}) == 1


def test_completed_zero_search_has_empty_results_without_job_table(database, monkeypatch):
    from actions import Response
    from linkedin.server_actions import search_discovery
    monkeypatch.setattr(search_discovery, "_run_engine", lambda _options: Response(result={"attempted_count": 0, "total_jobs": 0}))
    search_discovery.start_public_search("zero-results", "Synthetic")
    result = search_discovery.public_search_results("zero-results").result
    assert result["receipt"]["execution_state"] == "completed"
    assert result["receipt"]["persisted_count"] == 0
    assert result["listings"] == []


@pytest.mark.parametrize("count", [0, 1])
def test_four_actions_reconcile_after_process_restart(database, monkeypatch, tmp_path, count):
    import json
    import subprocess
    import sys
    from pathlib import Path

    from actions import Response
    from linkedin.server_actions import search_discovery
    from linkedin.utils import search_history

    def recorded_engine(options):
        if count:
            database.write_jobs([{
                "job_id": "synthetic-restart", "title": "Synthetic", "company": "Example",
                "run_id": search_history.execution_run_id(options["mode"]),
            }])
        return Response(result={"attempted_count": count, "total_jobs": count})

    monkeypatch.setattr(search_discovery, "_run_engine", recorded_engine)
    receipt = search_discovery.start_public_search("restart-delivery", "Synthetic").result
    environment = {
        "HOME": str(tmp_path), "PYTHON_DOTENV_DISABLED": "1",
        "PYTHONPATH": str(Path(__file__).parents[1] / "src"),
        "DATABASE_TYPE": os.environ["DATABASE_TYPE"],
    }
    for key in ("SQLITE_PATH", "DATABASE_URL"):
        if key in os.environ:
            environment[key] = os.environ[key]
    script = '''
import json
from linkedin.server_actions import discovery, search_discovery
def forbidden(options):
    raise AssertionError("duplicate delivery attempted browser work")
search_discovery._run_engine = forbidden
started = search_discovery.start_public_search("restart-delivery", "Synthetic").result
status = search_discovery.public_search_status("restart-delivery").result
results = search_discovery.public_search_results("restart-delivery").result
exported = discovery.export_recorded_public_listings(started["run_id"]).result
print("ACCEPTANCE:" + json.dumps([started, status, results, exported]))
'''
    process = subprocess.run([sys.executable, "-c", script], env=environment,
                             capture_output=True, text=True, timeout=30, check=False)
    assert process.returncode == 0, process.stderr
    payload = next(line.removeprefix("ACCEPTANCE:") for line in process.stdout.splitlines()
                   if line.startswith("ACCEPTANCE:"))
    started, status, results, exported = json.loads(payload)
    assert started == status == results["receipt"] == receipt
    assert receipt["execution_state"] == "completed"
    assert receipt["coverage"] == "bounded_unknown"
    assert len(results["listings"]) == count
    assert exported["returned_count"] == count
    assert exported["status"] == "unknown"


def test_discovery_adapter_disables_form_capture_before_calling_existing_engine(monkeypatch):
    from actions import Response
    from linkedin.search_actions import parallel_search, search
    from linkedin.server_actions import search_discovery
    from linkedin.utils.search_history import SearchOptions
    def engine(**kwargs):
        assert kwargs["snapshot_easy_apply"] is False
        assert "allow_submit" not in kwargs
        return Response(result={"attempted_count": 0, "total_jobs": 0})
    monkeypatch.setattr(search, "search_linkedin_easy_apply", engine)
    monkeypatch.setattr(parallel_search, "parallel_search_linkedin_easy_apply", engine)
    for mode in ("standard", "parallel"):
        result = search_discovery._run_engine(SearchOptions(query="Synthetic", mode=mode).model_dump())
        assert result.result["total_jobs"] == 0


def test_runtime_action_code_identity_is_distinct():
    from linkedin.search_actions.parallel_search import parallel_search_linkedin_easy_apply
    from linkedin.search_actions.search import search_linkedin_easy_apply
    # Actions Runtime identifies registrations by code name and source filename,
    # not functools.wraps metadata. Both actions must retain their own identity.
    for function in (search_linkedin_easy_apply, parallel_search_linkedin_easy_apply):
        assert function.__code__.co_name == function.__name__


def test_discovery_supports_runtime_individual_module_loading(tmp_path):
    import subprocess
    import sys
    from pathlib import Path

    source = Path(__file__).parents[1] / "src"
    # Runtime imports a selected action file before its package initialization.
    # Eager re-export of that half-initialized module causes circular ImportError.
    script = """
import importlib.util
import sys
from pathlib import Path
path = Path(sys.argv[1]) / 'linkedin/server_actions/search_discovery.py'
spec = importlib.util.spec_from_file_location('linkedin.server_actions.search_discovery', path)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
assert callable(module.public_search_status)
"""
    result = subprocess.run([sys.executable, "-c", script, str(source)],
                            env={**os.environ, "PYTHONPATH": str(source), "DATABASE_TYPE": "sqlite",
                                 "SQLITE_PATH": str(tmp_path / "runtime-import.sqlite")},
                            capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 0, result.stderr
