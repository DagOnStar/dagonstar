"""Importable functions used by the native task example."""


def transform(input_file: str, scale: float, output_file: str) -> dict:
    with open(input_file, encoding="utf-8") as source:
        values = [float(line.strip()) for line in source if line.strip()]
    with open(output_file, "w", encoding="utf-8") as destination:
        for value in values:
            destination.write(f"{value * scale}\n")
    return {"count": len(values), "scale": scale}
