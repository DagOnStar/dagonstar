"""Lesson 00: verify the installation, platform helpers, and sample configuration offline."""
import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
import configparser
import importlib.util
import os
import platform
from pathlib import Path

import dagon  # noqa: F401  (import check)
from dagon.platform_support import bash_executable
from dagon.task import TaskType

ROOT = Path(__file__).resolve().parents[2]
assert sys.version_info >= (3, 8), sys.version
assert Path(bash_executable()).exists() or bash_executable() == "bash"

sample = configparser.ConfigParser(interpolation=None)
sample.read(ROOT / "dagon.ini.sample", encoding="utf-8")
for section in ("batch", "agent.quality-local", "agent_provider.fixture"):
    assert sample.has_section(section), section
# The sample is documentation: agent profiles name an environment variable, never a key value.
for section in sample.sections():
    for key, value in sample.items(section):
        assert not (key == "api_key" and value.strip()), "sample must not contain a key: [%s]" % section

registered = sorted(item.value for item in TaskType)
assert "agentic" in registered and "batch" in registered, registered
extras = {name: importlib.util.find_spec(name) is not None
          for name in ("docker", "kubernetes", "libcloud", "globus_sdk", "cwltool")}
try:
    from importlib.metadata import version
    installed = version("dagonstar")
except Exception:  # running from a checkout without installation
    installed = "not installed (checkout on sys.path)"
print("Python", platform.python_version(), "on", platform.system(), "| dagonstar", installed)
print("bash:", bash_executable())
print("registered task types:", ", ".join(registered))
print("optional packages present:", ", ".join(k for k, v in sorted(extras.items()) if v) or "none")
print("DAGON_INI set:", "yes" if os.environ.get("DAGON_INI") else "no (lessons use temporary configuration)")
