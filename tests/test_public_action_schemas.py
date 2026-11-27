"""Collect the four fixed contracts through the maintained Actions CLI."""
import json
import subprocess
import sys
from pathlib import Path


def test_four_public_actions_have_runtime_collectable_schemas(tmp_path):
    source = Path(__file__).parents[1] / "src"
    result = subprocess.run(
        [sys.executable, "-m", "actions", "list", str(source / "linkedin/server_actions")],
        env={"HOME": str(tmp_path), "PYTHONPATH": str(source),
             "PYTHON_DOTENV_DISABLED": "1", "DATABASE_TYPE": "sqlite",
             "SQLITE_PATH": str(tmp_path / "unused.sqlite")},
        capture_output=True, text=True, timeout=30, check=False,
    )
    assert result.returncode == 0, result.stderr
    actions = json.loads(result.stdout)
    requirements = {
        "start_public_search": {"request_key", "query"},
        "public_search_status": {"request_key"},
        "public_search_results": {"request_key"},
        "export_recorded_public_listings": {"run_id"},
    }
    for name, required in requirements.items():
        matches = [action for action in actions if action["name"] == name]
        assert len(matches) == 1
        action = matches[0]
        assert set(action["input_schema"]["required"]) == required
        assert set(action["output_schema"]["properties"]) == {"result", "error"}
        assert "allow_submit" not in action["input_schema"]["properties"]
        assert "snapshot_easy_apply" not in action["input_schema"]["properties"]
        if name != "start_public_search":
            assert action["options"]["is_consequential"] is False
    assert not (tmp_path / "unused.sqlite").exists()
