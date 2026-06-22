# LLM task examples

`local_mock_llm.py` is a fully local, end-to-end example. It starts a temporary
OpenAI-compatible mock provider, produces a report with a batch task, attaches
that report to an LLM request with `workflow://`, and prints `response.json`.
It needs no credentials, network connection, or `dagon.ini`:

```bash
python3 examples/llm/local_mock_llm.py
```

`llm-demo.py` is the corresponding real-provider skeleton. Copy
`dagon.ini.sample` to an ignored local `dagon.ini`, configure `[llm.example]`
and `DAGON_LLM_EXAMPLE_API_KEY`, then run it.

See [LLM Tasks](../../docs/llm_tasks.md) for JSON prompts and `workflow://`
text-file inputs.
