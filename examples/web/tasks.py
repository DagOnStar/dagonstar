"""Functions used by the local web-task example."""

import json


def summarize_response(response_file: str, summary_file: str) -> dict:
    response = json.load(open(response_file, encoding="utf-8"))
    json.dump({"received": len(response["body"])}, open(summary_file, "w", encoding="utf-8"))
    return {"received": len(response["body"])}
