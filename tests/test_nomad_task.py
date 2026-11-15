"""Offline lifecycle tests for the Nomad backend: every HTTP call is mocked."""
import os
import unittest
from unittest import mock

from dagon.nomad_task import NomadTask, RemoteNomadTask
from dagon.task import DagonTask, TaskType


class _Response:
    def __init__(self, payload=None, status_code=200, text=""):
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.exceptions.HTTPError("status %d" % self.status_code)


def _task(**options):
    task = NomadTask("Analysis", "python run.py --input 'a b'", image="python:3.12",
                     nomad_address="http://nomad.invalid:4646/", cpu=500, memory=1024,
                     datacenter="edge", region="europe", **options)
    task.workflow = mock.Mock()
    return task


def _terminated(exit_code):
    return [{"ID": "alloc-1", "TaskStates": {"dagon-task": {
        "State": "dead", "Events": [{"Type": "Started"}, {"Type": "Terminated", "ExitCode": exit_code}]}}}]


class NomadJobSpecificationTests(unittest.TestCase):
    def test_factory_selects_local_and_remote_variants(self):
        self.assertIsInstance(DagonTask(TaskType.NOMAD, "local", "hostname"), NomadTask)
        with mock.patch("dagon.remote.SSHManager"):
            remote = DagonTask(TaskType.NOMAD, "remote", "hostname", ip="192.0.2.30",
                               ssh_username="user", keypath="/tmp/key")
        self.assertIsInstance(remote, RemoteNomadTask)

    def test_job_specification_carries_image_command_resources_and_placement(self):
        task = _task()
        spec = task._generate_job_spec()["Job"]
        self.assertTrue(spec["ID"].startswith("dagon-analysis-"))
        self.assertEqual(spec["Type"], "batch")
        self.assertEqual(spec["Datacenters"], ["edge"])
        self.assertEqual(spec["Region"], "europe")
        group = spec["TaskGroups"][0]
        self.assertEqual(group["RestartPolicy"], {"Attempts": 0, "Mode": "fail"})
        config = group["Tasks"][0]["Config"]
        self.assertEqual(config["image"], "python:3.12")
        # The command is passed as one argument; JSON encoding, not shell quoting, preserves it.
        self.assertEqual(config["args"], ["-c", "python run.py --input 'a b'"])
        self.assertEqual(group["Tasks"][0]["Resources"], {"CPU": 500, "MemoryMB": 1024})
        self.assertEqual(task.nomad_address, "http://nomad.invalid:4646")

    def test_volume_without_container_path_is_mounted_at_the_same_path(self):
        spec = _task(volume="/data")._generate_job_spec()["Job"]
        self.assertEqual(spec["TaskGroups"][0]["Tasks"][0]["Config"]["volumes"], ["/data:/data"])


class NomadLifecycleTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch("dagon.nomad_task.time.sleep")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_submission_posts_once(self):
        task = _task()
        with mock.patch("dagon.nomad_task.requests.post", return_value=_Response({"EvalID": "e"})) as post:
            self.assertEqual(task._submit_job(), {"EvalID": "e"})
            task._submit_job()
        post.assert_called_once()
        self.assertEqual(post.call_args.args[0], "http://nomad.invalid:4646/v1/jobs")
        self.assertEqual(post.call_args.kwargs["json"]["Job"]["ID"], task.job_id)
        self.assertTrue(task.job_submitted)

    def test_failed_submission_is_reported(self):
        task = _task()
        with mock.patch("dagon.nomad_task.requests.post", return_value=_Response({}, status_code=500)):
            with self.assertRaisesRegex(Exception, "Failed to submit Nomad job"):
                task._submit_job()
        self.assertFalse(task.job_submitted)

    def _wait(self, task, responses):
        with mock.patch("dagon.nomad_task.requests.get", side_effect=responses) as get:
            return task._wait_for_completion(timeout=60), get

    def test_polling_reports_success_after_running_state(self):
        task = _task()
        task.job_id = "dagon-analysis-1"
        result, get = self._wait(task, [_Response({"Status": "running"}), _Response({"Status": "dead"}),
                                        _Response(_terminated(0))])
        self.assertEqual(result["code"], 0)
        self.assertEqual(task.allocation_id, "alloc-1")
        self.assertEqual(get.call_args.args[0], "http://nomad.invalid:4646/v1/job/dagon-analysis-1/allocations")

    def test_polling_propagates_a_nonzero_exit_code(self):
        task = _task()
        task.job_id = "dagon-analysis-1"
        result, _ = self._wait(task, [_Response({"Status": "dead"}), _Response(_terminated(3))])
        self.assertEqual(result["code"], 3)

    def test_dead_job_without_allocations_fails(self):
        task = _task()
        task.job_id = "dagon-analysis-1"
        result, _ = self._wait(task, [_Response({"Status": "dead"}), _Response([])])
        self.assertEqual(result["code"], 1)
        self.assertEqual(result["output"], "Job died")

    def test_polling_is_bounded_by_the_timeout(self):
        task = _task()
        task.job_id = "dagon-analysis-1"
        clock = iter([0.0, 0.0, 61.0])
        with mock.patch("dagon.nomad_task.time.time", side_effect=lambda: next(clock)), \
                mock.patch("dagon.nomad_task.requests.get", return_value=_Response({"Status": "pending"})):
            result = task._wait_for_completion(timeout=60)
        self.assertEqual(result, {"code": 1, "output": "Timeout", "message": "Job execution timeout"})

    def test_logs_need_an_allocation(self):
        task = _task()
        self.assertIn("no allocation ID", task._get_logs())
        task.allocation_id = "alloc-1"
        with mock.patch("dagon.nomad_task.requests.get", return_value=_Response(text="hello\n")) as get:
            self.assertEqual(task._get_logs(), "hello\n")
        self.assertEqual(get.call_args.kwargs["params"],
                         {"task": "dagon-task", "type": "stdout", "plain": "true"})

    def test_cleanup_purges_only_a_submitted_job(self):
        task = _task()
        with mock.patch("dagon.nomad_task.requests.delete") as delete:
            task._cleanup_job()
            delete.assert_not_called()
            task.job_id = "dagon-analysis-1"
            delete.return_value = _Response()
            task._cleanup_job()
        delete.assert_called_once_with("http://nomad.invalid:4646/v1/job/dagon-analysis-1",
                                       params={"purge": "true"}, timeout=10)


class RemoteNomadTests(unittest.TestCase):
    def test_default_and_custom_ssh_ports_and_derived_address(self):
        with mock.patch("dagon.remote.SSHManager") as manager:
            default = RemoteNomadTask("r1", "hostname", ip="192.0.2.30", ssh_username="user", keypath="/tmp/key")
            custom = RemoteNomadTask("r2", "hostname", ip="192.0.2.30", ssh_username="user",
                                     keypath="/tmp/key", ssh_port=2200)
        self.assertEqual(default.nomad_address, "http://192.0.2.30:4646")
        self.assertEqual((default.ssh_port, custom.ssh_port), (22, 2200))
        manager.assert_any_call("user", "192.0.2.30", os.path.abspath("/tmp/key"), port=22)
        manager.assert_any_call("user", "192.0.2.30", os.path.abspath("/tmp/key"), port=2200)


if __name__ == "__main__":
    unittest.main()
