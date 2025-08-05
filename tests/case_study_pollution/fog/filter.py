import argparse
import pandas as pd
import os
from datetime import datetime

def consolidate_station_day_data(station_name: int, year_paths: list, day: int, month: int, output_dir: str = "."):
    consolidated_data = pd.DataFrame()

    for path in year_paths:
        if os.path.exists(path):
            df = pd.read_csv(path, sep=';', encoding='latin1')

            day_col = f"D{day:02}"
            val_col = f"V{day:02}"
            day_data = df[["PROVINCIA", "MUNICIPIO", "ESTACION", "MAGNITUD", "ANO", "MES", day_col, val_col]].copy()
            day_data.columns = ["provincia", "municipio", "estacion", "magnitud", "ano", "mes", "valor", "validacion"]
            day_data["dia"] = day
            day_data["timestamp"] = datetime.now().isoformat()
            print(type(df["MES"][0]), type(month))
            print(df['ESTACION'] == station_name)
            filtered_df = df[
                (df['ESTACION'] == station_name) &
                (df['MES'] == month)
            ]
            consolidated_data = pd.concat([consolidated_data, filtered_df], ignore_index=True)
        else:
            print(f"Warning: File not found {path}")

    output_filename = f"station_{station_name}_day_{day:02d}_month_{month:02d}.csv"
    output_path = os.path.join(output_dir, output_filename)
    consolidated_data.to_csv(output_path, index=False)
    print(f"Filtered data saved to {output_path}")
    return output_path

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simulate an edge device by aggregating data for a specific station, day, and month.")
    parser.add_argument("station", type=int, help="Station name (as in CSV file).")
    parser.add_argument("day", type=int, help="Day of the month.")
    parser.add_argument("month", type=int, help="Month of the year.")
    parser.add_argument("--data_dir", type=str, default=".", help="Directory containing the CSV files.")
    parser.add_argument("--output_dir", type=str, default=".", help="Directory to save the output CSV.")
    args = parser.parse_args()

    year_files = [
        os.path.join(args.data_dir, f"../data/datos202412.csv"),
    ]

    consolidate_station_day_data(args.station, year_files, args.day, args.month, args.output_dir)
