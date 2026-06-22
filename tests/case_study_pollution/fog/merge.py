import pandas as pd
import os

def summarize_fog_data(edge_csv_paths,  output_path):
    #day_str = f"{day:02d}"

    all_data = []

    for path in edge_csv_paths:
        print(f"Checking file: {path}", os.path.exists(path))
        if os.path.exists(path):
            print(f"Processing file: {path}")
            df = pd.read_csv(path)

            #filtered = df[(df["dia"] == day)]

            #print(filtered)

            all_data.append(df)
            

    if not all_data:
        print("No valid data found.")
        return None

    combined = pd.concat(all_data, ignore_index=True)

    summary = (
        combined
        .groupby(['estacion', 'magnitud', 'mes', 'ano'])
        .agg(PROMEDIO_VALOR=('valor', 'mean'))
        .reset_index()
    )

    summary.to_csv(output_path, index=False)
    return summary


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Summarize fog data from edge devices.")
    #parser.add_argument("day", type=int, help="Day of the month (1-31).")
    #parser.add_argument("month", type=int, help="Month of the year (1-12).")
    #parser.add_argument("station", type=int, help="Station name (as in CSV file).")
    parser.add_argument("--edge_csv_path", nargs="+" ,required=True, help="Paths to edge CSV files.")
    parser.add_argument("--output_path", type=str, default="fog_summary.csv", help="Output path for summary CSV.")

    args = parser.parse_args()

    summary = summarize_fog_data(args.edge_csv_path, args.output_path)
    if summary is not None:
        print(f"Summary saved to {args.output_path}")
        print(summary)