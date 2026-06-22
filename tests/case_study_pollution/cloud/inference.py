import argparse
import joblib
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime

# --- Argument parser ---
parser = argparse.ArgumentParser(description="Predict future pollution levels for specified stations.")
parser.add_argument('--stations', type=int, nargs='+', required=True, help="List of station IDs (e.g., --stations 4 8 10)")
args = parser.parse_args()

# --- Load model and metadata ---
model = joblib.load("pollution_predictor_poly.pkl")
features = joblib.load("poly_base_features.pkl")       # e.g., ["ESTACION", "MONTH", "YEAR"]
poly = joblib.load("poly_transformer.pkl")             # fitted PolynomialFeatures instance

# --- Configuration ---
years = [2025, 2026]
months = list(range(1, 13))
stations = args.stations

# --- Generate input data for prediction ---
future_data = []
for est in stations:
    for year in years:
        for month in months:
            future_data.append({
                "ESTACION": est,
                "MONTH": month,
                "YEAR": year
            })

df_future = pd.DataFrame(future_data)

# --- Apply transformation and predict ---
X_poly = poly.transform(df_future[features])
df_future["PREDICTED_VALOR"] = model.predict(X_poly)

# --- Create a datetime column for plotting (use 15th as dummy day) ---
df_future["DATE"] = pd.to_datetime(dict(year=df_future["YEAR"], month=df_future["MONTH"], day=15))

# --- Plot results ---
sns.set(style="whitegrid")
plt.figure(figsize=(12, 6))

for est in stations:
    subset = df_future[df_future["ESTACION"] == est]
    plt.plot(subset["DATE"], subset["PREDICTED_VALOR"], marker='o', label=f"Station {est}")

plt.xlabel("Date")
plt.ylabel("Predicted Pollution Value")
plt.title("Predicted Pollution Levels (2025–2026)")
plt.legend()
plt.tight_layout()
plt.savefig("predicted_trends_2025_2026.png")
plt.show()
