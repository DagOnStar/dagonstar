import argparse
import pandas as pd
import matplotlib.pyplot as plt
import os

POLLUTANT_THRESHOLDS = {
    1: 50,   # SO₂
    6: 40,   # NO₂
    8: 100,  # O₃
    9: 25,   # CO
    10: 50,  # PM₁₀
    12: 35   # PM₂.₅
}

POLLUTANT_NAMES = {
    1: "SO₂",
    6: "NO₂",
    8: "O₃",
    9: "CO",
    10: "PM₁₀",
    12: "PM₂.₅"
}

def process_cloud_data(input_file, output_file, alert_file, plot_dir=None):
    df = pd.read_csv(input_file)

    # Compute average per pollutant per month (across all stations)
    monthly_avg = df.groupby(["ano", "mes", "magnitud"])["PROMEDIO_VALOR"].mean().reset_index()
    monthly_avg.rename(columns={"PROMEDIO_VALOR": "avg_valor"}, inplace=True)

    # Save global averages
    monthly_avg.to_csv(output_file, index=False)
    print(f"[✓] Saved monthly averages to: {output_file}")

    # Generate alerts
    alerts = []
    for _, row in monthly_avg.iterrows():
        pollutant = row["magnitud"]
        avg = row["avg_valor"]
        threshold = POLLUTANT_THRESHOLDS.get(pollutant)
        if threshold and avg > threshold:
            alerts.append({
                "year": int(row["ano"]),
                "month": int(row["mes"]),
                "pollutant": POLLUTANT_NAMES.get(pollutant, f"ID-{pollutant}"),
                "avg_value": round(avg, 2),
                "threshold": threshold
            })

    pd.DataFrame(alerts).to_csv(alert_file, index=False)
    print(f"[!] Saved {len(alerts)} alert(s) to: {alert_file}")

    # Optional: plot monthly time series per pollutant
    if plot_dir:
        os.makedirs(plot_dir, exist_ok=True)
        for pollutant, name in POLLUTANT_NAMES.items():
            subset = monthly_avg[monthly_avg["magnitud"] == pollutant]
            if subset.empty:
                continue
            subset["date"] = pd.to_datetime(dict(year=subset["ano"], month=subset["mes"], day=1))
            plt.figure(figsize=(10, 4))
            plt.plot(subset["date"], subset["avg_valor"], marker='o', label=name)
            plt.axhline(POLLUTANT_THRESHOLDS[pollutant], color='r', linestyle='--', label='Threshold')
            plt.title(f"Monthly Avg Concentration of {name}")
            plt.xlabel("Date")
            plt.ylabel("µg/m³")
            plt.grid(True)
            plt.legend()
            plt.tight_layout()
            path = f"{plot_dir}/monthly_avg_{name}.png"
            plt.savefig(path)
            plt.close()
            print(f"[📈] Saved plot: {path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cloud aggregator: compute global monthly averages and alerts")
    parser.add_argument("--input", required=True, help="Path to fog-level aggregated CSV")
    parser.add_argument("--output", required=True, help="Output file with global monthly averages")
    parser.add_argument("--alerts", required=True, help="Output file with pollution alerts")
    parser.add_argument("--plots", help="Output folder for plots (optional)")
    args = parser.parse_args()

    process_cloud_data(args.input, args.output, args.alerts, args.plots)
