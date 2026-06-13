"""Phase 6: actuarial insights + rain/snow storm simulator.

Turns a scored segment into five underwriter-facing numbers, and recomputes them
for an arbitrary storm (rain + snow sliders). Everything is derived from values
already in scores.db plus the synthetic crack index; assumptions are labelled.

  1. Ponding Volume (cf)        = catchment_sqft x ponding_depth_ft x runoff_coeff
  2. Storm Return Period (yr)   = NOAA Atlas 14 (Somerville) storm that drives
                                  significant ponding here
  3. Foundation Flow Vector     = (elev_lowpoint - elev_foundation) / dist x 100
                                  (+ toward structure, - away); foundation grade
                                  ESTIMATED from LiDAR until footprints arrive
  4. Crack Infiltration Index   = width x depth of synthetic cracks, weighted by
                                  proximity to the low point -> Low/Med/High
  5. Drainage Relief Score 0-100= 100 - [drain_m*0.8 + 311*0.5 + catch/100*0.3]

Run:
    python -m curbrisk.scoring.insights            # prints all 5 for a sample seg
"""
from __future__ import annotations

import json
import sqlite3

from curbrisk import config as C

RUNOFF_COEFF = 0.9                 # standard paved-urban runoff coefficient
PONDING_THRESHOLD_IN = 6.0         # "significant" ponding (curb height / impassable)
FOUNDATION_SETBACK_M = 8.0         # assumed road-centre -> foundation entry distance
FOUNDATION_RISE_M = 0.15           # assumed grade rise from crown to foundation entry
SNOW_TO_WATER = 0.10               # 10:1 snow-water-equivalent on melt

# NOAA Atlas 14 (Volume 10, Northeastern US) — 24-hour precipitation depth (inches)
# for ~Somerville, MA (42.39N, 71.10W). Bundled point estimate; label in the UI.
ATLAS14_SOMERVILLE_24H = {
    1: 2.7, 2: 3.2, 5: 4.0, 10: 4.7, 25: 5.8, 50: 6.8, 100: 8.0,
}


# --------------------------------------------------------------------------- #
# individual insights
# --------------------------------------------------------------------------- #
def ponding_volume_cf(catchment_sqft: float, ponding_depth_in: float) -> float:
    depth_ft = (ponding_depth_in or 0.0) / 12.0
    return round((catchment_sqft or 0.0) * depth_ft * RUNOFF_COEFF, 1)


def storm_return_period(ponding_depth_in: float) -> dict:
    """Return period of the storm that drives PONDING_THRESHOLD_IN of ponding here.

    Ponding scales ~linearly with rainfall depth, so the rainfall needed to reach
    the threshold is rain* = design_storm x threshold / modeled_ponding. We then
    read rain* against the Atlas 14 24-hr depths.
    """
    if not ponding_depth_in or ponding_depth_in <= 0:
        return {"years": None, "label": "No modeled sag ponding",
                "annual_exceedance_prob": None, "source": "NOAA Atlas 14 (Somerville, 24-hr)"}
    rain_star = C.RAIN_EVENT_IN * PONDING_THRESHOLD_IN / ponding_depth_in
    items = sorted(ATLAS14_SOMERVILLE_24H.items())
    if rain_star <= items[0][1]:
        rp, label = items[0][0], f"<{items[0][0]}-yr (frequent)"
    elif rain_star > items[-1][1]:
        rp, label = items[-1][0], f">{items[-1][0]}-yr (rare)"
    else:
        rp = next(yr for yr, d in items if d >= rain_star)
        label = f"~{rp}-yr storm"
    return {
        "years": rp,
        "label": label,
        "required_rain_in": round(rain_star, 2),
        "annual_exceedance_prob": round(1.0 / rp, 3) if rp else None,
        "threshold_in": PONDING_THRESHOLD_IN,
        "source": "NOAA Atlas 14 (Somerville, MA · 24-hr depths)",
    }


