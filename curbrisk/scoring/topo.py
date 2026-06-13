"""Phase 2b: topographic analysis of the road network (street-centric).

The LiDAR tile densely covers the streets the survey vehicle actually drove
(here: Avon Street end-to-end, plus part of School Street). For each street we
merge its pavement segments into a continuous centerline, sample a longitudinal
ground profile from the LiDAR, and find drainage low points (sags):

  * interior sags  — local minima with real prominence (water ponds in the dip);
  * the street's global low point — its natural drainage collection point.

For every low point we estimate, from the 1-D street profile:
  * catchment area  — road length draining toward the sag x road width (sqft);
  * spill depth     — rise from the sag to the lower side before it overflows;
  * ponding depth   — design-storm runoff volume spread over the ponded
                       footprint, capped by spill depth;
  * ponding volume  — depth x footprint.

Outputs low_points.geojson and an elevation-augmented segments table.

Run:
    python -m curbrisk.scoring.topo
"""
from __future__ import annotations

import json

import numpy as np
import geopandas as gpd
from shapely.geometry import Point
from shapely.ops import linemerge
from scipy.signal import find_peaks

from curbrisk import config as C
from curbrisk.ingest.lidar_ground import get_sampler

RUNOFF_COEFF = 0.9            # impervious pavement runoff coefficient
PROFILE_SPACING_M = 2.0      # station spacing along the street profile
SAMPLE_RADIUS_M = 3.0        # ground-search radius per station
COVERAGE_MIN = 0.5           # min fraction of stations with LiDAR to use a street
SAG_PROMINENCE_M = 0.05      # min dip prominence to call an interior sag
DEFAULT_LANE_WIDTH_FT = 24.0
M2_TO_FT2 = 10.7639


def _street_lines(seg: gpd.GeoDataFrame):
    """Merge each street's segments into continuous line(s)."""
    for street, grp in seg.groupby("street"):
        merged = linemerge(grp.geometry.union_all())
        lines = list(merged.geoms) if merged.geom_type == "MultiLineString" else [merged]
        yield street, grp, lines


def _segment_width_ft(grp: gpd.GeoDataFrame) -> float:
    w = (grp["area_sqft"] / grp["length_ft"].replace(0, np.nan)).median()
    return float(np.clip(w if np.isfinite(w) else DEFAULT_LANE_WIDTH_FT, 8, 60))


def _ponding_at(prof_d, prof_z, i_sag, width_ft):
    """Estimate spill depth, catchment, ponding depth/volume for a sag at index i_sag."""
    z_sag = prof_z[i_sag]
    # walk left/right until the profile rises to a local crest (overflow point)
    def crest(direction):
        j = i_sag
        peak = z_sag
        while 0 < j < len(prof_z) - 1:
            j += direction
            if not np.isfinite(prof_z[j]):
                break
            if prof_z[j] >= peak:
                peak = prof_z[j]
            if prof_z[j] < peak - 1e-6:  # started descending again past a crest
                break
        return peak, j
    crest_l, jl = crest(-1)
    crest_r, jr = crest(+1)
    spill_m = float(max(min(crest_l, crest_r) - z_sag, 0.02))

    # catchment: street length between the two crests draining into the sag
    seg_len_m = abs(prof_d[max(jr, i_sag)] - prof_d[min(jl, i_sag)])
    catch_sqft = seg_len_m * (width_ft / 3.28084)  # length(m) * width(m)
    catch_sqft *= M2_TO_FT2

    runoff_depth_ft = (C.RAIN_EVENT_IN / 12.0) * RUNOFF_COEFF
    runoff_vol_cf = catch_sqft * runoff_depth_ft
    # ponded footprint: stations within spill depth of the sag, x width
    near = np.abs(prof_z - z_sag) <= spill_m
    pond_len_m = max(PROFILE_SPACING_M, near.sum() * PROFILE_SPACING_M * 0.5)
    footprint_sqft = pond_len_m * (width_ft / 3.28084) * M2_TO_FT2
    depth_ft = min(runoff_vol_cf / footprint_sqft, spill_m * 3.28084) if footprint_sqft else 0.0
    return spill_m, catch_sqft, depth_ft * 12.0, depth_ft * footprint_sqft


