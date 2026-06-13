"""Phase 3b: compute the per-segment CurbRisk score.

CurbRisk (0-100, higher = worse) blends four signals, each scaled 0-1 then
weighted (weights live in config so they're auditable):

  topo (40)      — modeled ponding at the nearest low point: depth and catchment.
  pavement (30)  — Cyvl PCI; cracked/failed pavement sheds water and pools.
  basin (20)     — distance to the nearest drainage structure (Cyvl catch basin
                   or municipal storm drain); far = worse. Inside this tile Cyvl
                   found none, so the municipal storm-drain layer carries it.
  complaint (10) — 311 flood reports nearby validate/upweight modeled risk.

Segments without LiDAR get a topo score imputed from their street's mean (flagged
`lidar=False`) so every address still returns a score; the API surfaces the flag.

Output: curbrisk_scores.geojson and a SQLite cache for fast API lookup.

Run:
    python -m curbrisk.scoring.risk
"""
from __future__ import annotations

import json
import sqlite3

import numpy as np
import geopandas as gpd

from curbrisk import config as C

PONDING_DEPTH_NORM_IN = 6.0      # ponding depth (in) that saturates the topo score
CATCHMENT_NORM_SQFT = 8000.0     # catchment that saturates the topo score
PCI_FLOOR = 30.0                 # PCI at/below this saturates the pavement score

HYDRAULIC_ASSUMPTIONS = {
    "rain_event_in": C.RAIN_EVENT_IN,
    "runoff_coefficient": 0.9,
    "model": "Simplified surface ponding model; no pipe-network hydraulics.",
    "vertical_accuracy": "LiDAR stores 1 cm Z precision; absolute vertical accuracy is not 1 cm.",
}


def _nearest_dist_m(pts_gdf: gpd.GeoDataFrame, target) -> float:
    if pts_gdf is None or len(pts_gdf) == 0:
        return np.inf
    return float(pts_gdf.geometry.distance(target).min())


def _topo_score(depth_in: float, catch_sqft: float) -> float:
    d = np.clip(depth_in / PONDING_DEPTH_NORM_IN, 0, 1)
    a = np.clip(catch_sqft / CATCHMENT_NORM_SQFT, 0, 1)
    return float(0.7 * d + 0.3 * a)   # depth dominates, catchment modulates


def _pavement_score(pci: float) -> float:
    if pci is None or not np.isfinite(pci):
        return 0.4
    return float(np.clip((100.0 - pci) / (100.0 - PCI_FLOOR), 0, 1))


def _basin_score(dist_m: float) -> float:
    # 0 risk when a drain is on top of the segment, →1 as distance ≥ influence radius
    if not np.isfinite(dist_m):
        return 1.0
    return float(np.clip(dist_m / C.BASIN_INFLUENCE_M, 0, 1))


def _complaint_score(n: int) -> float:
    return float(np.clip(n / 5.0, 0, 1))


def _recommended_action(
    risk: float, pavement: float, basin: float, topo: float, has_lidar: bool,
) -> str:
    """Choose one concise field action from the strongest risk signals."""
    if risk >= 66 and pavement >= 0.7:
        return "reconstruct"
    if not has_lidar:
        return "inspect" if risk >= 40 else "monitor"
    if basin >= 0.8 and topo >= 0.45:
        return "clear drainage"
    if pavement >= 0.55:
        return "crack-seal"
    if risk >= 40:
        return "inspect"
    return "monitor"


def _load(path):
    try:
        g = gpd.read_file(path)
        return g if len(g) else None
    except Exception:
        return None