def foundation_flow_vector(lowpoint_elev_m, segment_grade_m) -> dict:
    """% grade from the street low point to the (estimated) foundation entry.

    + grade => low point sits above the foundation entry => water flows TOWARD
    the structure. Foundation entry elevation is ESTIMATED from the LiDAR road
    grade plus a standard rise, pending real building-footprint elevations.
    """
    if lowpoint_elev_m is None or segment_grade_m is None:
        return {"grade_pct": None, "direction": "unknown",
                "note": "insufficient LiDAR elevation"}
    foundation_elev = segment_grade_m + FOUNDATION_RISE_M
    grade_pct = (lowpoint_elev_m - foundation_elev) / FOUNDATION_SETBACK_M * 100.0
    toward = grade_pct > 0
    return {
        "grade_pct": round(grade_pct, 2),
        "direction": "toward structure" if toward else "away from structure (toward street)",
        "toward_structure": bool(toward),
        "assumed_setback_m": FOUNDATION_SETBACK_M,
        "note": "foundation entry elevation ESTIMATED from LiDAR grade "
                "(no building footprints yet)",
    }


def crack_infiltration_index(cracks: list | None) -> dict:
    """Width x depth of synthetic cracks weighted by proximity to the low point."""
    cracks = cracks or []
    score = 0.0
    for c in cracks:
        w = c.get("width_mm", 0.0)
        d = c.get("depth_mm", 0.0)
        prox = 1.0 / (1.0 + max(c.get("dist_to_low_m", 0.0), 0.0))  # 1 at sag -> 0 far
        score += w * d * prox
    score = round(score / 1000.0, 1)  # scale to a readable index
    band = "High" if score >= 8 else "Medium" if score >= 3 else "Low"
    return {
        "index": band,
        "score": score,
        "n_cracks": len(cracks),
        "synthetic": True,
        "note": "synthetic cracks (PCI-derived); depth is a placeholder until "
                "real distress vectors arrive",
    }


def drainage_relief_score(nearest_drain_m, complaints_nearby, catchment_sqft) -> dict:
    drain = nearest_drain_m if nearest_drain_m is not None else 50.0
    raw = 100.0 - ((drain * 0.8) + ((complaints_nearby or 0) * 0.5)
                   + ((catchment_sqft or 0.0) / 100.0 * 0.3))
    score = round(max(0.0, min(100.0, raw)), 1)
    return {
        "score": score,
        "drain_distance_m": round(drain, 1),
        "complaints_311": int(complaints_nearby or 0),
        "catchment_sqft": round(catchment_sqft or 0.0, 0),
        "interpretation": "lower = water escapes slower = longer exposure",
    }


# --------------------------------------------------------------------------- #
# assembly + simulator
# --------------------------------------------------------------------------- #
def compute_insights(row: dict, cracks: list | None = None,
                     ponding_override: float | None = None) -> dict:
    """Bundle the five insights for a scored-segment row (sqlite Row or dict)."""
    g = (lambda k, d=None: row[k] if k in row.keys() else d) if isinstance(row, sqlite3.Row) \
        else row.get
    ponding = ponding_override if ponding_override is not None else g("ponding_depth_in", 0.0)
    catchment = g("catchment_sqft", 0.0)
    lowpt_elev = g("lowpt_elev_m", None)
    grade = g("elev_mean", None)
    if grade is None:
        grade = g("elev_min", None)
    return {
        "ponding_volume": {
            "cubic_feet": ponding_volume_cf(catchment, ponding),
            "formula": "catchment_sqft x ponding_depth_ft x 0.9 runoff coeff",
        },
        "storm_return_period": storm_return_period(ponding),
        "foundation_flow_vector": foundation_flow_vector(lowpt_elev, grade),
        "crack_infiltration_index": crack_infiltration_index(cracks),
        "drainage_relief_score": drainage_relief_score(
            g("nearest_drain_m", None), g("complaints_nearby", 0), catchment),
    }


