# Lesson 12: Run an LLM Task Locally

## Objective

Build a two-task workflow that produces a text report, passes it to an
OpenAI-compatible LLM request through `workflow://`, and saves the JSON reply.
The lesson uses a local mock provider, so it is repeatable without credentials
or Internet access.

## What you will learn

- how `TaskType.LLM` receives a JSON Chat Completions request;
- how named prompt parameters work;
- how `input_files` makes a `workflow://` producer file available as prompt
  text and creates the dependency automatically;
- where the LLM response is stored; and
- how to replace the mock configuration with a real provider safely.

## Step 1: Run the complete local example

From the repository root, run:

```bash
python3 examples/llm/local_mock_llm.py
```

The program starts an HTTP server bound only to `127.0.0.1` on an unused port.
It is a small OpenAI-compatible `/v1/chat/completions` implementation created
solely for the example. The program shuts it down when the workflow completes.

Expected output is JSON containing a completion like:

```json
{"choices": [{"message": {"content": "Mock summary: Summarize this report: temperature increased by 1.2 C"}}]}
```

The exact whitespace and additional JSON fields are not important.

## Step 2: Create the producer task

The first task writes a report inside its own task directory:

```python
produce = DagonTask(
    TaskType.BATCH,
    "prepare_report",
    "mkdir -p output; printf 'temperature increased by 1.2 C' > output/report.txt",
)
```

Its eventual file location is conceptually:

```text
<prepare_report task directory>/output/report.txt
```

Do not pass that absolute path to the LLM task. It is generated at runtime and
would make the workflow non-portable.

## Step 3: Declare the JSON request and file attachment

Create the LLM task with a JSON-compatible request object:

```python
summarize = DagonTask(
    TaskType.LLM,
    "summarize_report",
    {"messages": [{"role": "user", "content": "Summarize this report: {report}"}]},
    provider="local_mock",
    input_files={"report": "workflow:///prepare_report/output/report.txt"},
)
```

`{report}` is a prompt parameter. `input_files` gives it a value by referring
to the producer file with the normal schema:

```text
workflow:///<producer-task>/<path-inside-producer-directory>
```

When DAGonStar builds dependencies, it recognizes the reference and creates:

```text
prepare_report -> summarize_report
```

Before sending the request, the LLM task copies the UTF-8 file into:

```text
<summarize_report task directory>/.dagon/inputs/LocalMockLLM/prepare_report/output/report.txt
```

It then replaces `{report}` with the copied file’s text. An inline
`workflow:///prepare_report/output/report.txt` in a prompt string works too,
but `input_files` keeps longer prompts readable.

## Step 4: Configure the local provider

The example builds configuration in Python because the mock server selects a
free port at runtime:

```python
"llm.local_mock": {
    "endpoint": "http://127.0.0.1:%s" % server.server_port,
    "api_key": "example-key-not-a-secret",
    "model": "mock-chat",
}
```

Provider section names use `llm.<provider-name>`, and the task’s `provider`
argument selects the suffix. The example key is accepted only by the local mock;
it is not a credential.

## Step 5: Run and inspect the response

After adding both tasks, run the workflow:

```python
workflow.add_task(produce)
workflow.add_task(summarize)
workflow.run()
```

`Workflow.run()` builds missing dependencies automatically. On completion,
`summarize.working_dir` identifies the LLM task directory and the response is:

```python
response_path = Path(summarize.working_dir, "response.json")
print(response_path.read_text(encoding="utf-8"))
```

The complete JSON response is deliberately retained, rather than only the
assistant text, so a downstream task can extract provider-specific metadata or
choices with its own deterministic program.

## Step 6: Use a real provider

For a real OpenAI-compatible service, keep the workflow request unchanged and
create an ignored local `dagon.ini`:

```ini
[llm.research]
endpoint=https://api.example.org
api_key_env=DAGON_RESEARCH_LLM_KEY
model=research-chat
```

Then set the key in the shell and choose `provider="research"`:

```bash
export DAGON_RESEARCH_LLM_KEY=...
```

Never commit the key or replace the safe sample configuration with a real one.
The current LLM task accepts local UTF-8 text file inputs; binary uploads and
remote-only producer files are outside its supported behavior.

## Verify

Run the example again. It is successful when it exits with status zero and the
printed response includes both `Mock summary:` and the report text. For a
regression check, run:

```bash
python3 -m unittest tests.test_llm -v
```

## Scientific practice note

Record the provider name, model, prompt template, and source input files in
your workflow source. Preserve `response.json` as a workflow output. This makes
AI-assisted interpretation inspectable, while keeping secret credentials out of
the workflow and repository.
