"""Operating-system portability helpers for local task execution.

DAGonStar launchers are POSIX shell scripts.  On Linux, macOS, and other POSIX
systems they run with the system ``bash``.  On Windows, DAGonStar runs them with
a POSIX ``bash`` supplied by Git for Windows, MSYS2, or Cygwin; WSL's
``C:\\Windows\\System32\\bash.exe`` is deliberately skipped because it runs in a
separate Linux filesystem namespace and cannot see Windows scratch paths the
same way.  Set ``DAGON_BASH`` to an explicit interpreter path to override the
detection on any platform.
"""

import os
import shutil
from functools import lru_cache
from typing import List, Optional

IS_WINDOWS = os.name == "nt"


def _windows_candidates() -> List[str]:
    candidates = []
    git = shutil.which("git")
    if git:
        # <Git>/cmd/git.exe or <Git>/bin/git.exe -> <Git>/bin/bash.exe
        root = os.path.dirname(os.path.dirname(os.path.realpath(git)))
        candidates.append(os.path.join(root, "bin", "bash.exe"))
        candidates.append(os.path.join(root, "usr", "bin", "bash.exe"))
    for variable in ("ProgramW6432", "ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        base = os.environ.get(variable)
        if base:
            candidates.append(os.path.join(base, "Git", "bin", "bash.exe"))
            candidates.append(os.path.join(base, "Programs", "Git", "bin", "bash.exe"))
    candidates.extend([r"C:\msys64\usr\bin\bash.exe", r"C:\cygwin64\bin\bash.exe"])
    found = shutil.which("bash")
    if found:
        candidates.append(found)
    return candidates


def _is_wsl_launcher(path: str) -> bool:
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    normalized = os.path.normcase(os.path.abspath(path))
    return normalized.startswith(os.path.normcase(os.path.join(os.path.abspath(system_root), "")))


@lru_cache(maxsize=None)
def _detect_bash() -> Optional[str]:
    if IS_WINDOWS:
        for candidate in _windows_candidates():
            if candidate and os.path.isfile(candidate) and not _is_wsl_launcher(candidate):
                return candidate
        return None
    if os.path.exists("/bin/bash"):
        return "/bin/bash"
    return shutil.which("bash")


def bash_executable() -> str:
    """Return the POSIX bash interpreter used for local launchers.

    ``DAGON_BASH`` takes precedence.  A clear error is raised when no suitable
    interpreter exists, instead of failing later with an opaque launch error.
    """
    override = os.environ.get("DAGON_BASH")
    if override:
        return override
    found = _detect_bash()
    if found:
        return found
    hint = ("install Git for Windows (Git Bash), MSYS2, or Cygwin" if IS_WINDOWS
            else "install bash")
    raise RuntimeError("DAGonStar local tasks require a POSIX bash; %s or set DAGON_BASH" % hint)


def shell_path(path: str) -> str:
    """Return *path* in a form the launcher shell understands.

    Windows separators are converted to ``/`` so ``C:\\work\\task`` becomes
    ``C:/work/task``, which Git Bash, MSYS2, and Cygwin all accept and which
    Python's Windows file APIs also accept.  POSIX paths are returned unchanged.
    """
    if IS_WINDOWS and path:
        return str(path).replace("\\", "/")
    return path


def launcher_environment() -> Optional[dict]:
    """Return the environment for local launcher processes.

    ``None`` (inherit the parent environment) on POSIX.  On Windows, ``MSYS``
    and ``CYGWIN`` default to ``winsymlinks:native`` so ``ln -s`` in the
    ``LINK`` data mover creates real symbolic links when Windows allows it
    (developer mode or an elevated process) instead of silently copying.
    Values already set by the user are kept.
    """
    if not IS_WINDOWS:
        return None
    environment = dict(os.environ)
    environment.setdefault("MSYS", "winsymlinks:native")
    environment.setdefault("CYGWIN", "winsymlinks:native")
    return environment
