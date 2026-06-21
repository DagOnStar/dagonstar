# Lesson 13: Run Web Tasks

`TaskType.WEB` makes an HTTP/HTTPS request a DAGonStar task. Its structured request runs in task scratch, so local or Slurm execution can place the HTTP call where network access is available.

```python
DagonTask(TaskType.WEB, "fetch", {"method": "GET", "url": "https://example.org/data", "outputs": {"body": "data.json"}})
```

Use `workflow://` values in request specifications. Use `{"file": "workflow:///prepare/data.csv"}` for file uploads and `text` or `json_file` wrappers to read staged values. Files go below `inputs/`, responses below `outputs/`, and `.dagon/web_result.json` holds safe metadata. Bearer, basic, and API-key auth take environment-variable names only; never hardcode tokens. See the [web example](../../examples/web/README.md).
