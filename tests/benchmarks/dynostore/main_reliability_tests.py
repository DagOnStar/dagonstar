import time
import os
import json
from dagon import Workflow
from dagon.task import DagonTask, TaskType

def simulate_writer_failure(ip: str):
    print(f"[SIMULATION] Disconnecting writer node {ip}")
    # Block SSH access temporarily (requires firewall or admin rights).
    # You can also simulate with a sleep to represent unavailability,
    # or by removing access from known_hosts, etc.
    # For real clusters: deactivate or shut down the writer VM
    os.system(f"ssh -o StrictHostKeyChecking=no ubuntu@{ip} 'sudo shutdown -h now'")

def run_resilience_test(dagonini="dagon-dynostore.ini"):
    wf_label = "resilience-failure-test"
    workflow = Workflow(wf_label, config_file=dagonini)
    workflow.set_dry(False)

    writer_ip = "13.48.57.155"
    writer_key = "/home/cc/key_node_aws.key"
    reader_ip = "129.114.108.6"
    reader_key = "/home/cc/key_node.key"

    # Write task on Node A
    write_task = DagonTask(
        TaskType.BATCH,
        "write_0",
        "dd if=/dev/urandom of=file0.bin bs=1M count=100",
        ssh_username="ubuntu", ip=writer_ip, keypath=writer_key
    )
    workflow.add_task(write_task)

    # Consumer on Node B
    read_task = DagonTask(
        TaskType.BATCH,
        "hash_0",
        "md5sum workflow:///write_0/file0.bin > hash_0.txt",
        ssh_username="cc", ip=reader_ip, keypath=reader_key
    )
    workflow.add_task(read_task)
    

    # Save and run workflow
    json_path = f"{wf_label}.json"
    with open(json_path, 'w') as f:
        json.dump(workflow.as_json(), f, indent=2)

    # print(f"\n>>> Step 1: Uploading data from writer node...")
    # workflow.run_task("write_0")

    # print("✅ Upload complete. Waiting for data to register in DynoStore...\n")
    # time.sleep(5)

    # # Simulate failure
    # simulate_writer_failure(writer_ip)

    # print("\n>>> Step 2: Running consumer task after writer node is gone...")
    # start = time.time()
    # workflow.run_task("hash_0")
    # end = time.time()

    # print(f"\n✅ Consumer task completed in {end - start:.2f}s")
    # print("✅ Workflow survived node failure ✅")
    print(f"\n>>> Running workflow: {wf_label}")
    start = time.time()
    workflow.make_dependencies()
    workflow.run()
    end = time.time()
    print(f"<<< Completed: {wf_label} in {end - start:.2f} seconds\n")


if __name__ == "__main__":
    run_resilience_test()
