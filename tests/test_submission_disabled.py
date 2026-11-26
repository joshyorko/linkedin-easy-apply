"""Offline rejection checks using real response models and no browser imports."""

import ast
from pathlib import Path
import runpy
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SubmissionDisabledTest(unittest.TestCase):
    def test_live_submit_rejected_before_any_external_dependency(self):
        models = runpy.run_path(str(ROOT / "src/linkedin/utils/responses.py"))
        cases = [
            ("apply_actions/apply.py", "apply_to_single_job", {"job_id": "synthetic"}),
            ("apply_actions/apply.py", "batch_apply_by_run_id", {"run_id": "synthetic"}),
            ("apply_actions/oneoff_apply.py", "apply_to_job_by_url", {"job_url": "synthetic"}),
            ("utils/apply_core.py", "_apply_to_job_core", dict.fromkeys(
                ["page", "job_id", "job_url", "job_title", "company", "profile", "answers"])),
            ("utils/apply_tools.py", "navigate_and_fill_easy_apply_form", dict.fromkeys(
                ["page", "dlg", "profile", "answers"])),
        ]
        for path, name, kwargs in cases:
            with self.subTest(entrypoint=name):
                tree = ast.parse((ROOT / "src/linkedin" / path).read_text())
                function = next(node for node in tree.body
                                if isinstance(node, ast.FunctionDef) and node.name == name)
                function.decorator_list = []
                # Resolve only annotations lazily. All executable statements remain.
                module = ast.Module(body=[ast.ImportFrom(
                    module="__future__", names=[ast.alias(name="annotations")], level=0
                ), function], type_ignores=[])
                namespace = {key: models[key] for key in
                             ("ApplyJobResponse", "BatchApplyResponse", "OneoffApplyResponse")}
                exec(compile(ast.fix_missing_locations(module), path, "exec"), namespace)
                flag = "submit" if name == "navigate_and_fill_easy_apply_form" else "allow_submit"
                result = namespace[name](**kwargs, **{flag: True})
                if not isinstance(result, dict):
                    result = result.model_dump()
                    self.assertEqual(result["result"], "SUBMISSION_DISABLED")
                else:
                    self.assertEqual(result["status"], "SUBMISSION_DISABLED")
                self.assertFalse(result["success"])
                self.assertFalse(result["submitted"])


if __name__ == "__main__":
    unittest.main()
