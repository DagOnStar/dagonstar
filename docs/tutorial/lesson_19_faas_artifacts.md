# Lesson 19: connect workflow artifacts to FaaS

Prerequisite: Lesson 18. Put references at any nested input depth:

```python
inputs={"members": [{"source": "workflow:///prepare/outputs/input.json"}]}
```

No explicit dependency call is needed. `make_dependencies()` discovers the edge;
execution copies the file below `inputs/<workflow>/<task>/` and replaces the
logical value in `faas_request.json` with a descriptor containing the task-relative
path, media type, size, and SHA-256. Scalar JSON remains inline.

As an exercise, add two producers and inspect the two inferred predecessors.
Then consume `workflow:///invoke/outputs/result.json` from a Native or Batch task.
Clean up scratch data afterward. A missing producer fails dependency construction;
a missing producer file fails staging. Remote functions cannot use local-file
descriptors—use an already accessible object reference until object upload support
is added.
