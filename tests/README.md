# Container Tasks Tests

This document describes how to run the unit tests and explains what each test file does.

## Requirements

```bash
pip install pytest pytest-cov
```

Or if you prefer to use `unittest` directly (no additional installation required):
```bash
python -m unittest discover
```

## Running Tests

### Run all tests

```bash
# With pytest (recommended)
pytest

# With unittest
python -m unittest discover

# Run a specific file
python -m unittest test_apptainer_task
python -m unittest test_docker_task
python -m unittest test_kubernetes_task
```

### Run tests with coverage

```bash
pytest --cov=dagon --cov-report=html
```

### Run a specific test

```bash
# With pytest
pytest test_apptainer_task.py::TestApptainerTask::test_create_container_success

# With unittest
python -m unittest test_apptainer_task.TestApptainerTask.test_create_container_success
```

## Test Structure

### 1. `test_apptainer_task.py`

Tests the `ApptainerTask` and `RemoteApptainerTask` classes that manage Apptainer/Singularity containers.

#### `TestApptainerTask`
Tests for local Apptainer container execution:

- **`test_create_container_success`**: Verifies successful container creation, including generation of IDs, SIF files, and overlays.

- **`test_prepare_sif_image_existing_file`**: Checks that if a local SIF file already exists, it's reused without rebuilding.

- **`test_prepare_sif_image_build_from_docker`**: Verifies building a SIF image from Docker Hub using `apptainer build`.

- **`test_create_overlay`**: Checks creation of an overlay file for persistent storage in the container.

- **`test_exec_in_container`**: Verifies command execution inside the container using `apptainer exec`.

- **`test_export_file_to_staging`**: Checks exporting files from the container to a staging area.

- **`test_import_file_from_staging`**: Verifies importing files from staging into the container.

- **`test_stage_in_success`**: Tests file transfer between containers using staging as an intermediary.

- **`test_cleanup_container`**: Verifies cleanup of temporary files when `remove=True`.

- **`test_on_execute_success`**: Checks complete task execution inside the container.

- **`test_on_garbage`**: Verifies that `cleanup_container` is called during garbage collection.

#### `TestRemoteApptainerTask`
Tests for remote execution via SSH:

- **`test_run_apptainer_command_success/failure`**: Verifies execution of Apptainer commands on remote machines.

- **`test_create_remote_container`**: Checks container creation on remote hosts.

- **`test_prepare_sif_image_remote_existing/build`**: Verifies using and building SIF images on remote machines.

- **`test_exec_in_remote_container`**: Tests command execution in remote containers.

- **`test_export/import_file_to_remote_staging`**: Verifies file transfer in remote environments.

- **`test_remote_stage_in`**: Checks file copying between remote containers.

- **`test_cleanup_remote_container`**: Verifies resource cleanup on remote machines.

- **`test_remote_on_execute`**: Tests complete remote task execution.

### 2. `test_docker_task.py`

Tests the `DockerTask` and `DockerRemoteTask` classes for Docker container management.

#### `TestDockerTask`
Tests for local Docker operations:

- **`test_pull_image_success/failure`**: Verifies Docker image pulling.

- **`test_create_container_success/failure`**: Checks Docker container creation.

- **`test_get_running_container_success/failure`**: Verifies obtaining references to running containers.

- **`test_remove_container_with_remove_true/false`**: Tests conditional container stopping and removal.

- **`test_include_command_adds_exec_string`**: Verifies correct formatting of `docker exec` commands.

- **`test_on_execute_runs_batch`**: Checks script execution inside the container.

- **`test_on_garbage_removes_container`**: Verifies cleanup during garbage collection.

#### `TestDockerRemoteTask`
Tests for Docker on remote hosts:

- **`test_on_execute_runs_remote_command`**: Verifies Docker command execution via SSH.

- **`test_on_garbage_cleans_remote`**: Checks remote resource cleanup.

### 3. `test_kubernetes_task.py`

Tests the `KubernetesTask` and `RemoteKubernetesTask` classes for Kubernetes pod management.

#### `TestKubernetesTask`
Tests for local Kubernetes operations:

- **`test_create_pod_success`**: Verifies pod creation and waits until it's in "Running" state.

- **`test_exec_in_pod`**: Checks command execution inside a pod using the Kubernetes API.

- **`test_stage_in_success`**: Verifies file copying between pods using `cat` and redirection.

- **`test_remove_pod_force_delete`**: Tests forced pod deletion when standard deletion fails.

#### `TestRemoteKubernetesTask`
Tests for Kubernetes on remote clusters:

- **`test_run_kubectl_command_success/failure`**: Verifies `kubectl` command execution via SSH.

- **`test_exec_in_remote_pod`**: Checks command execution in remote pods using `kubectl exec`.

- **`test_remove_remote_pod`**: Verifies pod deletion in remote clusters.

## Test Implementation

### Techniques Used

1. **Mocking**: All tests use `unittest.mock` to simulate:
   - Docker and Kubernetes clients
   - SSH connections
   - System processes (`subprocess.run`)
   - File system operations (`os.path.exists`, `shutil.rmtree`)

2. **Patching**: External resource calls are intercepted:
   - `@patch("dagon.docker_task.docker.from_env")`
   - `@patch("dagon.kubernetes_task.config.load_kube_config")`
   - `@patch("dagon.apptainer_task.subprocess.run")`

3. **Fixtures**: Each test class has a `setUp()` method that initializes:
   - Workflow mocks
   - Task instances
   - Simulated connections

### Typical Test Structure

```python
@patch("module.external_call")  # Intercept external calls
def test_feature(self, mock_external):
    # Arrange: Configure the mock
    mock_external.return_value = "expected_value"
    
    # Act: Execute the functionality
    result = self.task.some_method()
    
    # Assert: Verify results
    self.assertEqual(result, "expected_value")
    mock_external.assert_called_once()
```

## Expected Coverage

The tests cover:
- ✅ Container/pod creation and management
- ✅ Command execution
- ✅ File transfer between containers
- ✅ Resource cleanup
- ✅ Error handling
- ✅ Local and remote operations

## Important Notes

- All tests are **unit tests** and don't require Docker, Kubernetes, or Apptainer installed
- Tests **don't create real resources** (containers, pods, files)
- **Mocks** are used to simulate all interactions with external systems
- Tests verify **business logic** and **correct API calls**

## Test Organization

Each test file follows this structure:

```
test_<technology>_task.py
├── TestLocalTask
│   ├── setUp()              # Initialize mocks and task instance
│   ├── test_feature_1()     # Test specific functionality
│   ├── test_feature_2()     # Test error handling
│   └── ...
└── TestRemoteTask
    ├── setUp()              # Initialize SSH mocks
    ├── test_remote_feature() # Test remote operations
    └── ...
```

## Debugging Tests

To run tests with verbose output:

```bash
# With pytest
pytest -v

# With unittest
python -m unittest -v test_apptainer_task
```

To run a single test with debugging:

```bash
python -m pdb -m unittest test_apptainer_task.TestApptainerTask.test_create_container_success
```

## Contributing

When adding new tests:
1. Follow the existing naming convention: `test_<feature>_<scenario>`
2. Mock all external dependencies
3. Use descriptive docstrings
4. Test both success and failure scenarios
5. Verify cleanup operations