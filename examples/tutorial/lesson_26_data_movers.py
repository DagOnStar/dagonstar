"""Lesson 26: transfer protocol selection and generated commands for the data movers (all mocked)."""
import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / "examples" / "dynostore"))
from unittest import mock

from dynostore_commands import upload_catalog  # noqa: E402
from dagon.remote import RemoteTask  # noqa: E402
from dagon.stager.base import DataMover, Stager, StagerMover  # noqa: E402
from examples.tutorial.common.support import config  # noqa: E402

cfg = config("/scratch")
cfg["globus"] = {"clientid": "teaching-client", "intermediate_endpoint": "ep-intermediate"}


def task(ip, scp="active", endpoint=None, remote=False):
    item = mock.Mock(spec=RemoteTask) if remote else mock.Mock()
    item.get_info.return_value = {"ip": ip, "SCP": scp, "GRIDFTP": "active" if endpoint else "none",
                                  "FTP": "none"}
    item.get_scratch_dir.return_value = "/scratch/" + ip
    item.get_endpoint.return_value = endpoint
    item.working_dir = "/scratch/" + ip
    item.get_user.return_value = "user"
    item.get_ip.return_value = ip
    return item


same_host = {}
for mover in (DataMover.COPY, DataMover.LINK):
    script = Stager(mover, StagerMover.NORMAL, cfg).stage_in(task("10.0.0.1"), task("10.0.0.1"),
                                                             "/scratch/dst", "out/a.txt")
    same_host[mover.name] = "cp -r" in script if mover is DataMover.COPY else "ln -sf" in script
assert same_host == {"COPY": True, "LINK": True}, same_host

stager = Stager(DataMover.COPY, StagerMover.NORMAL, cfg)
scp_script = stager.stage_in(task("10.0.0.2"), task("10.0.0.1", remote=True), "/scratch/dst", "out/a.txt")
assert stager.last_data_mover is DataMover.SCP and "scp -r" in scp_script and "user@10.0.0.1" in scp_script

with mock.patch("dagon.communication.data_transfer.GlobusManager") as globus:
    stager.stage_in(task("10.0.0.2", endpoint="ep-b"), task("10.0.0.1", endpoint="ep-a"), "/scratch/dst",
                    "out/a.txt")
assert stager.last_data_mover is DataMover.GRIDFTP
globus.assert_called_once_with("ep-a", "ep-b", "teaching-client", "ep-intermediate")

strict = stager.generate_command("/scratch/src dir/*", "/scratch/dst", 'cp -r "$file" "$dst"',
                                 StagerMover.NORMAL.value, strict=True)
assert "dagon_stage_status=1" in strict and "IFS='\n'" in strict
upload = upload_catalog("input file; false", "catalog; false")
assert "'input file; false'" in upload and '"$DYNOSTORE_SERVER"' in upload
print("same host:", same_host, "| different hosts with SCP: SCP | with Globus endpoints: GRIDFTP (mocked)")
print("strict loops propagate failures; DynoStore commands quote arguments and read the server at runtime")
