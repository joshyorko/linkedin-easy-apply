"""Import the package and reject submission with no network or account state."""

import importlib
import os
from pathlib import Path
import socket
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]


def deny_network(*args, **kwargs):
    raise AssertionError("Network access is forbidden in offline qualification")


def main():
    with tempfile.TemporaryDirectory(prefix="easy-apply-offline-") as directory:
        # Keep all writes and account discovery away from the operator's home.
        os.environ.clear()
        os.environ.update({
            "HOME": directory,
            "DATABASE_TYPE": "sqlite",
            "SQLITE_PATH": str(Path(directory) / "synthetic.sqlite"),
            "PYTHON_DOTENV_DISABLED": "1",
        })
        os.chdir(directory)
        socket.create_connection = deny_network
        socket.socket.connect = deny_network
        socket.socket.connect_ex = deny_network
        sys.path.insert(0, str(ROOT / "src"))

        from actions import ActionError, Response, action, chat
        from actions_http import get, post

        assert all(callable(value) for value in (
            ActionError, Response, action, chat.get_file, chat.attach_file_content,
            get, post,
        ))

        modules = []
        for path in sorted((ROOT / "src/linkedin").rglob("*.py")):
            parts = path.relative_to(ROOT / "src").with_suffix("").parts
            name = ".".join(parts[:-1] if parts[-1] == "__init__" else parts)
            importlib.import_module(name)
            modules.append(name)

        from linkedin.apply_actions.apply import apply_to_single_job, batch_apply_by_run_id
        from linkedin.apply_actions.oneoff_apply import apply_to_job_by_url
        from linkedin.utils.apply_core import _apply_to_job_core
        from linkedin.utils.apply_tools import navigate_and_fill_easy_apply_form

        results = [
            apply_to_single_job("synthetic", allow_submit=True),
            batch_apply_by_run_id("synthetic", allow_submit=True),
            apply_to_job_by_url("synthetic", allow_submit=True),
            _apply_to_job_core(None, "synthetic", "synthetic", "synthetic",
                               "synthetic", {}, {}, True),
            navigate_and_fill_easy_apply_form(None, None, {}, {}, submit=True),
        ]
        for result in results:
            values = result if isinstance(result, dict) else result.model_dump()
            assert not values["success"] and not values["submitted"]
            assert values.get("status", values.get("result")) == "SUBMISSION_DISABLED"
        assert not any(name == "sema4ai" or name.startswith("sema4ai.")
                       or name == "sema4ai_http" for name in sys.modules)
        assert not list(Path(directory).rglob("*.sqlite"))
        print(f"PASS: {len(modules)} module imports, maintained APIs, 5 submission rejections; no network/account/database effects")


if __name__ == "__main__":
    main()
