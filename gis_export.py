"""
gis_export.py
--------------
Converts an inundation depth raster (numpy array, from flood_extent.py)
into the .shp and .kml deliverables the problem statement explicitly asks
for. Needs a rasterio Affine transform + CRS -- when you're working with
a synthetic DEM (no real transform yet) this script falls back to a
simple pixel-grid transform so you can test the export step today.
"""

import numpy as np
import geopandas as gpd
from shapely.geometry import shape
from rasterio.features import shapes
from rasterio.transform import from_origin


def depth_to_polygon(depth: np.ndarray, transform, crs="EPSG:4326", min_depth_m: float = 0.1):
    """Dissolve all inundated cells (depth > min_depth_m) into one polygon
    (or multipolygon) representing the flood extent."""
    mask = depth > min_depth_m
    if not mask.any():
        raise ValueError("No inundated cells above the depth threshold -- check your inputs.")
    geoms = [
        shape(geom)
        for geom, val in shapes(depth.astype("float32"), mask=mask, transform=transform)
    ]
    gdf = gpd.GeoDataFrame({"source": ["JALRAKSHAK prototype"] * len(geoms)}, geometry=geoms, crs=crs)
    dissolved = gdf.dissolve().reset_index(drop=True)
    dissolved["max_depth_m"] = float(np.max(depth))
    dissolved["area_km2"] = float(np.sum(mask)) * abs(transform.a * transform.e) / 1e6
    return dissolved


def export(gdf: gpd.GeoDataFrame, out_prefix: str):
    gdf.to_file(f"{out_prefix}.shp")
    print(f"Saved {out_prefix}.shp (+ .shx/.dbf/.prj)")
    try:
        gdf.to_file(f"{out_prefix}.kml", driver="KML")
        print(f"Saved {out_prefix}.kml")
    except Exception as e:
        print(f"KML export via GeoPandas/Fiona failed ({e}).")
        print("Fallback: run this from a terminal once the .shp exists:")
        print(f"    ogr2ogr -f KML {out_prefix}.kml {out_prefix}.shp")
    # GeoJSON in WGS84 -- this is what the React/Leaflet dashboard consumes
    gdf_wgs84 = gdf.to_crs("EPSG:4326")
    gdf_wgs84.to_file(f"{out_prefix}.geojson", driver="GeoJSON")
    print(f"Saved {out_prefix}.geojson (WGS84 -- feed this to the dashboard)")


if __name__ == "__main__":
    depth = np.load("outputs/max_depth.npy")
    # Placeholder transform for the synthetic DEM test (30 m cells, arbitrary
    # origin). Replace with the REAL transform from rasterio.open(dem_path)
    # once you're running this against your downloaded DEM.
    transform = from_origin(0, 0, 30, 30)
    gdf = depth_to_polygon(depth, transform, crs="EPSG:32644")  # placeholder UTM zone
    print(gdf[["max_depth_m", "area_km2"]])
    export(gdf, "outputs/flood_extent")
