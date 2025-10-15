#!/usr/bin/env python3
import argparse
import sys
import warnings

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from netCDF4 import Dataset
import numpy as np


def infer_axis_order(var, slices):
    """
    Given a NetCDF variable and the list of slices/indices used to read it,
    return the order of kept axes (those sliced with slice(None)) *after* reading/squeezing.
    We assume only lat/lon are kept as slices in most cases.
    """
    kept_names = [d for d, sl in zip(var.dimensions, slices) if isinstance(sl, slice)]
    # After reading and squeeze, the kept axes should remain in the same order.
    return kept_names


def main():
    p = argparse.ArgumentParser(description="Render a NetCDF variable to a PNG (optional shapefile overlay)")
    p.add_argument("--in",  dest="infile",  required=True, help="Input NetCDF file (URL allowed)")
    p.add_argument("--out", dest="outfile", required=True, help="Output PNG path")
    p.add_argument("--var", default="va",   help="Variable name (default: va)")
    p.add_argument("--time",  type=int, default=0, help="Time index if present (default: 0)")
    p.add_argument("--level", type=int, default=0, help="Level/plevel index if present (default: 0)")
    p.add_argument("--step",  type=int, default=10, help="Spatial subsampling step (default: 10)")

    # Shapefile options
    p.add_argument("--shp", dest="shp", default=None, help="Path to the shapefile (.shp) to overlay")
    p.add_argument("--shp-crs", dest="shp_crs", default=None,
                   help="CRS for the shapefile if missing (e.g., 'EPSG:4326' or a PROJ string)")
    p.add_argument("--shp-fill", dest="shp_fill", action="store_true",
                   help="Draw filled polygons (default: boundaries only)")
    p.add_argument("--shp-alpha", dest="shp_alpha", type=float, default=1.0,
                   help="Opacity for the shapefile (default: 1.0)")
    p.add_argument("--shp-edgecolor", dest="shp_edgecolor", default="red",
                   help="Edge color for the shapefile (default: red)")
    p.add_argument("--shp-facecolor", dest="shp_facecolor", default="none",
                   help="Fill color for the shapefile (only if --shp-fill) (default: none)")
    p.add_argument("--shp-linewidth", dest="shp_lw", type=float, default=0.8,
                   help="Line width for the shapefile boundaries (default: 0.8)")

    args = p.parse_args()

    ds = Dataset(args.infile, "r")

    if args.var not in ds.variables:
        ds.close()
        raise KeyError(f"Variable '{args.var}' not found. Available: {list(ds.variables.keys())}")

    var = ds.variables[args.var]

    # Build slicing: time/plevel -> indices; lat/lon -> slice(None), others -> 0
    slices = []
    lat_dim = None
    lon_dim = None
    for dim in var.dimensions:
        d = dim.lower()
        if d in ("time", "t"):
            slices.append(args.time)
        elif d in ("plevel", "lev", "level", "depth", "z"):
            slices.append(args.level)
        elif d in ("latitude", "lat", "y"):
            slices.append(slice(None))
            lat_dim = dim
        elif d in ("longitude", "lon", "x"):
            slices.append(slice(None))
            lon_dim = dim
        else:
            # unknown dimension: take first index
            slices.append(0)

    data = np.array(var[tuple(slices)]).squeeze()

    # Must end up 2D
    if data.ndim < 2:
        ds.close()
        raise ValueError(f"Variable {args.var} is not 2D after slicing: shape={data.shape}")

    # If we still have >2 dims (rare), attempt to keep only lat/lon by moving axes
    kept_names = infer_axis_order(var, slices)
    if data.ndim > 2 and lat_dim and lon_dim:
        # determine current axis indices for lat/lon among kept axes
        try:
            kept_idx = list(range(data.ndim))  # assume same order
            lat_axis = kept_names.index(lat_dim)
            lon_axis = kept_names.index(lon_dim)
            # Move to (lat, lon, ...), then take first two
            data = np.moveaxis(data, [lat_axis, lon_axis], [0, 1])
            data = data[(slice(None), slice(None))]  # keep first two axes
        except Exception:
            # fallback: keep the first two axes
            data = np.array(data[0]).squeeze()
            while data.ndim > 2:
                data = np.array(data[0]).squeeze()

    # If dims are (lon, lat) instead of (lat, lon), transpose
    if lat_dim and lon_dim:
        try:
            # guess by comparing lengths with coordinate variables if 1D
            lat_name_var = next((n for n in ("latitude", "lat", "y") if n in ds.variables), None)
            lon_name_var = next((n for n in ("longitude", "lon", "x") if n in ds.variables), None)
            lat = ds.variables[lat_name_var][:] if lat_name_var else None
            lon = ds.variables[lon_name_var][:] if lon_name_var else None
            if lat is not None and lon is not None and lat.ndim == 1 and lon.ndim == 1:
                if data.shape[0] == lon.shape[0] and data.shape[1] == lat.shape[0]:
                    data = data.T  # transpose to (lat, lon)
        except Exception:
            pass

    # Subsample
    data = data[::args.step, ::args.step]

    # Build extent from lat/lon if available (assumes 1D coordinates)
    extent = None
    lat_name = next((n for n in ("latitude", "lat", "y") if n in ds.variables), None)
    lon_name = next((n for n in ("longitude", "lon", "x") if n in ds.variables), None)
    lat = None
    lon = None
    if lat_name and lon_name:
        try:
            lat = ds.variables[lat_name][::args.step]
            lon = ds.variables[lon_name][::args.step]
            # Ensure lat is ascending (for imshow)
            if lat.ndim == 1 and lat.size > 1 and lat[0] > lat[-1]:
                data = np.flipud(data)
                lat = lat[::-1]
            # Normalize longitudes 0..360 -> -180..180 and reorder columns
            if lon.ndim == 1 and np.nanmax(lon) > 180:
                lon_wrapped = ((lon + 180) % 360) - 180
                sort_idx = np.argsort(lon_wrapped)
                lon = lon_wrapped[sort_idx]
                data = data[:, sort_idx]
            extent = [float(np.nanmin(lon)), float(np.nanmax(lon)),
                      float(np.nanmin(lat)), float(np.nanmax(lat))]
        except Exception:
            extent = None

    # Plot raster
    fig = plt.figure(figsize=(10, 10), dpi=150)
    ax = plt.gca()
    im = ax.imshow(data, origin="lower", extent=extent, cmap="viridis", aspect="auto")
    units = getattr(var, "units", "")
    plt.colorbar(im, ax=ax, label=units)
    title = getattr(ds, "title", args.var)
    ax.set_title(title)
    ax.set_xlabel("Longitude" if extent else "X index")
    ax.set_ylabel("Latitude"  if extent else "Y index")

    # Shapefile overlay (if requested)
    if args.shp:
        if extent is None:
            warnings.warn(
                "Could not determine geographic extent from NetCDF; shapefile overlay may not align.",
                RuntimeWarning
            )
        try:
            import geopandas as gpd
        except Exception:
            ds.close()
            plt.close(fig)
            print(
                "Error: '--shp' requires the 'geopandas' library. "
                "Install with: pip install geopandas shapely",
                file=sys.stderr
            )
            raise

        shp = gpd.read_file(args.shp)

        # If shapefile CRS is missing but provided via CLI, set it
        if shp.crs is None and args.shp_crs:
            try:
                shp = shp.set_crs(args.shp_crs)
            except Exception as e:
                warnings.warn(f"Unable to set CRS '{args.shp_crs}' for the shapefile: {e}")

        # Reproject to EPSG:4326 if we have geographic extent
        if extent is not None:
            try:
                if shp.crs is None and not args.shp_crs:
                    warnings.warn(
                        "Shapefile CRS is undefined. Attempting to plot as-is; "
                        "if overlay is wrong, pass --shp-crs (e.g., 'EPSG:4326')."
                    )
                elif (shp.crs is not None) and (shp.crs.to_string() != "EPSG:4326"):
                    shp = shp.to_crs("EPSG:4326")
            except Exception as e:
                warnings.warn(f"Failed to reproject shapefile to EPSG:4326: {e}")

        # Draw either boundaries or filled polygons
        if args.shp_fill:
            shp.plot(ax=ax,
                     facecolor=args.shp_facecolor,
                     edgecolor=args.shp_edgecolor,
                     linewidth=args.shp_lw,
                     alpha=args.shp_alpha)
        else:
            # boundary is lighter-weight and avoids fills
            try:
                shp.boundary.plot(ax=ax,
                                  color=args.shp_edgecolor,
                                  linewidth=args.shp_lw,
                                  alpha=args.shp_alpha)
            except Exception:
                # Fallback: not all geometry types have a solid boundary (lines/points)
                shp.plot(ax=ax,
                         facecolor="none",
                         edgecolor=args.shp_edgecolor,
                         linewidth=args.shp_lw,
                         alpha=args.shp_alpha)

    fig.tight_layout()
    fig.savefig(args.outfile, bbox_inches="tight")
    plt.close(fig)
    ds.close()
    print(f"PNG saved to {args.outfile}")


if __name__ == "__main__":
    main()