def compute() -> None:
    seg = gpd.read_file(C.PROCESSED_DIR / "segments_elev.geojson").to_crs(C.UTM19N)
    low = _load(C.LOWPOINTS_OUT)
    if low is not None:
        low = low.to_crs(C.UTM19N)
    basins = _load(C.BASINS_OUT)
    drains = _load(C.PROCESSED_DIR / "storm_drains.geojson")
    comp = _load(C.PROCESSED_DIR / "flood_complaints.geojson")
    for g in (basins, drains, comp):
        if g is not None:
            g.to_crs(C.UTM19N, inplace=True)
    # unify drainage structures (Cyvl basins + municipal drains)
    drainage = None
    parts = [g for g in (basins, drains) if g is not None and len(g)]
    if parts:
        drainage = gpd.GeoDataFrame(
            __import__("pandas").concat([p[["geometry"]] for p in parts], ignore_index=True),
            crs=C.UTM19N)

    rows = []
    street_topo = {}  # street -> list of topo scores for imputation
    for _, sgmt in seg.iterrows():
        centroid = sgmt.geometry.interpolate(0.5, normalized=True)
        has_lidar = bool(sgmt.get("lidar_coverage", 0) and sgmt["lidar_coverage"] > 0.5)

        # --- topo: nearest low point within a short reach -------------------
        depth_in = catch_sqft = 0.0
        lp_dist = np.inf
        lowpt_elev_m = spill_depth_m = None
        if low is not None and len(low):
            di = low.geometry.distance(centroid)
            j = int(di.idxmin())
            lp_dist = float(di.loc[j])
            if lp_dist <= 40.0:  # the segment effectively contains/touches the sag
                depth_in = float(low.loc[j, "ponding_depth_in"])
                catch_sqft = float(low.loc[j, "catchment_sqft"])
                if "elev_m" in low.columns and np.isfinite(low.loc[j, "elev_m"]):
                    lowpt_elev_m = float(low.loc[j, "elev_m"])
                if "spill_depth_m" in low.columns and np.isfinite(low.loc[j, "spill_depth_m"]):
                    spill_depth_m = float(low.loc[j, "spill_depth_m"])
        topo = _topo_score(depth_in, catch_sqft)
        if has_lidar:
            street_topo.setdefault(sgmt["street"], []).append(topo)

        # --- pavement -------------------------------------------------------
        pav = _pavement_score(sgmt.get("pci"))

        # --- basin / drainage ----------------------------------------------
        dist_drain = _nearest_dist_m(drainage, centroid)
        basin = _basin_score(dist_drain)

        # --- 311 complaints -------------------------------------------------
        n_comp = 0
        if comp is not None and len(comp):
            n_comp = int((comp.geometry.distance(centroid) <= C.COMPLAINT_INFLUENCE_M).sum())
        compl = _complaint_score(n_comp)

        rows.append({
            "geometry": sgmt.geometry,
            "segment_id": sgmt.get("inspect_id"),
            "client_seg": sgmt.get("client_seg"),
            "street": sgmt.get("street"),
            "pci": round(float(sgmt["pci"]), 1) if np.isfinite(sgmt.get("pci", np.nan)) else None,
            "has_lidar": has_lidar,
            "ponding_depth_in": round(depth_in, 2),
            "catchment_sqft": round(catch_sqft, 0),
            "low_point_dist_m": round(lp_dist, 1) if np.isfinite(lp_dist) else None,
            "nearest_drain_m": round(dist_drain, 1) if np.isfinite(dist_drain) else None,
            "complaints_nearby": n_comp,
            "elev_min": round(float(sgmt["elev_min"]), 3) if np.isfinite(sgmt.get("elev_min", np.nan)) else None,
            "elev_mean": round(float(sgmt["elev_mean"]), 3) if np.isfinite(sgmt.get("elev_mean", np.nan)) else None,
            "lowpt_elev_m": round(lowpt_elev_m, 3) if lowpt_elev_m is not None else None,
            "spill_depth_m": round(spill_depth_m, 3) if spill_depth_m is not None else None,
            "_topo": topo, "_pav": pav, "_basin": basin, "_compl": compl,
        })

    gdf = gpd.GeoDataFrame(rows, crs=C.UTM19N)

    # impute topo for non-LiDAR segments from their street mean (else global mean)
    global_topo = float(np.mean([r["_topo"] for r in rows if r["has_lidar"]] or [0.3]))
    def impute(r):
        if r["has_lidar"]:
            return r["_topo"]
        vals = street_topo.get(r["street"])
        return float(np.mean(vals)) if vals else global_topo
    gdf["_topo_eff"] = gdf.apply(impute, axis=1)

    gdf["curb_risk"] = (
        C.W_TOPO * gdf["_topo_eff"] + C.W_PAVEMENT * gdf["_pav"]
        + C.W_BASIN * gdf["_basin"] + C.W_COMPLAINT * gdf["_compl"]
    ).round(1)
    # component breakdown (points contributed) for transparency in the API
    gdf["topo_pts"] = (C.W_TOPO * gdf["_topo_eff"]).round(1)
    gdf["pavement_pts"] = (C.W_PAVEMENT * gdf["_pav"]).round(1)
    gdf["basin_pts"] = (C.W_BASIN * gdf["_basin"]).round(1)
    gdf["complaint_pts"] = (C.W_COMPLAINT * gdf["_compl"]).round(1)
    gdf["risk_band"] = np.select(
        [gdf["curb_risk"] >= 66, gdf["curb_risk"] >= 40],
        ["High", "Moderate"], default="Low")
    gdf["recommended_action"] = gdf.apply(
        lambda r: _recommended_action(
            float(r["curb_risk"]), float(r["_pav"]),
            float(r["_basin"]), float(r["_topo_eff"]), bool(r["has_lidar"])),
        axis=1,
    )
    gdf["hydraulic_assumptions"] = json.dumps(HYDRAULIC_ASSUMPTIONS, sort_keys=True)

    out = gdf.drop(columns=[c for c in gdf.columns if c.startswith("_")])
    out.to_crs(C.WGS84).to_file(C.SCORES_OUT, driver="GeoJSON")
    _write_sqlite(out.to_crs(C.WGS84))

    print(json.dumps({
        "segments_scored": int(len(out)),
        "curb_risk_min": float(out["curb_risk"].min()),
        "curb_risk_max": float(out["curb_risk"].max()),
        "curb_risk_mean": round(float(out["curb_risk"].mean()), 1),
        "band_counts": out["risk_band"].value_counts().to_dict(),
    }, indent=2))
    print("\nHighest-risk segments:")
    cols = ["street", "segment_id", "pci", "ponding_depth_in", "complaints_nearby",
            "curb_risk", "risk_band", "has_lidar"]
    print(out.sort_values("curb_risk", ascending=False)[cols].head(10).to_string(index=False))
    print(f"\nWrote {C.SCORES_OUT}\nWrote {C.SCORES_DB}")


