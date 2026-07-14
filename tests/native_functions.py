"""Importable functions used by native task tests."""


def scale_file(input_file, scale, output_file):
    with open(input_file, encoding="utf-8") as source:
        values = [float(value.strip()) for value in source if value.strip()]
    with open(output_file, "w", encoding="utf-8") as destination:
        for value in values:
            destination.write(str(value * scale) + "\n")
    return {"count": len(values), "scale": scale}


def needs_value(value):
    return {"value": value}
