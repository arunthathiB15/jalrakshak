"""
api.py
-------
Tiny local API that serves your run_demo.py outputs to the dashboard, so
the dashboard can fetch() your REAL simulation results instead of you
copy-pasting numbers by hand.

Run it with:
    uvicorn api:app --reload --port 8000

Then open jalrakshak_dashboard.html (see the fetch wiring note at the
bottom of this file / the chat message that shipped this) and it will
pull from http://localhost:8000/bundle and http://localhost:8000/extent.

Leave this running in its own terminal window while you use the
dashboard -- it just reads whatever is currently in outputs/, so re-run
run_demo.py and refresh the dashboard page to see updated results.
"""

import json
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="JALRAKSHAK local API")

# Allow the dashboard (opened as a local file or from claude.ai) to fetch from this server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"status": "ok", "endpoints": ["/bundle", "/extent"]}


@app.get("/bundle")
def get_bundle():
    try:
        with open("outputs/dashboard_bundle.json") as f:
            return json.load(f)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Run run_demo.py first -- outputs/dashboard_bundle.json not found.")


@app.get("/extent")
def get_extent():
    try:
        with open("outputs/flood_extent.geojson") as f:
            return json.load(f)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Run run_demo.py first -- outputs/flood_extent.geojson not found.")
