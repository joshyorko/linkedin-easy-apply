"""Application state must survive replacement of the immutable source tree."""
from linkedin.utils import apply_tools, tools, robolog


def test_browser_state_uses_same_volume_across_source_replacements(tmp_path, monkeypatch):
    state = tmp_path / "state"
    monkeypatch.setenv("EASY_APPLY_STATE_DIR", str(state))
    calls = []
    monkeypatch.setattr(tools.browser, "configure", lambda **kwargs: calls.append(kwargs))
    for name in ("source-v1", "source-v2"):
        source = tmp_path / name
        source.mkdir()
        monkeypatch.chdir(source)
        tools.configure_browser(headless_mode=True)
        apply_tools.configure_browser(headless_mode=True)
    assert [call["persistent_context_directory"] for call in calls] == [str(state / "browser_context")] * 4


def test_logging_writes_only_to_owned_state_volume(tmp_path, monkeypatch):
    state = tmp_path / "state"
    source = tmp_path / "source"
    source.mkdir()
    monkeypatch.chdir(source)
    monkeypatch.setenv("EASY_APPLY_STATE_DIR", str(state))
    monkeypatch.setattr(robolog, "_LOGGING_INITIALIZED", False)
    monkeypatch.setattr(robolog.log, "setup_log", lambda **kwargs: None)
    calls = []
    monkeypatch.setattr(robolog.log, "add_log_output", lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr(robolog, "_configure_sensitive_data_protection", lambda: None)
    robolog.setup_logging(output_dir="./output/synthetic")
    assert calls[0]["output_dir"] == str(state / "output/synthetic")
    assert (state / "output/synthetic").is_dir()
    assert not (source / "output").exists()
