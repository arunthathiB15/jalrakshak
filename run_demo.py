"""
run_demo.py
------------
End-to-end demo run: breach hydrograph -> inundation simulation -> GIS
export -> a JSON bundle the dashboard can read. Works on the SYNTHETIC
DEM out of the box (no downloads needed) so you can confirm the whole
pipeline runs today. Swap `load_real_dem()` in for `make_synthetic_valley_dem()`
once your SRTM/CartoDEM download + AOI clip is ready (see README.md).
"""

import json
import numpy as np
from rasterio.transform import from_origin

from breach_hydrograph import generate_hydrograph
from flood_extent import simulate_inundation, make_synthetic_valley_dem
from gis_export import depth_to_polygon, export


def load_real_dem(path):
    """Use this once you have a real DEM GeoTIFF (clipped to your AOI).
    Requires: pip install rasterio (already in requirements.txt)."""
    import rasterio
    with rasterio.open(path) as src:
        dem = src.read(1).astype(float)
        transform = src.transform
        crs = src.crs
        cell_size_m = abs(transform.a)
    return dem, transform, crs, cell_size_m


def main(dem_path: str = None):
    # --- 1. Terrain ---
    if dem_path:
        dem, transform, crs, cell_size_m = load_real_dem(dem_path)
        print(f"Loaded real DEM: {dem_path}  shape={dem.shape}  cell={cell_size_m:.1f} m  crs={crs}")
    else:
        dem = make_synthetic_valley_dem()
        cell_size_m = 30.0
        transform = from_origin(0, 0, cell_size_m, cell_size_m)
        crs = "EPSG:32644"  # placeholder UTM zone -- use your real AOI's UTM zone
        print("Using SYNTHETIC DEM (no --dem given). Replace with a real DEM before finals.")

    source_rc = (dem.shape[0] // 2, 5)  # TODO: set to the real dam/breach pixel location

    # --- 2. Breach hydrograph (EDIT THESE for your chosen dam, from NRLD) ---
    t, q, hydro_params = generate_hydrograph(
        volume_m3=15_000_000,      # reservoir gross storage at failure (m3)
        breach_height_m=12.0,      # approx. dam/breach height (m)
        failure_time_hr=1.0,       # breach formation time (hr)
        mode="overtopping",        # or "piping"
    )
    print("Hydrograph:", hydro_params)

    # --- 3. Inundation simulation ---
    frames = simulate_inundation(dem, source_rc, t, q, cell_size_m=cell_size_m, n_frames=8)
    max_depth = frames[-1]["depth"]

    # --- 4. GIS export (.shp / .kml / .geojson) ---
    gdf = depth_to_polygon(max_depth, transform, crs=crs)
    export(gdf, "outputs/flood_extent")

    # --- 5. Bundle for the dashboard ---
    bundle = {
        "hydrograph": {"time_min": (t / 60).round(1).tolist(), "discharge_cumecs": q.round(1).tolist()},
        "params": hydro_params,
        "frames_summary": [
            {"time_min": round(f["time_s"] / 60, 1), "wse_m": round(f["wse"], 2),
             "inundated_area_km2": round(f["inundated_area_m2"] / 1e6, 3)}
            for f in frames
        ],
        "max_inundated_area_km2": round(frames[-1]["inundated_area_m2"] / 1e6, 3),
        "max_depth_m": round(float(np.max(max_depth)), 2),
    }
    with open("outputs/dashboard_bundle.json", "w") as f:
        json.dump(bundle, f, indent=2)
    print("Saved outputs/dashboard_bundle.json -- paste this into the dashboard's DATA object,")
    print("or serve it from a small FastAPI endpoint (see README.md Step 5).")


if __name__ == "__main__":
    import sys
    dem_arg = sys.argv[1] if len(sys.argv) > 1 else None
    main(dem_arg)
