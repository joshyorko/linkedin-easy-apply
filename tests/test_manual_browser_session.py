"""Fail-closed boundaries; no browser, account, network, or service is used."""

import importlib.util
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    "manual_session", Path(__file__).parents[1] / "scripts/manual_browser_session.py"
)
session = importlib.util.module_from_spec(spec)
spec.loader.exec_module(session)


class SessionBoundaryTests(unittest.TestCase):
    def test_wrong_remote_host_starts_nothing(self):
        with patch.object(session.socket, "gethostname", return_value="other-host"), patch.object(session, "run") as run:
            with self.assertRaisesRegex(RuntimeError, "approved pi5-02"):
                session.remote(True)
            run.assert_not_called()

    def test_wrong_image_starts_no_ui(self):
        result = subprocess.CompletedProcess([], 0, json.dumps([{
            "Architecture": "amd64", "Config": {"Labels": {}}
        }]))
        with patch.object(session.socket, "gethostname", return_value="pi5-02"), patch.object(session, "run", return_value=result), patch.object(session.subprocess, "Popen") as start:
            with self.assertRaisesRegex(RuntimeError, "pin does not match"):
                session.remote(True)
            start.assert_not_called()

    def test_running_service_prevents_profile_and_ui_access(self):
        image = subprocess.CompletedProcess([], 0, json.dumps([{
            "Architecture": "arm64", "Config": {"Labels": {
                "org.opencontainers.image.revision": session.SOURCE
            }}
        }]))
        busy = subprocess.CompletedProcess([], 0, "synthetic-running-container\n")
        with patch.object(session.socket, "gethostname", return_value="pi5-02"), patch.object(session, "run", side_effect=[image, busy]) as run, patch.object(session.subprocess, "Popen") as start:
            with self.assertRaisesRegex(RuntimeError, "reserved by a running service"):
                session.remote(False)
            self.assertEqual(run.call_count, 2)
            start.assert_not_called()

    def test_missing_approved_route_does_not_upload_or_start(self):
        unresolved = subprocess.CompletedProcess([], 0, "hostname pi5-02\n")
        with patch.object(session, "run", return_value=unresolved) as run, patch.object(session.subprocess, "Popen") as start:
            with self.assertRaisesRegex(RuntimeError, "One-time setup"):
                session.local(False)
            self.assertEqual(run.call_count, 1)
            start.assert_not_called()


if __name__ == "__main__":
    unittest.main()
