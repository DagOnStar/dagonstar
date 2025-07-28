from dagon import Workflow
from dagon.task import DagonTask, TaskType
import json
import time
import csv
import os
from collections import defaultdict
import statistics



def create_and_run_workflow(object_size_mb: int, num_objects: int, label: str = "", dry_run=False, dagonini: str = "dagon.ini"):
    wf_label = f"Microbench-{label or f'{object_size_mb}MB-{num_objects}files'}"
    workflow = Workflow(wf_label,config_file=dagonini)
    workflow.set_dry(dry_run)

    write_tasks = []
    hash_tasks = []

    for i in range(num_objects):
        write_id = f"write_{i}"
        write_cmd = f"dd if=/dev/urandom of=file{i}.bin bs=1M count={object_size_mb}"
        task_write = DagonTask(TaskType.BATCH, write_id, write_cmd)
        workflow.add_task(task_write)
        write_tasks.append(write_id)

        hash_id = f"hash_{i}"
        hash_cmd = f"md5sum workflow:///{write_id}/file{i}.bin > hash_{i}.txt"
        task_hash = DagonTask(TaskType.BATCH, hash_id, hash_cmd)
        workflow.add_task(task_hash)
        hash_tasks.append(hash_id)

    # Final aggregation task
    agg_cmd = "cat " + " ".join([f"workflow:///{hid}/hash_{i}.txt" for i, hid in enumerate(hash_tasks)]) + " > final.txt"
    task_agg = DagonTask(TaskType.BATCH, "aggregate", agg_cmd)
    workflow.add_task(task_agg)

    # Save JSON file
    json_path = f"{wf_label}.json"
    with open(json_path, 'w') as f:
        json.dump(workflow.as_json(), f, indent=2)

    print(f"\n>>> Running workflow: {wf_label}")
    start = time.time()
    workflow.run()
    end = time.time()
    print(f"<<< Completed: {wf_label} in {end - start:.2f} seconds\n")
    return end - start

def append_to_csv(csv_path: str, config: str, test_config: dict, duration: float, iteration: int):
    file_exists = os.path.isfile(csv_path)
    with open(csv_path, 'a', newline='') as csvfile:
        fieldnames = ["label", "config", "object_size_MB", "num_objects", "iteration", "total_time_s", "avg_time_per_object_s"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            "label": test_config["label"],
            "config": config,
            "object_size_MB": test_config["object_size_mb"],
            "num_objects": test_config["num_objects"],
            "iteration": iteration,
            "total_time_s": duration,
            "avg_time_per_object_s": duration / test_config["num_objects"]
        })


def write_summary_csv(input_csv: str, summary_csv: str):
    grouped = defaultdict(list)
    with open(input_csv, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (row["label"], row["config"], int(row["object_size_MB"]), int(row["num_objects"]))
            grouped[key].append(float(row["total_time_s"]))

    with open(summary_csv, 'w', newline='') as f:
        fieldnames = ["label", "config", "object_size_MB", "num_objects", "mean_total_time_s", "std_total_time_s"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for (label, config, size, count), durations in grouped.items():
            writer.writerow({
                "label": label,
                "config": config,
                "object_size_MB": size,
                "num_objects": count,
                "mean_total_time_s": round(statistics.mean(durations), 2),
                "std_total_time_s": round(statistics.stdev(durations), 2) if len(durations) > 1 else 0.0
            })


if __name__ == '__main__':
    output_csv = "microbench_results.csv"
    summary_csv = "microbench_summary.csv"
    iterations = 1

    #configurations = ["dagon-dynostore.ini"]  # ["dagon.ini", "dagon-dynostore.ini"]
    configurations = ["dagon.ini", "dagon-dynostore.ini"]

    tests = [
        {"object_size_mb": 10, "num_objects": 3, "label": "small"},
        {"object_size_mb": 50, "num_objects": 3, "label": "medium"},
        {"object_size_mb": 100, "num_objects": 3, "label": "large"},
    ]

    for config in configurations:
        for test in tests:
            for i in range(iterations):
                duration = create_and_run_workflow(**test, dagonini=config)
                append_to_csv(output_csv, config, test, duration, iteration=i)

    # Create summary with std
    write_summary_csv(output_csv, summary_csv)