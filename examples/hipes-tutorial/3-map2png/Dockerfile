# Dockerfile: simple container to convert .nc → .png
FROM python:3.11-slim

ENV MPLBACKEND=Agg \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir xarray netCDF4 matplotlib numpy geopandas shapely

COPY shapes/ shapes/
COPY map2png.py /app/map2png.py

CMD ["/bin/bash"]
