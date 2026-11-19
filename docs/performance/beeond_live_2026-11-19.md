# BeeOND as an ad-hoc resource: live verification (19 November 2026)

This record covers BeeOND used through the common
[ad-hoc file-system interface](../adhoc_filesystems.md) (`create_adhoc_filesystem("beeond", ...)`),
streaming over BeeOND, and developer-chosen volume variables (`export=`) on a
real BeeOND site. It extends the BeeOND site run of 13 November 2026 recorded
in [BeeOND](../beeond.md#live-site-verification). The run was manual and is not
part of CI. The raw output is in
[`raw/e4-beeond-xxcpu-2026-11-19.txt`](raw/e4-beeond-xxcpu-2026-11-19.txt).

## Host and software

| Host | System | Storage |
|---|---|---|
| E4 cluster, front end `fesrv`, Rocky Linux 8.10, Slurm 23.11.3, Python 3.11.11 | DAGonStar on the front end, which submits the BeeOND jobs | BeeOND started by the site Prolog for jobs submitted with `--comment=beeond-fs`, mounted at `/mnt/beeond_<user>-jobid_<job>` |

The working tree tested was the `development` branch at `915cd1b` plus the
uncommitted `export=` change, copied with `rsync`.

## Partitions

The site Prolog runs for every job submitted with `--comment=beeond-fs`, but
the volume is only mounted where the BeeGFS client is installed:

- `hhcpu` (wn17–wn20): three probe jobs (1090879–1090881, two nodes each)
  found no BeeGFS kernel module on wn17 and wn18 and no mount after 180 s,
  although the Prolog had written its port and node-list files. DAGonStar's
  BeeOND tasks there would fail at `mount_timeout`. The unit tests and local
  examples ran on `hhcpu` (below).
- `xxcpu` (wn01–wn04): a probe job (1090885, wn02–wn03) saw the volume mounted
  5 s after the job started. The live checks below ran there.

## `tools/ci_beeond_slurm.py --partition xxcpu --nodes 2`

Run from 18:00:45 to 18:05:51 UTC, with `verify=checksum`. Every BeeOND job
and holder used two nodes. All 30 checks passed:

| Scenario | Checks | What ran |
|---|---:|---|
| `task` | 6 | per-task volume persisted to the task directory, read downstream through `workflow://`, every node wrote into it |
| `failure` | 3 | a failing command; its volume was still persisted and verified |
| `workflow` | 6 | two `srun --jobid` steps shared one holder volume, every holder node wrote into it, the holder persisted it |
| `stream` | 6 | produce → consume over an ad-hoc BeeOND resource (`workflow:///produce/items?stream`): four items arrived verified and in order; the first was consumed 4.52 s before the producer finished |
| `export` | 6 | ad-hoc BeeOND resource with `export="JOBFS"` on two tasks of holder job 1090891 (wn02, wn04) |
| `signal` | 3 | `--signal=B:USR1@<grace>` stopped the command before its time limit and the volume was persisted and verified |

In the `export` scenario both tasks and the `dagon_beeond_srun` steps on both
nodes saw `$JOBFS` equal to `$DAGON_BEEOND` and `$DAGON_ADHOC_JOBFS_PATH`,
namely `/mnt/beeond_<user>-jobid_1090891`, the allocation's mount rather than a
submission-host path; each node wrote one file through `$JOBFS`, the second
task found both, and the execution metadata recorded only the name `JOBFS`.

This is the first live run of the ad-hoc BeeOND adapter and of BeeOND
streaming; earlier evidence for both was the CI's emulated BeeOND site.

## Unit tests and local examples on `hhcpu`

Run as Slurm jobs on wn17 with the CI extras (`pip install -e ".[docker,kubernetes]"`).
The first run, without those extras, also exposed a test that let the
caller's `SLURM_*` variables reach a simulated BeeOND holder: inside a Slurm job
the holder correctly reported `SLURM_JOB_NODELIST`, which the test did not
expect. `tests/test_beeond.py` now removes the caller's `SLURM_*` variables
before simulating a job.

With the fix, job 1090893 (18:08:49–18:19:48 UTC) passed: 472 unit tests (3
skipped), the `py_compile` check, `tools/validate_tutorial.py`,
`tools/validate_tutorial_coverage.py`, and all 51 examples of
`tools/run_local_examples.py`, including `examples/adhoc/task_scope_volume.py`.
The earlier job 1090884 failed only on the test above and on the Docker and
Kubernetes modules, which were not installed yet.
