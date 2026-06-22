import builtins
import importlib
import sys
import unittest
from unittest import mock

import dagon
from dagon.batch import Batch
from dagon.checkpoint import Checkpoint
from dagon.communication.data_transfer import GlobusManager
from dagon.shell import join_command, remote_target


class FailurePathTests(unittest.TestCase):
    def test_local_command_preserves_nonzero_exit_without_stderr(self):
        result = Batch.execute_command(
            join_command((sys.executable, "-c", "raise SystemExit(7)"))
        )

        self.assertEqual(7, result["code"])
        self.assertEqual("", result["message"])

    def test_checkpoint_command_preserves_nonzero_exit_without_stderr(self):
        result = Checkpoint.execute_command(
            join_command((sys.executable, "-c", "raise SystemExit(9)"))
        )

        self.assertEqual(9, result["code"])
        self.assertEqual("", result["message"])

    def test_remote_target_quotes_connection_values_but_expands_path_variable(self):
        target = remote_target("user; touch /tmp/pwned", "host name", '"$file"')

        self.assertEqual("'user; touch /tmp/pwned@host name:'\"$file\"", target)

    def test_globus_manager_reports_missing_optional_extra_before_authentication(self):
        real_import = builtins.__import__

        def import_without_globus(name, *args, **kwargs):
            if name == "globus_sdk":
                error = ImportError("No module named globus_sdk")
                error.name = "globus_sdk"
                raise error
            return real_import(name, *args, **kwargs)

        with mock.patch("builtins.__import__", side_effect=import_without_globus):
            with self.assertRaisesRegex(ImportError, r"dagonstar\[globus\]"):
                GlobusManager("source", "destination", "client", "intermediate")

    def test_api_server_reports_missing_optional_extra(self):
        real_import = builtins.__import__

        def import_without_flask(name, *args, **kwargs):
            if name == "flask":
                error = ImportError("No module named flask")
                error.name = "flask"
                raise error
            return real_import(name, *args, **kwargs)

        previous_server = sys.modules.pop("dagon.api.server", None)
        try:
            with mock.patch("builtins.__import__", side_effect=import_without_flask):
                with self.assertRaisesRegex(ImportError, r"dagonstar\[api\]"):
                    getattr(dagon, "WorkflowServer")
        finally:
            if previous_server is not None:
                sys.modules["dagon.api.server"] = previous_server
            importlib.invalidate_caches()


if __name__ == "__main__":
    unittest.main()
