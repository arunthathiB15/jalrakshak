"""
breach_hydrograph.py
---------------------
Generates a dam-breach outflow hydrograph (discharge vs. time) from basic
dam/reservoir parameters, using standard empirical dam-breach engineering
methods. This is the "how much water, how fast" input that feeds the
inundation engine (flood_extent.py).

Method:
  1. Average breach width from the Froehlich (2008) regression equation.
  2. Breach side slope from Froehlich (2008) typical values.
  3. Peak breach outflow from a broad-crested trapezoidal weir equation,
     once breach geometry is known (standard hydraulics treatment used
     across dam-break literature).
  4. A mass-conservative rising/falling hydrograph shape built around
     that peak, calibrated so total volume released ~= reservoir volume.

IMPORTANT: the exact coefficients in dam-breach regression equations vary
slightly between textbooks/papers. Before quoting these numbers in your
final report, cross-check against your primary source (Froehlich 2008,
or a secondary source such as FEMA's dam breach guidance / a HEC-RAS
breach-parameter reference) and cite that source, not this code comment.
"""

import numpy as np

G = 9.81  # m/s^2


def _trapz(y, x):
    """Version-safe trapezoidal integration (np.trapz was removed in NumPy 2.x
    in favor of np.trapezoid; this works on either version)."""
    y, x = np.asarray(y, dtype=float), np.asarray(x, dtype=float)
    if len(y) < 2:
        return 0.0
    return float(np.sum((y[1:] + y[:-1]) / 2.0 * np.diff(x)))


def froehlich_breach_width(volume_m3: float, breach_height_m: float, mode: str = "overtopping") -> float:
    """Average breach width (m): Bavg = 0.27 * Ko * Vw^0.32 * hb^0.04
    Ko = 1.4 (overtopping) or 1.0 (piping/seepage) -- commonly cited values.
    Vw = reservoir volume at failure (m3), hb = breach height (m).
    """
    ko = 1.4 if mode == "overtopping" else 1.0
    return 0.27 * ko * (volume_m3 ** 0.32) * (breach_height_m ** 0.04)


def breach_side_slope(mode: str = "overtopping") -> float:
    """Trapezoidal breach side slope (H:V)."""
    return 1.0 if mode == "overtopping" else 0.7


def peak_outflow_weir(breach_width_avg: float, breach_height: float, side_slope: float, cd: float = 1.7) -> float:
    """Peak breach discharge via broad-crested trapezoidal weir approximation
    at full breach development:
        Q = Cd * [ Bbottom * sqrt(2g) * H^1.5 + (8/15) * z * sqrt(2g) * H^2.5 ]
    """
    b_bottom = max(breach_width_avg - side_slope * breach_height, 0.5)
    h = breach_height
    rect_term = b_bottom * np.sqrt(2 * G) * h ** 1.5
    tri_term = (8.0 / 15.0) * side_slope * np.sqrt(2 * G) * h ** 2.5
    return cd * (rect_term + tri_term)


def generate_hydrograph(volume_m3: float, breach_height_m: float, failure_time_hr: float,
                         mode: str = "overtopping", n_steps: int = 200, cd: float = 1.7):
    """
    Returns (t_seconds, Q_cumecs, params_dict).

    Rising limb: breach develops linearly over `failure_time_hr`; discharge
    grows as (t/tf)^1.5, approximating simultaneous growth of breach width
    and depth (a common simplifying assumption in rapid breach modelling).

    Falling limb: exponential recession, with the decay constant solved so
    that the *total* volume under the hydrograph matches the reservoir
    volume (mass conservation) -- this keeps the hydrograph physically
    consistent even though the shape itself is a simplification of full
    reservoir-routing.
    """
    b_avg = froehlich_breach_width(volume_m3, breach_height_m, mode)
    z = breach_side_slope(mode)
    q_peak = peak_outflow_weir(b_avg, breach_height_m, z, cd)

    tf = failure_time_hr * 3600.0
    n_rise = max(n_steps // 3, 2)
    t_rise = np.linspace(0, tf, n_rise)
    q_rise = q_peak * (t_rise / tf) ** 1.5 if tf > 0 else np.array([q_peak])

    # Falling limb: exponential recession over a generic timescale (~tf),
    # shape only -- the absolute scale is fixed by mass conservation below,
    # not by this decay constant, so it doesn't need to be exact.
    n_fall = n_steps - n_rise
    tau = max(tf, 60.0)
    t_fall = np.linspace(tf, tf + 6.0 * tau, n_fall)
    q_fall = q_peak * np.exp(-(t_fall - tf) / tau)

    t = np.concatenate([t_rise, t_fall])
    q_shape = np.concatenate([q_rise, q_fall])

    # --- Mass conservation: rescale the whole hydrograph so the volume
    # under the curve exactly equals the reservoir volume released. This
    # is the step that matters most for credibility -- without it, the
    # weir-equation peak and the linear-growth shape can imply releasing
    # far more (or less) water than the reservoir actually holds. ---
    shape_volume = _trapz(q_shape, t)
    scale = (volume_m3 / shape_volume) if shape_volume > 0 else 1.0
    q = q_shape * scale
    q_peak_final = float(np.max(q))

    params = {
        "breach_avg_width_m": round(b_avg, 2),
        "breach_side_slope_HV": z,
        "peak_discharge_weir_estimate_cumecs": round(float(q_peak), 2),
        "peak_discharge_mass_conservative_cumecs": round(q_peak_final, 2),
        "failure_time_hr": failure_time_hr,
        "mode": mode,
        "total_volume_released_m3": round(_trapz(q, t), 1),
        "reservoir_volume_m3": volume_m3,
    }
    return t, q, params


if __name__ == "__main__":
    # Example: a mid-size earthen dam, ~25 m breach height, 15 million m3
    # reservoir, overtopping failure, 1.5 hr breach formation time.
    t, q, params = generate_hydrograph(
        volume_m3=15_000_000,
        breach_height_m=25.0,
        failure_time_hr=1.5,
        mode="overtopping",
    )
    print("Breach parameters:", params)
    print(f"Peak discharge (mass-conservative): {params['peak_discharge_mass_conservative_cumecs']:.0f} "
          f"m3/s at t={t[np.argmax(q)]/60:.1f} min")
    print(f"(Raw weir-equation estimate before rescaling: "
          f"{params['peak_discharge_weir_estimate_cumecs']:.0f} m3/s -- large gap vs. the "
          f"mass-conservative value usually means your dam height / reservoir volume / breach "
          f"height inputs are not mutually consistent for a real dam; double-check them against NRLD.)")

    import csv
    with open("outputs/hydrograph.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["time_seconds", "discharge_cumecs"])
        for ti, qi in zip(t, q):
            writer.writerow([round(float(ti), 1), round(float(qi), 2)])
    print("Saved outputs/hydrograph.csv")
