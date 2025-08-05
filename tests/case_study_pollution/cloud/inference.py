import joblib
import pandas as pd

# Load the model and feature list
clf = joblib.load("exceed_predictor_rf.pkl")
features = joblib.load("model_features.pkl")

# Example: new input data from fog or edge
# Format must match training features
print(features)
new_data = pd.DataFrame([
    {"MONTH": 8, "ESTACION": 4, "WEEKDAY": 1, "YEAR":2025}
])

# Predict
predictions = clf.predict(new_data[features])

# Print results
for i, row in new_data.iterrows():
    print(predictions[i])
    status = "EXCEEDS" if predictions[i] else "OK"
    print(f"Station {row['ESTACION']} (Month {row['MONTH']}): {status}")
