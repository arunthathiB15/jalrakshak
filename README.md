# JALRAKSHAK Prototype — 2-Day Build Guide

This is the **scoped-down, actually-buildable** version of the full JALRAKSHAK
architecture. Read this top-to-bottom once before you start typing.

## Reality check first (read this, it saves you time)

You cannot build real SPH + Delft3D in 2 days — nobody could, those are
multi-week-to-install research-grade solvers. What you're building instead is:

**A working pipeline: real DEM → breach hydrograph → simplified but
mass-conservative inundation model → dashboard with map + hydrograph +
`.shp`/`.kml` export → one validation comparison against a real historical
flood.**

That is a legitimate, honestly-described prototype of the architecture in
your solution document. Say so explicitly in your submission/demo: *"the
prototype implements a lightweight, mass-conservative inundation engine as
a working stand-in for the SPH+Delft3D coupled solver described in the
architecture; full solver integration is the next milestone."* Judges respect
that far more than an over-claimed black box.

## What's already done for you

`breach_hydrograph.py`, `flood_extent.py`, `gis_export.py`, and `run_demo.py`
are **tested and working** — run `python3 run_demo.py` right now (no data
download needed) and it will run the full pipeline on a synthetic DEM and
write real `.shp` / `.kml` / `.geojson` / `dashboard_bundle.json` files into
`outputs/`. Do this first, before anything else, so you know the pipeline
itself isn't your risk — only swapping in real data is.

```bash
pip install -r requirements.txt
python3 run_demo.py
```

---

## Step 1 — Pick your demo dam (30 min, do this first)

You need one dam with: a real entry in the National Register of Large Dams,
DEM coverage, and ideally a documented historical flood/failure to validate
against.

**Recommended: Machhu-II Dam, Morbi, Gujarat.** It's a real, catastrophic,
literal *dam break* (1979) with well-documented consequences — a stronger
validation story than a landslide-triggered event, since the PS is
specifically about dam break, not GLOF. If you'd rather keep the Rishiganga
narrative from your solution document for the predictive-layer story, that's
fine too — you can mention both, but pick **one** for the actual working demo.

Get its specs (height, reservoir capacity, coordinates) from:
- NRLD search: https://cwc.gov.in/national-register-large-dams
- India-WRIS: https://indiawris.gov.in/

Write these down now — you'll plug them into `run_demo.py`:
- Dam/breach latitude, longitude
- Dam height (m)
- Reservoir gross storage (m³)

## Step 2 — Get the DEM (1–2 hrs)

1. Go to https://earthexplorer.usgs.gov/ (SRTM 30 m) — free, needs a free
   USGS login. Search by your dam's coordinates, download the SRTM tile(s)
   covering ~20–30 km downstream of the dam.
2. Clip it to your area of interest (AOI) so the pipeline runs fast:
   ```bash
   gdalwarp -te <minlon> <minlat> <maxlon> <maxlat> srtm_tile.tif dem_clipped.tif
   ```
   (`gdal` comes with `pip install rasterio` on most systems; if `gdalwarp`
   isn't found, `apt install gdal-bin` or use QGIS's clip tool instead.)
3. Reproject to a metric CRS (needed so "cell size in metres" is correct):
   ```bash
   gdalwarp -t_srs EPSG:32644 dem_clipped.tif dem_utm.tif
   ```
   (EPSG:32644 = UTM zone 44N, roughly central India — check
   https://epsg.io for the right zone for your dam's longitude.)

Put `dem_utm.tif` in `data/`, then run:
```bash
python3 run_demo.py data/dem_utm.tif
```
You'll need to edit `run_demo.py`'s `source_rc` line — for a real DEM, convert
your breach lat/lon to a pixel row/col:
```python
import rasterio
with rasterio.open("data/dem_utm.tif") as src:
    row, col = src.index(breach_lon_in_dem_crs, breach_lat_in_dem_crs)
```
(Reproject your lat/lon to the DEM's CRS first if it isn't already UTM —
`pyproj.Transformer` or just do it in QGIS by clicking the point and reading
the coordinates in the DEM's CRS.)

## Step 3 — Set your dam's real parameters (15 min)

In `run_demo.py`, edit the `generate_hydrograph(...)` call:
```python
t, q, hydro_params = generate_hydrograph(
    volume_m3=<reservoir gross storage from NRLD>,
    breach_height_m=<dam height from NRLD>,
    failure_time_hr=1.0,   # reasonable default, cite a range in your report
    mode="overtopping",    # or "piping"
)
```
Run it again. Sanity-check the printed peak discharge against literature
values for a dam of similar size (order of magnitude should look reasonable,
not off by 100x — the script itself will warn you if the weir estimate and
mass-conservative value disagree wildly, which usually means your numbers
don't match a real dam).

## Step 4 — Validate against history (2–3 hrs, do NOT skip this)

This is the single most convincing thing you can show the jury.

1. On https://dataspace.copernicus.eu/ (free account), search Sentinel-1 SAR
   scenes for your chosen dam's location just before and during/after the
   historical flood date.
2. In QGIS (or a quick GEE script if you get to Step 6), compute a simple
   water mask from the SAR image (low backscatter = water) to get an
   approximate **observed flood extent polygon**.
3. Load both your simulated `outputs/flood_extent.geojson` and the observed
   polygon into QGIS (or straight into the dashboard, see Step 5) and show
   them side by side. Compute a rough overlap % — even an approximate
   number ("~60% areal overlap with the observed 1979 flood extent") is a
   massive credibility boost over an unvalidated simulation.

## Step 5 — Wire it to the dashboard (2–4 hrs)

Take `outputs/dashboard_bundle.json` and `outputs/flood_extent.geojson` and
either:
- **Fastest:** paste their contents directly into the `DATA` object at the
  top of the dashboard's `<script>` (see the published dashboard artifact —
  it's built to accept exactly this JSON shape).
- **Better for a live demo:** stand up the tiny FastAPI server below and
  have the dashboard `fetch()` it.

```python
# api.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import json

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"])

@app.get("/bundle")
def get_bundle():
    return json.load(open("outputs/dashboard_bundle.json"))

@app.get("/extent")
def get_extent():
    return json.load(open("outputs/flood_extent.geojson"))
```
```bash
uvicorn api:app --reload --port 8000
```

## Step 6 — Stretch goals, only if Steps 1–5 are done with time to spare

- A short Google Earth Engine script pulling live GPM IMERG rainfall for
  your AOI (even just printed to console) to back up the "near-real-time
  layer" claim in your document.
- A static "risk panel" mockup with a few pre-computed anomaly scores for
  the weak-zone layer — you don't need a real InSAR pipeline working in 2
  days, a clearly-labelled mockup of what it *would* show is honest and
  still demonstrates the concept.

## What to say when judges ask "where's the SPH/Delft3D?"

Be direct: *"This prototype validates the full pipeline — real terrain, a
physically-grounded breach hydrograph, mass-conservative inundation
mapping, GIS export, and a validation check against a real historical
event — with a lightweight inundation engine standing in for the coupled
SPH+Delft3D solvers, which is the immediate next milestone."* That's a
true, confident answer, not a dodge.
