import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.preprocessing import PolynomialFeatures
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, r2_score
from joblib import dump
import os
import argparse
import glob

# --- Configuration ---
MAGNITUD = 8  # pollutant code
DEGREES_TO_TEST = range(1, 10)  # degrees from 1 to 5
OUTPUT_DIR = "model_selection_plots"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def load_data_from_dir(directory_path):
    csv_files = sorted(glob.glob(os.path.join(directory_path, "*.csv")))
    if not csv_files:
        raise FileNotFoundError(f"No CSV files found in {directory_path}")

    all_data = []
    for file in csv_files:
        df = pd.read_csv(file, sep=";", dtype=str)
        df["ANO"] = df["ANO"].astype(int)
        df["MES"] = df["MES"].astype(int)
        df["MAGNITUD"] = df["MAGNITUD"].astype(int)
        df = df[df["MAGNITUD"] == MAGNITUD]

        for day in range(1, 32):
            d_col = f"D{day:02d}"
            if d_col not in df.columns:
                continue
            temp = df[["ESTACION", "ANO", "MES", "MAGNITUD", d_col]].copy()
            temp = temp.rename(columns={d_col: "VALOR"})
            temp["DIA"] = day
            all_data.append(temp)

    combined = pd.concat(all_data)
    combined["VALOR"] = pd.to_numeric(combined["VALOR"], errors="coerce")
    combined.dropna(subset=["VALOR"], inplace=True)

    combined["ESTACION"] = combined["ESTACION"].astype(int)
    combined["DIA"] = combined["DIA"].astype(int)
    combined["DATE"] = pd.to_datetime(dict(year=combined["ANO"], month=combined["MES"], day=combined["DIA"]), errors='coerce')
    combined.dropna(subset=["DATE"], inplace=True)
    combined["WEEKDAY"] = combined["DATE"].dt.weekday
    combined["MONTH"] = combined["DATE"].dt.month
    combined["YEAR"] = combined["DATE"].dt.year

    return combined[["ESTACION", "WEEKDAY", "MONTH", "YEAR", "VALOR", "DATE"]]

def main():
    parser = argparse.ArgumentParser(description="Train polynomial regression model on air quality data.")
    parser.add_argument("--data_dir", required=True, help="Path to directory with CSV files")
    args = parser.parse_args()

    df = load_data_from_dir(args.data_dir)
    features = ["ESTACION", "MONTH", "YEAR"]
    X = df[features]
    y = df["VALOR"]

    X_train_base, X_test_base, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    best_rmse = float("inf")
    best_model = None
    best_poly = None
    best_degree = None

    rmse_values = []
    r2_values = []

    for degree in DEGREES_TO_TEST:
        poly = PolynomialFeatures(degree=degree, include_bias=False)
        X_train = poly.fit_transform(X_train_base)
        X_test = poly.transform(X_test_base)

        model = LinearRegression()
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)

        rmse = mean_squared_error(y_test, y_pred) ** 0.5
        r2 = r2_score(y_test, y_pred)
        rmse_values.append(rmse)
        r2_values.append(r2)

        print(f"[DEGREE {degree}] RMSE: {rmse:.2f} - R²: {r2:.3f}")

        if rmse < best_rmse:
            best_rmse = rmse
            best_model = model
            best_poly = poly
            best_degree = degree

    # Save best model
    dump(best_model, "pollution_predictor_poly.pkl")
    dump(features, "poly_base_features.pkl")
    dump(best_poly, "poly_transformer.pkl")

    print(f"\n[SELECTED] Degree: {best_degree}, RMSE: {best_rmse:.2f}")

    # Plot metrics by degree
    plt.figure(figsize=(8, 4))
    plt.plot(DEGREES_TO_TEST, rmse_values, marker="o", label="RMSE")
    plt.plot(DEGREES_TO_TEST, r2_values, marker="s", label="R²")
    plt.title("Model Performance by Polynomial Degree")
    plt.xlabel("Polynomial Degree")
    plt.ylabel("Score")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "degree_selection.png"))

    # Predictions on full data
    df["PREDICTED"] = best_model.predict(best_poly.transform(df[features]))

    # Time series plot for one station
    df_station = df[df["ESTACION"] == df["ESTACION"].iloc[0]].sort_values("DATE")
    plt.figure(figsize=(12, 6))
    plt.plot(df_station["DATE"], df_station["VALOR"], label="Observed", alpha=0.7)
    plt.plot(df_station["DATE"], df_station["PREDICTED"], label="Predicted", alpha=0.7)
    plt.title(f"Observed vs Predicted (Station {df_station['ESTACION'].iloc[0]}, Degree {best_degree})")
    plt.xlabel("Date")
    plt.ylabel("Pollutant Value")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "observed_vs_predicted.png"))

    # Scatter plot
    plt.figure(figsize=(6, 6))
    sns.scatterplot(x=y_test, y=best_model.predict(best_poly.transform(X_test_base)), alpha=0.3)
    plt.xlabel("Actual")
    plt.ylabel("Predicted")
    plt.title("Actual vs Predicted")
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "scatter_actual_vs_predicted.png"))

if __name__ == "__main__":
    main()
