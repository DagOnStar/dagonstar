"""Lesson 19: Kubernetes pod lifecycle with the Kubernetes client mocked."""
import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
from unittest import mock

try:
    from dagon.kubernetes_task import KubernetesTask
except ImportError as error:  # the kubernetes extra is optional
    print("skipped (optional kubernetes extra not installed):", error)
    raise SystemExit(0)
from dagon.task import DagonTask, TaskType

with mock.patch("dagon.kubernetes_task.config.load_kube_config"), \
        mock.patch("dagon.kubernetes_task.client.CoreV1Api") as api_class:
    api = api_class.return_value
    task = DagonTask(TaskType.KUBERNETES, "simulate", "python simulate.py", image="python:3.12-slim",
                     namespace="research", remove=True)
    assert isinstance(task, KubernetesTask)
    task.workflow = mock.Mock()
    running = mock.Mock()
    running.status.phase = "Running"
    running.status.pod_ip = "10.0.0.5"
    api.read_namespaced_pod.return_value = running
    task.create_pod()
    api.create_namespaced_pod.assert_called_once()
    call = api.create_namespaced_pod.call_args
    namespace = call.kwargs.get("namespace", call.args[0] if call.args else None)
    assert namespace == "research", call
    pod_ip, pod_name = task.info["ip"], task.pod_name
    assert pod_ip == "10.0.0.5" and pod_name
    task.remove_pod()
    assert api.delete_namespaced_pod.called, "remove=True deletes the pod"
print("pod", pod_name, "created in", namespace, "at", pod_ip, "and deleted (mocked API)")
