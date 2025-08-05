import argparse
import joblib
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime

# --- Argument parser ---
parser = argparse.ArgumentParser(description="Predict and compare historical vs future pollution levels.")
parser.add_argument('--stations', type=int, nargs='+', required=True, help="List of station IDs (e.g., --stations 4 8 10)")
parser.add_argument('--model', type=str, help="Path to model")
parser.add_argument('--features', type=str, help="Path to base features")
parser.add_argument('--poly_transformer', type=str, help="Path to PolynomialFeatures transformer")
parser.add_argument('--data_dir', type=str, default='.', help="Data dir")
args = parser.parse_args()
stations = args.stations

# --- Load trained model and metadata ---
model = joblib.load(args.model) if args.model else joblib.load("pollution_predictor_poly.pkl")
features = joblib.load(args.features)       # should be ['ESTACION', 'MONTH', 'YEAR']
poly = joblib.load(args.poly_transformer)             # fitted PolynomialFeatures instance

# --- Load historical data (2020–2023) ---
DATA_FILES = []
import os
import glob
data_dir = args.data_dir
DATA_FILES = sorted(glob.glob(os.path.join(data_dir, "*.csv")))

MAGNITUD = 8  # O3, for example

def load_historical_data(files):
    records = []
    for file in files:
        df = pd.read_csv(file, sep=";", dtype=str)
        df = df[df["MAGNITUD"].astype(int) == MAGNITUD]
        df["ANO"] = df["ANO"].astype(int)
        df["MES"] = df["MES"].astype(int)
        df["ESTACION"] = df["ESTACION"].astype(int)
        for day in range(1, 32):
            val_col = f"D{day:02d}"
            if val_col not in df.columns:
                continue
            temp = df[["ESTACION", "ANO", "MES", val_col]].copy()
            temp = temp.rename(columns={val_col: "VALOR"})
            temp["DIA"] = day
            records.append(temp)
    all_data = pd.concat(records)
    all_data["VALOR"] = pd.to_numeric(all_data["VALOR"], errors="coerce")
    all_data.dropna(subset=["VALOR"], inplace=True)
    all_data["DIA"] = all_data["DIA"].astype(int)
    all_data["DATE"] = pd.to_datetime(dict(year=all_data["ANO"], month=all_data["MES"], day=all_data["DIA"]), errors='coerce')
    all_data.dropna(subset=["DATE"], inplace=True)
    return all_data

historical_data = load_historical_data(DATA_FILES)

# Compute monthly averages
monthly_avg = historical_data.groupby(["ESTACION", "ANO", "MES"]).agg({
    "VALOR": "mean"
}).reset_index().rename(columns={"ANO": "YEAR", "MES": "MONTH"})
monthly_avg = monthly_avg[monthly_avg["ESTACION"].isin(stations)]
monthly_avg["SOURCE"] = "real"
monthly_avg["DATE"] = pd.to_datetime(dict(year=monthly_avg["YEAR"], month=monthly_avg["MONTH"], day=15))

# --- Create prediction input for 2024–2026 ---
future_rows = []
for station in stations:
    for year in range(2020,2028):
        for month in range(1, 13):
            future_rows.append({
                "ESTACION": station,
                "YEAR": year,
                "MONTH": month
            })

df_future = pd.DataFrame(future_rows)
X_poly = poly.transform(df_future[features])
df_future["VALOR"] = model.predict(X_poly)
df_future["SOURCE"] = "predicted"
df_future["DATE"] = pd.to_datetime(dict(year=df_future["YEAR"], month=df_future["MONTH"], day=15))

# --- Combine real and predicted ---
combined = pd.concat([monthly_avg, df_future], ignore_index=True)

# --- Plot ---
sns.set(style="whitegrid")
plt.figure(figsize=(14, 7))

for station in stations:
    subset = combined[combined["ESTACION"] == station]
    sns.lineplot(data=subset, x="DATE", y="VALOR", hue="SOURCE")

plt.xlabel("Date")
plt.ylabel("Pollution Value (monthly avg)")
plt.title("Pollution Trends: Real (2020–2023) vs Predicted (2024–2026)")
plt.legend(title="Data Source")
plt.tight_layout()
plt.savefig("real_vs_predicted_trends_2020_2026.png")
#plt.show()
