import pandas as pd

# --- Configuration ---
fog_summary_file = "../fog/fog_summary.csv"  # File containing fog-level averages
historical_files = [
    "historical_data/datos2022.csv",
    "historical_data/datos2023.csv",
    "historical_data/datos2024.csv",
    "historical_data/datos2021.csv"
]

# --- Step 1: Load Fog Summary ---
fog_df = pd.read_csv(fog_summary_file)
fog_df["estacion"] = fog_df["estacion"].astype(int)
fog_df["magnitud"] = fog_df["magnitud"].astype(int)
fog_df["mes"] = fog_df["mes"].astype(int)

# --- Step 2: Load and reshape historical data ---
historical_long = []

for file in historical_files:
    df = pd.read_csv(file, sep=";", encoding="latin-1")
    
    # Identify columns that contain daily values
    value_columns = [col for col in df.columns if col.startswith("D") and len(col) == 3]
    
    # Melt the wide format into long format
    df_melted = df.melt(
        id_vars=["ESTACION", "MAGNITUD", "ANO", "MES"],
        value_vars=value_columns,
        var_name="DIA",
        value_name="VALOR"
    )
    
    # Extract day number from column name (e.g., D01 -> 1)
    df_melted["DIA"] = df_melted["DIA"].str.extract("D(\d+)").astype(int)
    
    # Convert values to numeric
    df_melted["VALOR"] = pd.to_numeric(df_melted["VALOR"], errors="coerce")
    
    historical_long.append(df_melted)

# Concatenate all years
historical_df = pd.concat(historical_long, ignore_index=True)

# --- Step 3: Compute Historical Averages ---
historical_avg = (
    historical_df
    .groupby(["ESTACION", "MAGNITUD", "MES"], as_index=False)["VALOR"]
    .mean()
    .rename(columns={
        "ESTACION": "estacion",
        "MAGNITUD": "magnitud",
        "MES": "mes",
        "VALOR": "PROMEDIO_HISTORICO"
    })
)

# --- Step 4: Merge with Fog Summary ---
comparison_df = pd.merge(
    fog_df,
    historical_avg,
    on=["estacion", "magnitud", "mes"],
    how="left"
)

# --- Step 5: Save result ---
comparison_df.to_csv("comparison_cloud.csv", index=False)
print("✅ Cloud-level comparison saved to 'comparison_cloud.csv'")