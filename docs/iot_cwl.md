# IoT and CWL

`Workflow.saveAsCWL()` represents IoT as a CWL v1.2 `CommandLineTool` invoking `dagon-iot-runner`. Its portable specification uses `InitialWorkDirRequirement`; declared outputs use file globs, and a `dagon:IoTTask` hint preserves semantics.

The graph is portable, but execution requires DAGonStar's runner, the selected provider, runtime credentials, and reachable devices. Generic CWL software may ignore the hint. Credentials are resolved at runtime and are never embedded.
