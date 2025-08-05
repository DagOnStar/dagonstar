
import pandas as pd
import time
import os
import sys
from datetime import datetime



# --- Get the day from command-line argument ---
if len(sys.argv) != 6:
    print("Usage: python ingest_simulator.py <day> <month> <station> <data>")
    sys.exit(1)

try:
    day = int(sys.argv[1])
    month = int(sys.argv[2])
    station = int(sys.argv[3])
    if not (1 <= day <= 31):
        raise ValueError
except ValueError:
    print("Invalid day. Must be an integer between 1 and 31.")
    sys.exit(1)

# --- Configuration ---
DATA_FILE = sys.argv[4]  # Path to the dataset
output_file = sys.argv[5]

# --- Load dataset ---
df = pd.read_csv(DATA_FILE, sep=';')
df = df[df['ESTACION'] == station]  # Filter by station
if df.empty:
    print(f"No data available for station {station}")
    sys.exit(0)
# Ensure 'MES' column is numeric for filtering
df['MES'] = pd.to_numeric(df['MES'], errors='coerce')
# Filter by month
df = df[df['MES'] == month]  # Filter by month

# Filter by month and station 

# --- Process given day ---
day_col = f"D{day:02}"
val_col = f"V{day:02}"

if day_col not in df.columns:
    print(f"No data available for day {day}")
    sys.exit(0)

day_data = df[["PROVINCIA", "MUNICIPIO", "ESTACION", "MAGNITUD", "ANO", "MES", day_col, val_col]].copy()
day_data.columns = ["provincia", "municipio", "estacion", "magnitud", "ano", "mes", "valor", "validacion"]
day_data["dia"] = day
day_data["timestamp"] = datetime.now().isoformat()


# Save temporary slice
out_filename = f"airquality_{output_file}"
day_data.to_csv(out_filename, index=False)

print(f"[INFO] Simulating ingestion for day {day}: {out_filename}")
