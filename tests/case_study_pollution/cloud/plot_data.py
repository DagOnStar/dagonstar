import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import os

# File path to your merged result
INPUT_FILE = "comparison_cloud.csv"

# Load the comparison file
df = pd.read_csv(INPUT_FILE)

# Ensure output folder exists
os.makedirs("plots", exist_ok=True)

# Convert 'ano' and 'mes' into datetime
df["date"] = pd.to_datetime(dict(year=df["ano"], month=df["mes"], day=1))

# Sort chronologically
df.sort_values("date", inplace=True)

print("Available columns:", df.columns.tolist())  # Debug print

# Ensure correct capitalization and column presence
if "DEVIATION" not in df.columns:
    if "PROMEDIO_VALOR" in df.columns and "PROMEDIO_HISTORICO" in df.columns:
        df["DEVIATION"] = df["PROMEDIO_VALOR"] - df["PROMEDIO_HISTORICO"]
    else:
        raise ValueError("Required columns to compute DEVIATION are missing.")


# 1. Observed time trends per pollutant
plt.figure(figsize=(12, 6))
sns.lineplot(data=df, x="date", y="PROMEDIO_VALOR", hue="magnitud", marker="o")
plt.title("Observed Monthly Average Trends per Pollutant")
plt.xlabel("Date")
plt.ylabel("Observed Average")
plt.xticks(rotation=45)
plt.tight_layout()
plt.savefig("plots/time_trend_observed_per_pollutant.png")
plt.close()

# 2. Historical time trends per pollutant
plt.figure(figsize=(12, 6))
sns.lineplot(data=df, x="date", y="PROMEDIO_HISTORICO", hue="magnitud", marker="o", linestyle="--")
plt.title("Historical Monthly Average Trends per Pollutant")
plt.xlabel("Date")
plt.ylabel("Historical Average")
plt.xticks(rotation=45)
plt.tight_layout()
plt.savefig("plots/time_trend_historical_per_pollutant.png")
plt.close()

# 3. Deviation with thresholds
plt.figure(figsize=(12, 6))
sns.lineplot(data=df, x="date", y="DEVIATION", hue="magnitud", marker="o")
plt.axhline(0, linestyle='--', color='black', label='No Deviation')
plt.axhline(5, linestyle=':', color='red', label='Threshold +5')
plt.axhline(-5, linestyle=':', color='blue', label='Threshold -5')
plt.title("Deviation Over Time (Observed - Historical)")
plt.xlabel("Date")
plt.ylabel("Deviation")
plt.legend()
plt.xticks(rotation=45)
plt.tight_layout()
plt.savefig("plots/time_trend_deviation_with_thresholds.png")
plt.close()
