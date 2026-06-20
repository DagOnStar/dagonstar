"""A fully local two-task FAIR-by-design DAGonStar example."""
from dagon import Workflow
from dagon.task import DagonTask, TaskType
from dagon.fair import AccessPolicy, Agent, Artifact, FairProfile

workflow = Workflow("FAIR-Demo")
workflow.enable_fair(FairProfile(title="DAGonStar FAIR demo", description="A two-task local FAIR workflow.",
    creators=[Agent(name="DAGonStar Team")], license="Apache-2.0", keywords=["FAIR", "provenance"],
    access_policy=AccessPolicy(metadata="public", data="local")))
first = DagonTask(TaskType.BATCH, "A", "mkdir -p output; echo hello > output/message.txt").declare_outputs(
    Artifact("output/message.txt", name="Message", media_type="text/plain", license="Apache-2.0"))
second = DagonTask(TaskType.BATCH, "B", "cat workflow:///A/output/message.txt > copied-message.txt").declare_outputs(
    Artifact("copied-message.txt", name="Copied message", media_type="text/plain", license="Apache-2.0"))
workflow.add_task(first); workflow.add_task(second); workflow.run()
