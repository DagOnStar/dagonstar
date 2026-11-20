# Compute-continuum operations

An IoT `compute` task declares an artifact/runtime and device, gateway, edge, or cloud placement preferences. DAGonStar owns workflow dependencies and evidence; provider adapters or external orchestrators own discovery, deployment, and migration. Results record requested/selected targets, tier, placement, migrations, and protocol metadata. Mock placement is deterministic and does not claim real deployment.

An agentic task can sit between edge and serverless stages: Lesson 33
(`examples/tutorial/lesson_33_compute_continuum.py`) chains IoT observation,
a Native normalisation step, an agentic quality-control step, and a FaaS
publication, all with deterministic mocks. See [Agentic tasks](agentic_tasks.md).
