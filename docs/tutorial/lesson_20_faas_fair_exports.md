# Lesson 20: inspect FAIR, JSON, and CWL FaaS records

Prerequisite: Lessons 15–17. Enable a local FAIR profile as in Lesson 15, add the
mock task from Lesson 16, and run it. `run.json` contains `execution.model="faas"`,
attempt data, and the mock request ID. RO-Crate links the `CreateAction` to a
provider-neutral deployed-function service; materialized outputs include size and
SHA-256.

Run `python3 examples/faas/export.py` to produce workflow JSON and CWL. The CWL
step uses `python -m dagon.faas_runner` plus a namespaced hint. Search all exports
for a marker secret as an exercise; it must be absent. JSON/CWL describe invocation,
not function deployment. Delete the two export files and FAIR output directory
for cleanup. If CWL validation fails, confirm the document is v1.2 and that the
validator accepts namespaced hints.