def analyze() -> None:
    seg = gpd.read_file(C.SEGMENTS_OUT).to_crs(C.UTM19N)
    sampler = get_sampler()
    print(f"Loaded {len(sampler.z):,} ground points; analyzing {len(seg)} segments...")

    # --- per-segment elevation stats (used by scoring + cross-section) -------
    e_min, e_mean, cover = [], [], []
    for line in seg.geometry:
        _, elev = sampler.profile(line, spacing_m=PROFILE_SPACING_M, radius_m=SAMPLE_RADIUS_M)
        c = float(np.isfinite(elev).mean())
        cover.append(c)
        e_min.append(np.nanmin(elev) if c > 0 else np.nan)
        e_mean.append(np.nanmean(elev) if c > 0 else np.nan)
    seg["elev_min"] = e_min
    seg["elev_mean"] = e_mean
    seg["lidar_coverage"] = cover

    # --- street-centric low-point detection ----------------------------------
    low_points = []
    for street, grp, lines in _street_lines(seg):
        width_ft = _segment_width_ft(grp)
        for line in lines:
            d, z = sampler.profile(line, spacing_m=PROFILE_SPACING_M, radius_m=SAMPLE_RADIUS_M)
            if np.isfinite(z).mean() < COVERAGE_MIN or len(z) < 5:
                continue
            # interpolate small gaps so peak finding is stable
            ok = np.isfinite(z)
            z = np.interp(d, d[ok], z[ok])
            z_s = np.convolve(z, np.ones(3) / 3, mode="same")  # light smooth

            cand = set()
            # interior sags by prominence (invert: sags become peaks)
            peaks, _ = find_peaks(-z_s, prominence=SAG_PROMINENCE_M)
            cand.update(int(p) for p in peaks)
            # street's global low point (drainage collection), if interior-ish
            gmin = int(np.argmin(z_s))
            if 0 < gmin < len(z_s) - 1:
                cand.add(gmin)

            for i in sorted(cand):
                spill_m, catch_sqft, depth_in, vol_cf = _ponding_at(d, z_s, i, width_ft)
                if depth_in < 0.25:   # ignore trivially shallow ponding
                    continue
                pt = line.interpolate(d[i])
                # nearest segment to attribute this low point
                nearest_idx = int(grp.geometry.distance(pt).idxmin())
                low_points.append({
                    "geometry": pt,
                    "street": street,
                    "segment_id": str(seg.loc[nearest_idx, "inspect_id"]),
                    "elev_m": round(float(z_s[i]), 3),
                    "spill_depth_m": round(spill_m, 3),
                    "catchment_sqft": round(catch_sqft, 0),
                    "ponding_depth_in": round(depth_in, 2),
                    "ponding_volume_cf": round(vol_cf, 1),
                    "width_ft": round(width_ft, 1),
                })

    lp = gpd.GeoDataFrame(low_points, crs=C.UTM19N) if low_points else \
        gpd.GeoDataFrame(columns=["geometry"], crs=C.UTM19N)

    seg.to_crs(C.WGS84).to_file(C.PROCESSED_DIR / "segments_elev.geojson", driver="GeoJSON")
    if len(lp):
        lp.to_crs(C.WGS84).to_file(C.LOWPOINTS_OUT, driver="GeoJSON")

    print(json.dumps({
        "segments_with_lidar": int((seg["lidar_coverage"] > COVERAGE_MIN).sum()),
        "low_points": len(lp),
        "ponding_depth_in_max": float(lp["ponding_depth_in"].max()) if len(lp) else None,
    }, indent=2))
    if len(lp):
        print("\nLow points:")
        print(lp[["street", "segment_id", "elev_m", "spill_depth_m",
                  "catchment_sqft", "ponding_depth_in"]].to_string(index=False))
        print(f"\nWrote {C.LOWPOINTS_OUT}")


if __name__ == "__main__":
    analyze()
