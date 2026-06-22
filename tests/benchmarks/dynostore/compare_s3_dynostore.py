import boto3
import time
import os
import uuid
import csv
import statistics
import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

from dynostore import client

AWS_BUCKET = "mydynobucket2"
AWS_REGION = "us-west-1"
DYNOSTORE_NAMESPACE = "benchmark"
REPEATS = 10
FILE_SIZES_MB = {1} #[1, 10, 100]

s3 = boto3.client("s3", region_name=AWS_REGION)
dyno_client = client.Client(metadata_server="192.5.86.169")

def generate_file(path, size_mb):
    print(f"Generating {size_mb}MB file at {path}...")
    with open(path, "wb") as f:
        f.write(os.urandom(size_mb * 1024 * 1024))

def time_s3_upload(file_path, object_key):
    start = time.time()
    s3.upload_file(file_path, AWS_BUCKET, object_key)
    return time.time() - start

def time_s3object_upload(file_path, object_key):
    with open(file_path, "rb") as f:
        data = f.read()
    start = time.time()
    s3.put_object(Bucket=AWS_BUCKET, Key=object_key, Body=data)
    return time.time() - start

def time_s3_download(object_key, local_path):
    start = time.time()
    s3.download_file(AWS_BUCKET, object_key, local_path)
    return time.time() - start

def time_dynostore_push(file_path):
    print(f"Pushing {file_path} into Dynostore...")
    with open(file_path, 'rb') as f:
        data = f.read()
    start = time.time()
    result = dyno_client.put(data=data, catalog="test", name=os.path.basename(file_path))
    return time.time() - start, result["key_object"]

def time_dynostore_pull(dyno_key, out_path):
    start = time.time()
    print(dyno_key)
    data = dyno_client.get(dyno_key)
    if data is not None:
        with open(out_path, 'wb') as f:
            f.write(data)
    return time.time() - start

def record_result(writer, system, operation, size_mb, iteration, client_id, elapsed_time):
    writer.writerow({
        "system": system,
        "operation": operation,
        "file_size_mb": size_mb,
        "iteration": iteration,
        "client_id": client_id,
        "time_sec": round(elapsed_time, 4)
    })

