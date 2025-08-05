import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.preprocessing import PolynomialFeatures
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, r2_score
from joblib import dump

# --- Configuration ---
DATA_FILES = [
    "historical_data/datos2017.csv",
    "historical_data/datos2018.csv",
    "historical_data/datos2019.csv",
    "historical_data/datos2020.csv",
    "historical_data/datos2021.csv",
    "historical_data/datos2022.csv",
    "historical_data/datos2023.csv"
]

MAGNITUD = 8  # pollutant code

def load_data(files):
    all_data = []
    for file in files:
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
    df = load_data(DATA_FILES)
    features = ["ESTACION", "WEEKDAY", "MONTH", "YEAR"]
    X = df[features]
    y = df["VALOR"]

    # Create polynomial features
    poly = PolynomialFeatures(degree=4, include_bias=False)
    X_poly = poly.fit_transform(X)

    # Split the dataset
    X_train, X_test, y_train, y_test = train_test_split(X_poly, y, test_size=0.2, random_state=42)

    # Train model
    model = LinearRegression()
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)

    # Save model and feature transformer
    dump(model, "pollution_predictor_poly.pkl")
    dump(poly, "poly_features.pkl")

    # Evaluation
    rmse = mean_squared_error(y_test, y_pred) ** 0.5
    r2 = r2_score(y_test, y_pred)
    print(f"[RMSE] {rmse:.2f}")
    print(f"[R²] {r2:.3f}")

    # Add predictions to original DataFrame
    df["PREDICTED"] = model.predict(poly.transform(df[features]))

    # Plot observed vs predicted for a single station
    df_station = df[df["ESTACION"] == df["ESTACION"].iloc[0]].sort_values("DATE")
    plt.figure(figsize=(12, 6))
    plt.plot(df_station["DATE"], df_station["VALOR"], label="Observed", alpha=0.7)
    plt.plot(df_station["DATE"], df_station["PREDICTED"], label="Predicted", alpha=0.7)
    plt.title("Observed vs Predicted Pollution Values (Station {})".format(df_station["ESTACION"].iloc[0]))
    plt.xlabel("Date")
    plt.ylabel("Pollutant Value")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig("poly_observed_vs_predicted.png")

    # Plot scatter
    plt.figure(figsize=(6, 6))
    sns.scatterplot(x=y_test, y=y_pred, alpha=0.3)
    plt.xlabel("Actual Values")
    plt.ylabel("Predicted Values")
    plt.title("Predicted vs Actual (Polynomial)")
    plt.grid(True)
    plt.tight_layout()
    plt.savefig("poly_scatter_actual_vs_predicted.png")

if __name__ == "__main__":
    main()
