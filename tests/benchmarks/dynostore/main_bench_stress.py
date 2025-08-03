from dagon import Workflow
from dagon.task import DagonTask, TaskType
import json
import time
import csv
import os
import shutil
from collections import defaultdict
import statistics


def create_and_run_multi_consumer(object_size_mb: int, num_consumers: int, label: str = "", dry_run=False, dagonini: str = "dagon.ini"):
    wf_label = f"ReuseTest-{label or f'{object_size_mb}MB-{num_consumers}consumers'}"
    workflow = Workflow(wf_label, config_file=dagonini)
    workflow.set_dry(dry_run)

    # One write task
    write_id = "write_0"
    write_cmd = f"dd if=/dev/urandom of=file0.bin bs=1M count={object_size_mb}"
    task_write = DagonTask(TaskType.BATCH, write_id, write_cmd, ssh_username="ubuntu", ip="13.51.207.137", keypath="/home/cc/key_node_aws.key")
    workflow.add_task(task_write)

    consumer_tasks = []

    for i in range(num_consumers):
        hash_id = f"hash_{i}"
        hash_cmd = f"md5sum workflow:///{write_id}/file0.bin > hash_{i}.txt"
        task_hash = DagonTask(TaskType.BATCH, hash_id, hash_cmd, ssh_username="cc", ip="129.114.108.6", keypath="/home/cc/key_node.key")
        workflow.add_task(task_hash)
        consumer_tasks.append(hash_id)

    agg_cmd = "cat " + " ".join([f"workflow:///{hid}/hash_{i}.txt" for i, hid in enumerate(consumer_tasks)]) + " > final.txt"
    task_agg = DagonTask(TaskType.BATCH, "aggregate", agg_cmd)
    workflow.add_task(task_agg)

    json_path = f"{wf_label}.json"
    with open(json_path, 'w') as f:
        json.dump(workflow.as_json(), f, indent=2)

    print(f"\n>>> Running workflow: {wf_label}")
    start = time.time()
    workflow.make_dependencies()
    workflow.run()
    end = time.time()
    print(f"<<< Completed: {wf_label} in {end - start:.2f} seconds\n")

    # Save individual task durations
    task_times = workflow.get_task_times()
    csv_path = f"{wf_label}_task_times.csv"
    with open(csv_path, 'a', newline='') as csvfile:
        fieldnames = ["task_id", "duration"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for task_id, times in task_times.items():
            writer.writerow({"task_id": task_id, "duration": times})

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
    output_csv = "microbench_results-stress.csv"
    summary_csv = "microbench_summary-stress.csv"
    iterations = 2

    #configurations = ["dagon-dynostore.ini"]  # ["dagon.ini", "dagon-dynostore.ini"]
    configurations = ["dagon.ini", "dagon-dynostore.ini"]
    #configurations = ["dagon.ini"]

    # tests = [
    #     # Vary object size, keep readers fixed
    #     # {"object_size_mb": 1, "num_objects": 10, "label": "small"},
    #     # {"object_size_mb": 50, "num_objects": 10, "label": "medium"},
    #     # {"object_size_mb": 100, "num_objects": 10, "label": "large"},
    #     # {"object_size_mb": 500, "num_objects": 10, "label": "xlarge"},
    #     # {"object_size_mb": 1000, "num_objects": 10, "label": "xxlarge"},

    #     # Vary consumers, fixed object size (scaling test)
    #     #{"object_size_mb": 100, "num_objects": 1, "label": "readers1"}#,
    #     # {"object_size_mb": 100, "num_objects": 5, "label": "readers5"},
    #     # {"object_size_mb": 100, "num_objects": 10, "label": "readers10"},
    #     # {"object_size_mb": 100, "num_objects": 20, "label": "readers20"},
    #     {"object_size_mb": 100, "num_objects": 100, "label": "readers100"}
    # ]


    # for config in configurations:
    #     for test in tests:
    #         for i in range(iterations):
    #             os.makedirs('/home/cc/dagonstar/tests/benchmarks/dynostore/dagonresults', exist_ok=True)
    #             duration = create_and_run_multi_consumer(
    #                 object_size_mb=test["object_size_mb"],
    #                 num_consumers=test["num_objects"],
    #                 label=test["label"],
    #                 dagonini=config
    #             )
    #             append_to_csv(output_csv, config, test, duration, iteration=i)
    #             shutil.rmtree('/home/cc/dagonstar/tests/benchmarks/dynostore/dagonresults')

    write_summary_csv(output_csv, summary_csv)