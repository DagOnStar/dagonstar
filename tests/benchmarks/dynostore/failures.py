import subprocess
import time
import csv
import argparse
from datetime import datetime
from dynostore import client

dyno_client = client.Client(metadata_server="192.5.86.169")

def run_dynostore_get(server, object_key, output_prefix, repeats, csv_file):
    results = []

    for i in range(1, repeats + 1):
        print(f"Running test {i}")
        output_file = f"{output_prefix}_{i}"
        cmd = [
            "dynostore",
            "--server", server,
            "get", object_key,
            "--output", output_file
        ]
        
        start = time.perf_counter()
        try:
            data = dyno_client.get(object_key)
            success = data is not None
            end = time.perf_counter()
            duration = round(end - start, 4)
            
        except Exception as e:
            print("ENTRO",e)
            end = time.perf_counter()
            duration = round(end - start, 4)
            success = False

        results.append({
            "iteration": i,
            "start_time": datetime.now().isoformat(),
            "duration_sec": duration,
            "success": success
        })

    # Write results to CSV
    with open(csv_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["iteration", "start_time", "duration_sec", "success"])
        writer.writeheader()
        writer.writerows(results)

    print(f"Completed {repeats} runs. Results saved to {csv_file}.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", required=True, help="DynoStore server address")
    parser.add_argument("--object", required=True, help="Object key to retrieve")
    parser.add_argument("--output_prefix", default="a", help="Prefix for output files")
    parser.add_argument("--repeats", type=int, default=10, help="Number of repetitions")
    parser.add_argument("--csv", default="results.csv", help="Output CSV file")
    args = parser.parse_args()

    run_dynostore_get(args.server, args.object, args.output_prefix, args.repeats, args.csv)
