# NetCDF to PNG with Shapefile Overlay

This script converts a **NetCDF variable** into a PNG image using
`matplotlib`.\
Optionally, it can overlay a **shapefile** (boundaries or filled
polygons) on top of the raster.

------------------------------------------------------------------------

## Requirements

-   Python 3.8+
-   Dependencies:

    ``` bash
    pip install numpy matplotlib netCDF4
    ```

-   For shapefile support:

    ``` bash
    pip install geopandas shapely
    ```

------------------------------------------------------------------------

## Usage

``` bash
python map2png.py --in INPUT.nc --out OUTPUT.png [options]
```

### Main options

  ----------------------------------------------------------------------------
  Option      Description                                            Default
  ----------- ------------------------------------------------------ ---------
  `--in`      Input NetCDF file (local path or URL)                  ---

  `--out`     Output PNG filename                                    ---

  `--var`     Variable name to plot                                  `va`

  `--time`    Time index if variable has a time dimension            `0`

  `--level`   Level/plevel index if variable has a vertical          `0`
              dimension                                              

  `--step`    Spatial subsampling step (higher = lower resolution,   `10`
              faster plotting)                                       
  ----------------------------------------------------------------------------

### Shapefile options

  ------------------------------------------------------------------------------------
  Option              Description                                            Default
  ------------------- ------------------------------------------------------ ---------
  `--shp`             Path to a shapefile (`.shp`) to overlay on the raster  None

  `--shp-crs`         CRS for the shapefile if missing (e.g., `EPSG:4326`,   None
                      PROJ string)                                           

  `--shp-fill`        Draw filled polygons instead of boundaries only        False

  `--shp-alpha`       Transparency for shapefile polygons/boundaries         `1.0`

  `--shp-edgecolor`   Edge color of the shapefile polygons                   `red`

  `--shp-facecolor`   Fill color of the shapefile polygons (only if          `none`
                      `--shp-fill` is set)                                   

  `--shp-linewidth`   Line width for shapefile boundaries                    `0.8`
  ------------------------------------------------------------------------------------

------------------------------------------------------------------------

## Examples

### 1. Plot NetCDF variable only

``` bash
python map2png.py --in file.nc --out map.png --var va
```

### 2. Overlay shapefile boundaries (red)

``` bash
python map2png.py --in file.nc --out map.png --var va --shp borders.shp
```

### 3. Overlay shapefile with semi-transparent fill

``` bash
python map2png.py --in file.nc --out map.png --var va   --shp areas.shp --shp-fill --shp-facecolor none   --shp-edgecolor black --shp-linewidth 0.6 --shp-alpha 0.8
```

### 4. Specify shapefile CRS (if missing)

``` bash
python map2png.py --in file.nc --out map.png --var va   --shp data.shp --shp-crs EPSG:32633
```

------------------------------------------------------------------------

## Notes

-   The script assumes the NetCDF latitude/longitude variables are in
    **WGS84 (EPSG:4326)**.\
-   If the NetCDF uses a projected CRS (e.g., UTM, Lambert), reproject
    the shapefile accordingly before overlay.\
-   For performance, the script subsamples the raster with `--step`.
    Lower values give higher resolution but can be slower.

------------------------------------------------------------------------

## Output

-   The script saves the figure to the path given with `--out`.
-   A colorbar is automatically added with units (if available in the
    NetCDF variable attributes).
-   Titles are taken from the NetCDF global attribute `title` (fallback:
    variable name).

------------------------------------------------------------------------

## License

MIT License -- feel free to use and adapt.
