import os
import unittest
from unittest import mock

from dagon import platform_support


class PlatformSupportTests(unittest.TestCase):
    def setUp(self):
        platform_support._detect_bash.cache_clear()
        self.addCleanup(platform_support._detect_bash.cache_clear)

    def test_dagon_bash_override_wins(self):
        with mock.patch.dict(os.environ, {"DAGON_BASH": "/opt/custom/bash"}):
            self.assertEqual("/opt/custom/bash", platform_support.bash_executable())

    def test_detected_bash_exists_on_this_platform(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DAGON_BASH", None)
            self.assertTrue(os.path.isfile(platform_support.bash_executable()))

    def test_posix_prefers_bash_on_path_over_bin_bash(self):
        with mock.patch.object(platform_support, "IS_WINDOWS", False), \
                mock.patch.object(platform_support.shutil, "which", return_value="/opt/homebrew/bin/bash"):
            self.assertEqual("/opt/homebrew/bin/bash", platform_support._detect_bash())
        platform_support._detect_bash.cache_clear()
        with mock.patch.object(platform_support, "IS_WINDOWS", False), \
                mock.patch.object(platform_support.shutil, "which", return_value=None), \
                mock.patch.object(platform_support.os.path, "exists", return_value=True):
            self.assertEqual("/bin/bash", platform_support._detect_bash())

    def test_missing_bash_raises_actionable_error(self):
        with mock.patch.dict(os.environ, {}, clear=False), \
                mock.patch.object(platform_support, "_detect_bash", return_value=None):
            os.environ.pop("DAGON_BASH", None)
            with self.assertRaisesRegex(RuntimeError, "DAGON_BASH"):
                platform_support.bash_executable()

    def test_shell_path_converts_windows_separators_only_on_windows(self):
        with mock.patch.object(platform_support, "IS_WINDOWS", True):
            self.assertEqual("C:/work/task dir", platform_support.shell_path("C:\\work\\task dir"))
        with mock.patch.object(platform_support, "IS_WINDOWS", False):
            self.assertEqual("/tmp/a\\b", platform_support.shell_path("/tmp/a\\b"))

    def test_windows_detection_skips_wsl_launcher(self):
        system_root = os.path.join(os.sep, "Windows")
        wsl = os.path.join(system_root, "System32", "bash.exe")
        with mock.patch.object(platform_support, "IS_WINDOWS", True), \
                mock.patch.object(platform_support, "_windows_candidates", return_value=[wsl]), \
                mock.patch.object(platform_support.os.path, "isfile", return_value=True), \
                mock.patch.dict(os.environ, {"SystemRoot": system_root}):
            self.assertIsNone(platform_support._detect_bash())

    def test_launcher_environment_inherits_on_posix_and_enables_symlinks_on_windows(self):
        with mock.patch.object(platform_support, "IS_WINDOWS", False):
            self.assertIsNone(platform_support.launcher_environment())
        with mock.patch.object(platform_support, "IS_WINDOWS", True), \
                mock.patch.dict(os.environ, {"CYGWIN": "user-choice"}):
            os.environ.pop("MSYS", None)
            environment = platform_support.launcher_environment()
        self.assertEqual("winsymlinks:native", environment["MSYS"])
        self.assertEqual("user-choice", environment["CYGWIN"])

    def test_launcher_scripts_are_written_with_lf_line_endings(self):
        import tempfile
        from dagon.task import Task
        with tempfile.TemporaryDirectory() as directory:
            os.makedirs(os.path.join(directory, ".dagon"))
            task = Task.__new__(Task)
            task.working_dir = directory
            Task.on_execute(task, "echo one\necho two\n", "launcher.sh")
            with open(os.path.join(directory, ".dagon", "launcher.sh"), "rb") as stream:
                self.assertNotIn(b"\r\n", stream.read())


if __name__ == "__main__":
    unittest.main()
