import pandas as pd
import statistics
import os
import csv


def analyze_operations(csv_path, n, k, prob):
    # Load CSV
    df = pd.read_csv(csv_path)

    # Count success and failure
    success_count = df['success'].sum()
    failure_count = len(df) - success_count

    # Compute time stats
    total_time = df['duration_sec'].sum()
    average_time = df['duration_sec'].mean()
    std_dev_time = df['duration_sec'].std()

    # Print results
    print(f"📊 Results from {csv_path}")
    print(f"Total operations: {len(df)}")
    print(f"Successes: {success_count}")
    print(f"Failures: {failure_count}")
    print(f"Total time (s): {round(total_time, 4)}")
    print(f"Average time per object (s): {round(average_time, 4)}")
    print(f"Standard deviation (s): {round(std_dev_time, 4)}")

    # Check if CSV file exists, if not create it
    # Ensure the summary file exists and has a header
    if not os.path.exists("results_failures_sum.csv"):
        with open("results_failures_sum.csv", 'w', newline='') as csvfile:
            fieldnames = ["Total_Operations", "Successes", "Failures", "Total_Time_s", "Average_Time_s", "Std_Dev_Time_s", "n", "k", "prob"]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

    # Append the results
    with open("results_failures_sum.csv", 'a', newline='') as csvfile:
        fieldnames = ["Total_Operations", "Successes", "Failures", "Total_Time_s", "Average_Time_s", "Std_Dev_Time_s", "n", "k", "prob"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writerow({
            "Total_Operations": len(df),
            "Successes": success_count,
            "Failures": failure_count,
            "Total_Time_s": round(total_time, 4),
            "Average_Time_s": round(average_time, 4),
            "Std_Dev_Time_s": round(std_dev_time, 4),
            "n": n,
            "k": k,
            "prob": prob
        })

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Usage: python analyze_results.py <path_to_csv>")
    else:
        analyze_operations(sys.argv[1])


# Directory
dir_name = "failure_results"

# List of CSV files to analyze reading content in directory
if not os.path.exists(dir_name):
    print(f"Directory '{dir_name}' does not exist.")

csv_files = [f for f in os.listdir(dir_name) if f.endswith('.csv')]

# Analyze each CSV file
for csv_file in csv_files:
    # Get values of n,k, and probability from the filename
    n, k, prob = csv_file.split('_')[1:4]
    prob = prob.split('p')[0]  # Remove .csv extension
    print(f"Analyzing file: {csv_file} with n={n}, k={k}, prob={prob}")
    csv_path = os.path.join(dir_name, csv_file)
    print(f"Analyzing {csv_path}...")
    analyze_operations(csv_path, n, k, prob)
    print("\n" + "="*40 + "\n")