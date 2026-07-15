# LLM Task Example

Source directory: [`examples/llm`](../../examples/llm)

`local_mock_llm.py` is a locally verifiable end-to-end LLM workflow. It starts a
temporary OpenAI-compatible HTTP mock, runs a batch producer, attaches its text
output through `workflow://`, and writes the JSON completion to `response.json`.
It does not contact an external service or need credentials.

```bash
python3 examples/llm/local_mock_llm.py
```

`llm-demo.py` is a real-provider skeleton and requires a locally configured
`[llm.example]` provider. See [LLM Tasks](../llm_tasks.md) for configuration and
[Lesson 11](../tutorial/lesson_11_execute_an_llm_task_responsibly.md) for the incremental explanation.