def run_tests(backends, operation_mode="both", concurrent_upload=False, concurrent_download=False, num_clients=4):
    suffix_parts = [
        "-".join(sorted(backends)),
        f"{num_clients}clients",
        operation_mode,
        "cu" if concurrent_upload else "su",
        "cd" if concurrent_download else "sd"
    ]
    suffix = "_".join(suffix_parts)
    csv_file = f"results_{suffix}.csv"
    summary_file = f"summary_{suffix}.csv"

    os.makedirs("temp_outputs", exist_ok=True)
    all_times = []

    with open(csv_file, "w", newline="") as csvfile:
        fieldnames = ["system", "operation", "file_size_mb", "iteration", "client_id", "time_sec"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        for size in FILE_SIZES_MB:
            fname = f"testfile-{uuid.uuid4().hex}-{size}MB.bin"
            generate_file(fname, size)

            print(f"\n--- Testing {size}MB with {num_clients} concurrent clients ---")

            for rep in range(REPEATS):
                object_keys = [f"{fname}_rep{rep}_client{c}" for c in range(num_clients)]
                dyno_keys = [None] * num_clients

                if operation_mode in ["upload", "both"]:
                    print(f"\n[Repetition {rep+1}] Upload Phase")

                    def s3_upload_task(c):
                        t = time_s3_upload(fname, object_keys[c])
                        return ("s3", "upload", size, rep + 1, c, t)

                    def s3object_upload_task(c):
                        t = time_s3object_upload(fname, object_keys[c])
                        return ("s3object", "upload", size, rep + 1, c, t)

                    def dyno_upload_task(c):
                        t, k = time_dynostore_push(fname)
                        return ("dynostore", "upload", size, rep + 1, c, t, k)

                    upload_futures = []
                    with ThreadPoolExecutor(max_workers=num_clients) as executor:
                        for c in range(num_clients):
                            if "s3" in backends:
                                upload_futures.append(executor.submit(s3_upload_task, c))
                            if "s3object" in backends:
                                upload_futures.append(executor.submit(s3object_upload_task, c))
                            if "dynostore" in backends:
                                upload_futures.append(executor.submit(dyno_upload_task, c))
                            if not concurrent_upload:
                                time.sleep(2)

                        for f in as_completed(upload_futures):
                            result = f.result()
                            if result[0] in ["s3", "s3object"]:
                                sys, op, sz, it, cid, t = result
                                record_result(writer, sys, op, sz, it, cid, t)
                                all_times.append((sys, op, sz, t))
                            else:
                                sys, op, sz, it, cid, t, k = result
                                dyno_keys[cid] = k
                                record_result(writer, sys, op, sz, it, cid, t)
                                all_times.append((sys, op, sz, t))

                if operation_mode in ["download", "both"]:
                    print(f"[Repetition {rep+1}] Download Phase")

                    def s3_download_task(c):
                        out = f"temp_outputs/s3_{size}MB_rep{rep}_client{c}.bin"
                        t = time_s3_download(object_keys[c], out)
                        return ("s3", "download", size, rep + 1, c, t)

                    def dyno_download_task(c):
                        out = f"temp_outputs/dyno_{size}MB_rep{rep}_client{c}.bin"
                        t = time_dynostore_pull(dyno_keys[c], out)
                        return ("dynostore", "download", size, rep + 1, c, t)

                    download_futures = []
                    with ThreadPoolExecutor(max_workers=num_clients) as executor:
                        for c in range(num_clients):
                            print(dyno_keys[c])
                            if "s3" in backends or "s3object" in backends:
                                download_futures.append(executor.submit(s3_download_task, c))
                            if "dynostore" in backends and dyno_keys[c] is not None:
                                download_futures.append(executor.submit(dyno_download_task, c))
                            if not concurrent_download:
                                time.sleep(2)

                        for f in as_completed(download_futures):
                            sys, op, sz, it, cid, t = f.result()
                            record_result(writer, sys, op, sz, it, cid, t)
                            all_times.append((sys, op, sz, t))
                            print(f"[{sz}MB] Rep {it} - Client {cid} - {sys} {op}: {t:.2f}s")

            os.remove(fname)

    grouped = defaultdict(list)
    with open(csv_file, newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            key = (row["system"], row["operation"], int(row["file_size_mb"]))
            grouped[key].append(float(row["time_sec"]))

    with open(summary_file, "w", newline="") as summary_file_obj:
        writer = csv.DictWriter(summary_file_obj, fieldnames=["system", "operation", "file_size_mb", "avg_time", "std_dev"])
        writer.writeheader()
        for (sys, op, size), times in grouped.items():
            avg = round(statistics.median(times), 4)
            std = round(statistics.stdev(times), 4) if len(times) > 1 else 0.0
            writer.writerow({
                "system": sys,
                "operation": op,
                "file_size_mb": size,
                "avg_time": avg,
                "std_dev": std
            })

    print("\n✅ All tests complete. Results saved to:")
    print(f"  - Raw: {csv_file}")
    print(f"  - Summary: {summary_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Benchmark S3/S3object/DynoStore")
    parser.add_argument("--backend", nargs="+", choices=["s3", "s3object", "dynostore"],
                        default=["s3", "s3object", "dynostore"], help="Select one or more backends")
    parser.add_argument("--operation", choices=["upload", "download", "both"], default="both")
    parser.add_argument("--concurrent-upload", action="store_true")
    parser.add_argument("--concurrent-download", action="store_true")
    parser.add_argument("--clients", type=int, default=4)
    args = parser.parse_args()

    run_tests(
        backends=args.backend,
        operation_mode=args.operation,
        concurrent_upload=args.concurrent_upload,
        concurrent_download=args.concurrent_download,
        num_clients=args.clients
    )
