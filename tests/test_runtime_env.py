import os
import subprocess
import sys
import tempfile
import unittest

from dagon.runtime_env import PACKAGE_ROOT, runner_environment


class RunnerEnvironmentTests(unittest.TestCase):
    def test_package_root_is_prepended_once_and_existing_entries_kept(self):
        base = {"PYTHONPATH": os.pathsep.join(["/opt/site", PACKAGE_ROOT]), "KEEP": "1"}
        environment = runner_environment({"TASK_VAR": "x"}, base=base)
        entries = environment["PYTHONPATH"].split(os.pathsep)
        self.assertEqual(entries.count(PACKAGE_ROOT), 1)
        self.assertIn("/opt/site", entries)
        self.assertEqual(environment["KEEP"], "1")
        self.assertEqual(environment["TASK_VAR"], "x")

    def test_package_root_is_added_when_pythonpath_is_unset(self):
        environment = runner_environment(base={})
        self.assertEqual(environment["PYTHONPATH"], PACKAGE_ROOT)

    def test_task_environment_overrides_base(self):
        environment = runner_environment({"MODE": "task"}, base={"MODE": "base"})
        self.assertEqual(environment["MODE"], "task")

    def test_runner_module_is_importable_from_unrelated_directory(self):
        base = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
        with tempfile.TemporaryDirectory() as directory:
            completed = subprocess.run(
                [sys.executable, "-c", "import dagon.native_runner, dagon.web.runner"],
                cwd=directory, env=runner_environment(base=base), capture_output=True, text=True,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
