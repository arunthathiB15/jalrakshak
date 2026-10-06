"""
flood_extent.py
-----------------
Turns a breach hydrograph (from breach_hydrograph.py) into a time-stepped
flood inundation extent over a real DEM. This is the prototype's stand-in
for the full SPH + Delft3D coupled engine described in the architecture
document -- lightweight enough to run in the 2-day build window, while
still being mass-conservative and physically motivated.

Method ("volume-matched priority-flood"):
  1. From the breach point, compute a "fill level" for every DEM cell:
     the minimum water-surface elevation needed to flood that cell while
     staying hydraulically connected to the breach (classic priority-flood
     / connected-basin-fill algorithm, the same family of algorithm used
     for depression-filling in hydrology tools like WhiteboxTools/RichDEM).
  2. From the hydrograph, compute cumulative outflow volume over time.
  3. For each time step, binary-search the water-surface elevation whose
     priority-flood-connected volume matches the cumulative volume
     delivered so far -> gives a mass-conservative, physically consistent,
     growing flood extent + depth raster per time step (a time-slider).

This is NOT a substitute for solving the shallow-water equations -- it
does not capture momentum, velocity, or wave-front dynamics the way SPH
or Delft3D would. Be upfront about that in your report/demo: this proxy
gets you a defensible working extent + depth map fast; the roadmap item
is swapping this module for the real coupled solver.
"""

import heapq
import numpy as np


def priority_flood_fill_level(dem: np.ndarray, source_rc: tuple) -> np.ndarray:
    """For every cell, the minimum water-surface elevation required to
    inundate it while remaining connected to the source cell (breach
    location). Standard priority-flood / connected-fill algorithm."""
    nrows, ncols = dem.shape
    fill = np.full(dem.shape, np.inf, dtype=float)
    visited = np.zeros(dem.shape, dtype=bool)
    sr, sc = source_rc
    heap = [(float(dem[sr, sc]), sr, sc)]
    while heap:
        level, r, c = heapq.heappop(heap)
        if visited[r, c]:
            continue
        visited[r, c] = True
        fill[r, c] = level
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                nr, nc = r + dr, c + dc
                if 0 <= nr < nrows and 0 <= nc < ncols and not visited[nr, nc]:
                    new_level = max(level, float(dem[nr, nc]))
                    if new_level < fill[nr, nc]:
                        fill[nr, nc] = new_level
                        heapq.heappush(heap, (new_level, nr, nc))
    return fill


def _cumulative_volume(t: np.ndarray, q: np.ndarray) -> np.ndarray:
    cum = np.zeros(len(t))
    for i in range(1, len(t)):
        cum[i] = cum[i - 1] + 0.5 * (q[i] + q[i - 1]) * (t[i] - t[i - 1])
    return cum


def _volume_at_level(dem, fill_level, wse, cell_area):
    depth = np.clip(wse - dem, 0, None)
    depth = np.where(fill_level <= wse, depth, 0.0)
    return float(np.sum(depth) * cell_area), depth


def _wse_for_volume(dem, fill_level, target_vol, cell_area, lo, hi, iters=40):
    if target_vol <= 0:
        return lo, np.zeros_like(dem)
    for _ in range(iters):
        mid = (lo + hi) / 2
        vol, depth = _volume_at_level(dem, fill_level, mid, cell_area)
        if vol < target_vol:
            lo = mid
        else:
            hi = mid
    wse = (lo + hi) / 2
    _, depth = _volume_at_level(dem, fill_level, wse, cell_area)
    return wse, depth


def simulate_inundation(dem: np.ndarray, source_rc: tuple, t: np.ndarray, q: np.ndarray,
                         cell_size_m: float, n_frames: int = 10):
    """Returns a list of frames: [{time_s, wse, depth (2D array)}, ...].
    The last frame is the maximum inundation extent for the event."""
    cell_area = cell_size_m ** 2
    fill_level = priority_flood_fill_level(dem, source_rc)
    cum_vol = _cumulative_volume(t, q)

    frame_idx = np.unique(np.linspace(0, len(t) - 1, n_frames).astype(int))
    dem_min, dem_max = float(np.nanmin(dem)), float(np.nanmax(dem))
    frames = []
    for i in frame_idx:
        target_vol = cum_vol[i]
        wse, depth = _wse_for_volume(dem, fill_level, target_vol, cell_area, dem_min, dem_max + 30)
        frames.append({"time_s": float(t[i]), "wse": float(wse), "depth": depth,
                        "inundated_area_m2": float(np.sum(depth > 0.05) * cell_area)})
    return frames


def make_synthetic_valley_dem(shape=(150, 220), seed=0):
    """A quick synthetic valley DEM so you can test the whole pipeline
    end-to-end TODAY, before your real DEM download finishes. Replace with
    a real rasterio.open(...).read(1) array once you have the DEM."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:shape[0], 0:shape[1]]
    # Valley floor slopes gently downstream (x) and rises toward the banks (y)
    dem = 200 - 0.08 * x + 0.9 * np.abs(y - shape[0] / 2)
    dem += rng.normal(0, 0.4, shape)  # small terrain noise
    return dem.astype(float)


if __name__ == "__main__":
    from breach_hydrograph import generate_hydrograph

    dem = make_synthetic_valley_dem()
    source_rc = (dem.shape[0] // 2, 5)  # breach near the top of the valley

    t, q, params = generate_hydrograph(
        volume_m3=15_000_000, breach_height_m=12.0, failure_time_hr=1.0, mode="overtopping"
    )
    print("Hydrograph params:", params)

    frames = simulate_inundation(dem, source_rc, t, q, cell_size_m=30.0, n_frames=6)
    for f in frames:
        print(f"t={f['time_s']/60:6.1f} min | WSE={f['wse']:6.2f} m | "
              f"inundated area={f['inundated_area_m2']/1e6:6.3f} km2")

    np.save("outputs/max_depth.npy", frames[-1]["depth"])
    print("Saved outputs/max_depth.npy (final/maximum inundation depth raster)")
