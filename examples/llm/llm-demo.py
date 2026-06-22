"""Requires a local [llm.example] configuration."""
from dagon import Workflow
from dagon.task import DagonTask, TaskType

workflow = Workflow("llm-demo")
workflow.add_task(DagonTask(
    TaskType.LLM, "ask",
    {"messages": [{"role": "user", "content": "Write a haiku about {topic}."}]},
    provider="example", params={"topic": "scientific workflows"},
))
workflow.run()