def _write_sqlite(gdf: gpd.GeoDataFrame) -> None:
    """Flat table with centroid lat/lon + WKT geometry for fast API lookup."""
    con = sqlite3.connect(C.SCORES_DB)
    cur = con.cursor()
    cur.execute("DROP TABLE IF EXISTS segments")
    cur.execute("""
        CREATE TABLE segments (
            segment_id TEXT, client_seg TEXT, street TEXT, pci REAL, has_lidar INTEGER,
            ponding_depth_in REAL, catchment_sqft REAL, low_point_dist_m REAL,
            nearest_drain_m REAL, complaints_nearby INTEGER,
            topo_pts REAL, pavement_pts REAL, basin_pts REAL, complaint_pts REAL,
            curb_risk REAL, risk_band TEXT, recommended_action TEXT,
            hydraulic_assumptions TEXT, lat REAL, lon REAL, wkt TEXT,
            elev_min REAL, elev_mean REAL, lowpt_elev_m REAL, spill_depth_m REAL
        )""")
    for _, r in gdf.iterrows():
        c = r.geometry.interpolate(0.5, normalized=True)
        cur.execute(
            "INSERT INTO segments VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (r["segment_id"], r["client_seg"], r["street"], r["pci"], int(bool(r["has_lidar"])),
             r["ponding_depth_in"], r["catchment_sqft"], r["low_point_dist_m"],
             r["nearest_drain_m"], int(r["complaints_nearby"]),
             r["topo_pts"], r["pavement_pts"], r["basin_pts"], r["complaint_pts"],
             r["curb_risk"], r["risk_band"], r["recommended_action"],
             r["hydraulic_assumptions"], c.y, c.x, r.geometry.wkt,
             r["elev_min"], r["elev_mean"], r["lowpt_elev_m"], r["spill_depth_m"]))
    con.commit()
    con.close()


if __name__ == "__main__":
    compute()
