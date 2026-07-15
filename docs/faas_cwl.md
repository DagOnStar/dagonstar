# FaaS CWL export

CWL v1.2 has no universal FaaS execution class. `Workflow.saveAsCWL()` therefore
exports a standards-based `CommandLineTool` that runs:

```text
python -m dagon.faas_runner --spec faas-task.json
```

`InitialWorkDirRequirement` creates the provider-neutral specification, while the
namespaced `dagon:FaaSInvocation` hint preserves provider, profile, and function
identity. Inferred dependencies remain ordinary CWL step connections, so mixed
workflows retain their existing non-FaaS tools.

The export contains no resolved credentials or scratch paths. A CWL runtime still
needs DAGonStar, the selected optional provider dependency, provider-standard
credentials, and access to the deployed function. This preserves command-graph
structure and invocation semantics; it does not make the deployment portable or
recreate cloud infrastructure.

Validate a generated document with an installed CWL validator, for example
`cwltool --validate workflow.cwl`. The base DAGonStar installation does not depend
on `cwltool`.