def simulate(row: dict, rain_in: float, snow_in: float = 0.0,
             cracks: list | None = None) -> dict:
    """Recompute ponding, topo, CurbRisk and the 5 insights for a chosen storm.

    Ponding scales linearly with effective rainfall vs the design storm, capped by
    the local overflow (spill) depth. Pavement/basin/311 components are storm
    independent (read back from the stored component points).
    """
    g = (lambda k, d=None: row[k] if k in row.keys() else d) if isinstance(row, sqlite3.Row) \
        else row.get
    base_ponding = g("ponding_depth_in", 0.0) or 0.0
    catchment = g("catchment_sqft", 0.0) or 0.0
    effective_rain = rain_in + snow_in * SNOW_TO_WATER
    scale = effective_rain / C.RAIN_EVENT_IN if C.RAIN_EVENT_IN else 1.0

    spill_in = (g("spill_depth_m", None) or 0.0) * 39.3701
    new_ponding = base_ponding * scale
    if spill_in > 0:
        new_ponding = min(new_ponding, spill_in)   # overflows past the divide
    new_ponding = round(new_ponding, 2)

    # topo component recomputed from new ponding (mirror of scoring.risk._topo_score)
    import numpy as np
    d = float(np.clip(new_ponding / 6.0, 0, 1))
    a = float(np.clip(catchment / 8000.0, 0, 1))
    topo = 0.7 * d + 0.3 * a
    pav_pts = g("pavement_pts", 0.0) or 0.0
    basin_pts = g("basin_pts", 0.0) or 0.0
    compl_pts = g("complaint_pts", 0.0) or 0.0
    curb_risk = round(C.W_TOPO * topo + pav_pts + basin_pts + compl_pts, 1)
    curb_risk = max(0.0, min(100.0, curb_risk))
    band = "High" if curb_risk >= 66 else "Moderate" if curb_risk >= 40 else "Low"

    insights = compute_insights(row, cracks=cracks, ponding_override=new_ponding)
    # in simulate mode, report the return period of the APPLIED storm
    insights["storm_return_period"] = _applied_return_period(effective_rain)
    return {
        "applied_storm": {"rain_in": round(rain_in, 2), "snow_in": round(snow_in, 2),
                          "effective_rain_in": round(effective_rain, 2),
                          "snow_water_equiv": SNOW_TO_WATER},
        "modeled_ponding_depth_in": new_ponding,
        "topo_pts": round(C.W_TOPO * topo, 1),
        "curb_risk_score": curb_risk,
        "risk_band": band,
        "insights": insights,
    }


def _applied_return_period(rain_in: float) -> dict:
    items = sorted(ATLAS14_SOMERVILLE_24H.items())
    if rain_in <= items[0][1]:
        rp, label = items[0][0], f"<{items[0][0]}-yr (frequent)"
    elif rain_in > items[-1][1]:
        rp, label = items[-1][0], f">{items[-1][0]}-yr (rare)"
    else:
        rp = next(yr for yr, dpt in items if dpt >= rain_in)
        label = f"~{rp}-yr storm"
    return {"years": rp, "label": label, "applied_rain_in": round(rain_in, 2),
            "annual_exceedance_prob": round(1.0 / rp, 3) if rp else None,
            "source": "NOAA Atlas 14 (Somerville, MA · 24-hr depths)"}


def _sample():
    con = sqlite3.connect(C.SCORES_DB)
    con.row_factory = sqlite3.Row
    row = con.execute("SELECT * FROM segments ORDER BY curb_risk DESC LIMIT 1").fetchone()
    con.close()
    if row is None:
        print("scores.db empty — run the pipeline first")
        return
    print(f"Segment {row['segment_id']} ({row['street']}) curb_risk={row['curb_risk']}")
    print(json.dumps(compute_insights(row), indent=2))
    print("\n-- simulate 4\" rain + 6\" snow --")
    print(json.dumps(simulate(row, rain_in=4.0, snow_in=6.0), indent=2))


if __name__ == "__main__":
    _sample()
