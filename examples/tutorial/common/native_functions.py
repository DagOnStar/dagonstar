"""Importable functions for native-task lessons."""
import csv
import json


def mean_temperature(observations, result):
    with open(observations, newline="", encoding="utf-8") as stream:
        values = [float(row["temperature_c"]) for row in csv.DictReader(stream)]
    with open(result, "w", encoding="utf-8") as stream:
        json.dump({"mean_temperature_c": sum(values) / len(values)}, stream, sort_keys=True)
        stream.write("\n")
    return {"count": len(values)}


def count_records(input_file, output_file):
    """Count the records of an agentic JSON result (used by the agentic examples)."""
    import json
    with open(input_file, encoding="utf-8") as source:
        records = json.load(source)["observations"]
    with open(output_file, "w", encoding="utf-8") as destination:
        json.dump({"count": len(records)}, destination)
    return {"count": len(records)}


def events_to_observations(input_file, output_file):
    """Normalise an IoT observation envelope into the record table used by the agentic lessons."""
    import json
    with open(input_file, encoding="utf-8") as source:
        events = json.load(source)["events"]
    keys = ("id", "station", "temperature_c")
    records = [{key: event[key] for key in keys if key in event} for event in events]
    with open(output_file, "w", encoding="utf-8") as destination:
        json.dump({"observations": records}, destination)
    return {"count": len(records)}
