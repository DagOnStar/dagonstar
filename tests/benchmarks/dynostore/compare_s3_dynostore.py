import boto3
import time
import os
import uuid
import csv
import statistics
from collections import defaultdict

from dynostore import client

AWS_BUCKET = "dynostore-tests-2"
AWS_REGION = "us-west-1"
DYNOSTORE_NAMESPACE = "benchmark"
REPEATS = 5
FILE_SIZES_MB = [1000] # [1, 10, 50, 100, 1000]
CSV_FILE = "results.csv"
SUMMARY_FILE = "summary.csv"

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


def time_s3_download(object_key, local_path):
    start = time.time()
    s3.download_file(AWS_BUCKET, object_key, local_path)
    return time.time() - start


def time_dynostore_push(file_path):
    print(f"pushing {file_path} into Dynostore...")
    with open(file_path, 'rb') as f:
        data = f.read()
    start = time.time()
    result = dyno_client.put(data=data, catalog="test", name=os.path.basename(file_path))
    return time.time() - start, result["key_object"]


def time_dynostore_pull(dyno_key, out_path):
    start = time.time()
    data = dyno_client.get(dyno_key)
    if data is not None:
        with open(out_path, 'wb') as f:
            f.write(data)
    return time.time() - start


def record_result(writer, system, operation, size_mb, iteration, elapsed_time):
    writer.writerow({
        "system": system,
        "operation": operation,
        "file_size_mb": size_mb,
        "iteration": iteration,
        "time_sec": round(elapsed_time, 4)
    })


def run_tests():
    os.makedirs("temp_outputs", exist_ok=True)

    all_times = []  # For summary

    # with open(CSV_FILE, "w", newline="") as csvfile:
    #     fieldnames = ["system", "operation", "file_size_mb", "iteration", "time_sec"]
    #     writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
    #     writer.writeheader()

    #     for size in FILE_SIZES_MB:
    #         fname = f"testfile-{uuid.uuid4().hex}-{size}MB.bin"
    #         generate_file(fname, size)
    #         object_key = fname
    #         dynofile = fname

    #         s3_uploads = []
    #         dyno_uploads = []

    #         # Repeat uploads
    #         print(f"\n--- Uploading {size}MB file ---")
    #         for i in range(REPEATS):
    #             s3_time = time_s3_upload(fname, object_key)
    #             dyno_time, dyno_key = time_dynostore_push(fname)

    #             s3_uploads.append(s3_time)
    #             dyno_uploads.append(dyno_time)

    #             record_result(writer, "s3", "upload", size, i + 1, s3_time)
    #             record_result(writer, "dynostore", "upload", size, i + 1, dyno_time)

    #         # Repeat downloads
    #         for i in range(REPEATS):
    #             out_s3 = f"temp_outputs/s3_{size}MB_{i}.bin"
    #             out_dyno = f"temp_outputs/dyno_{size}MB_{i}.bin"

    #             s3_t = time_s3_download(object_key, out_s3)
    #             dyno_t = time_dynostore_pull(dyno_key, out_dyno)

    #             record_result(writer, "s3", "download", size, i + 1, s3_t)
    #             record_result(writer, "dynostore", "download", size, i + 1, dyno_t)

    #             all_times.append(("s3", "download", size, s3_t))
    #             all_times.append(("dynostore", "download", size, dyno_t))

    #             print(f"[{size}MB] Iteration {i+1}: S3={s3_t:.2f}s | DynoStore={dyno_t:.2f}s")

    #         # Add upload to summary
    #         for t in s3_uploads:
    #             all_times.append(("s3", "upload", size, t))
    #         for t in dyno_uploads:
    #             all_times.append(("dynostore", "upload", size, t))

    #         os.remove(fname)

    # Read from results.csv
    # Step 1: Read the CSV and group times
    grouped = defaultdict(list)

    with open(CSV_FILE, newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            key = (
                row["system"],
                row["operation"],
                int(row["file_size_mb"])
            )
            time = float(row["time_sec"])
            grouped[key].append(time)

    # Step 2: Write the statistics summary
    with open(SUMMARY_FILE, "w", newline="") as summary_file:
        writer = csv.DictWriter(summary_file, fieldnames=["system", "operation", "file_size_mb", "avg_time", "std_dev"])
        writer.writeheader()

        for (sys, op, size), times in grouped.items():
            avg = round(statistics.mean(times), 4)
            std = round(statistics.stdev(times), 4) if len(times) > 1 else 0.0
            writer.writerow({
                "system": sys,
                "operation": op,
                "file_size_mb": size,
                "avg_time": avg,
                "std_dev": std
            })

    print("✅ All tests complete. Results saved to:")
    print(f"  - Raw: {CSV_FILE}")
    print(f"  - Summary: {SUMMARY_FILE}")


if __name__ == "__main__":
    run_tests()
