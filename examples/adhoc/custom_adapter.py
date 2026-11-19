"""A complete ad-hoc file-system adapter written outside the ``dagon`` package.

``LocalDirectory`` serves a node-local directory (for example a RAM disk or a
burst-buffer mount that needs no daemon) through DAGonStar's common ad-hoc
interface.  Supporting a new storage system takes only such a class and one
:func:`dagon.adhoc.register_provider` call: neither DAGonStar nor the storage
software is modified.  An installed package can instead declare the class in
the ``dagon.adhoc_providers`` entry-point group::

    [project.entry-points."dagon.adhoc_providers"]
    local-directory = "my_package.adapters:LocalDirectory"

Because the directory is reached with ordinary file calls (``access =
"posix"``), the adapter inherits the provider-neutral stream store and sets
``supports_streaming``.  Run this file to see a workflow use two volumes of
this provider at once, one of them task-scoped::

    python examples/adhoc/custom_adapter.py
"""

import os
import shutil
import tempfile
from typing import Any, Dict, Optional

from dagon import Workflow
from dagon.adhoc import AdHocFileSystem, register_provider
from dagon.task import DagonTask, TaskType


class LocalDirectory(AdHocFileSystem):
    """A directory created when the resource starts and removed when it stops."""

    provider = "local-directory"
    access = "posix"
    supports_streaming = True

    def __init__(self, workflow: Any, name: str = "default", path: Optional[str] = None,
                 keep: bool = False) -> None:
        super().__init__(workflow, name)
        self.path = path or os.path.join(workflow.get_scratch_dir_base(), ".local-directory-" + name)
        self.keep = keep

    @property
    def task_path(self) -> str:
        return self.path

    def start(self) -> None:
        if self.started or self.workflow.portable_emulation:
            return
        os.makedirs(self.path, exist_ok=True)
        self._started = True

    def is_ready(self) -> bool:
        return self.started and os.path.isdir(self.path)

    def stop(self) -> Optional[int]:
        if not self.started:
            return None
        self._started = False
        if not self.keep:
            shutil.rmtree(self.path, ignore_errors=True)
        return 0

    def provider_environment(self, task: Any) -> Dict[str, str]:
        return {"LOCAL_DIRECTORY": self.path}

    def path_variables(self):
        return ("LOCAL_DIRECTORY",)

    def metadata(self) -> Dict[str, Any]:
        return dict(super().metadata(), path=self.path, keep=self.keep)


register_provider("local-directory", LocalDirectory, replace=True)


def main() -> None:
    with tempfile.TemporaryDirectory() as scratch:
        config = {"batch": {"scratch_dir_base": scratch, "run_base": "", "threads": "4"},
                  "dagon_service": {"use": "False"}, "ftp_pub": {"ip": "localhost"}}
        workflow = Workflow("custom-adapter", config=config)
        shared = workflow.create_adhoc_filesystem("local-directory", name="shared", default=True)
        write = DagonTask(TaskType.BATCH, "write",
                          'echo hello > "$DAGON_ADHOC_SHARED_PATH/greeting.txt"')
        read = DagonTask(TaskType.BATCH, "read",
                         'echo workflow:///write/ > /dev/null; '
                         'cp "$DAGON_ADHOC_SHARED_PATH/greeting.txt" "$DAGON_ADHOC_PRIVATE_PATH/copy.txt" && '
                         '[ "$(cat "$DAGON_ADHOC_SHARED_PATH/greeting.txt")" = "$(cat "$DAGON_ADHOC_PRIVATE_PATH/copy.txt")" ] && '
                         'echo "$DAGON_ADHOC_NAMES" > names.txt')
        workflow.add_task(write)
        workflow.add_task(read)
        private = read.create_adhoc_filesystem("local-directory", name="private")
        workflow.run()
        failed = [task.name for task in workflow.tasks if task.result.get("code")]
        assert not failed, failed
        with open(os.path.join(read.working_dir, "names.txt"), encoding="utf-8") as stream:
            assert stream.read().split() == ["private,shared"], "both volumes are bound to the reader"
        assert not shared.started and not private.started
        assert not os.path.exists(private.path), "the task-scope volume was removed after its task"
        print("Workflow-scope default volume and task-scope volume: %s, %s"
              % (shared.metadata()["scope"], private.metadata()["scope"]))
        print("Verification: ok")


if __name__ == "__main__":
    main()
