"""Phase 3a: build the municipal open-data layers that validate/weight risk,
from the REAL downloaded Somerville data (no live endpoints, no sample fallbacks).

Outputs (both WGS84, clipped to the demo tile + a neighbourhood buffer):
  * storm_drains.geojson     <- somerville_drainage/catch_basins.geojson (66)
                                + somerville_drainage/storm_inlets.geojson (577).
                                Drainage structures; distance-to-nearest feeds the
                                20% "basin" component of CurbRisk.
  * flood_complaints.geojson <- somerville_311/drainage_pavement_311.csv, filtered
                                to flooding / catch-basin / sewer / drain service
                                types and geolocated by joining the 15-digit
                                `block_code` (2020 Census block GEOID) to TIGER/Line
                                block centroids for MA Middlesex County (FIPS 25017).
                                BLOCK-level resolution — NOT exact coordinates.

The 311 CSV carries no lat/lon, so the 2020 TIGER block shapefile is downloaded and
cached on first run to resolve `block_code` -> block centroid. Complaints whose
block does not match a Middlesex block (e.g. outside the county) are dropped.

Run:
    python -m curbrisk.ingest.opendata
"""
from __future__ import annotations

import io
import json
import zipfile

import requests
import pandas as pd
import geopandas as gpd
from shapely.geometry import box

from curbrisk import config as C

COMPLAINTS_OUT = C.PROCESSED_DIR / "flood_complaints.geojson"
DRAINS_OUT = C.PROCESSED_DIR / "storm_drains.geojson"

# --- Real downloaded municipal data -----------------------------------------
DRAINAGE_DIR = C.DATA_DIR / "somerville_drainage"
CATCH_BASINS = DRAINAGE_DIR / "catch_basins.geojson"
STORM_INLETS = DRAINAGE_DIR / "storm_inlets.geojson"
CSV_311 = C.DATA_DIR / "somerville_311" / "drainage_pavement_311.csv"

# 2020 TIGER/Line tabulation blocks. For TIGER2020 the TABBLOCK20 layer is
# published per-STATE (MA = 25), not per-county; we filter to Middlesex (017)
# after loading. (The 2010-era county-level tl_2020_25017_* file does not exist.)
TIGER_URL = (
    "https://www2.census.gov/geo/tiger/TIGER2020/TABBLOCK20/"
    "tl_2020_25_tabblock20.zip"
)
TIGER_DIR = C.DATA_DIR / "tiger_blocks_25"
TIGER_SHP = TIGER_DIR / "tl_2020_25_tabblock20.shp"
MIDDLESEX_PREFIX = "25017"  # state 25 + county 017

# 311 service types that signal drainage / flood failures. Deliberately excludes
# Pothole and Street/road defect — those are pavement signals already captured by
# the PCI (pavement) component, not flood complaints.
FLOOD_TERMS = ["flood", "catch basin", "sewer", "drain", "standing water"]

# Neighbourhood buffer (degrees) around the LiDAR tile. The drainage network and
# historical complaints that affect our streets extend past the tile edge, so we
# keep a generous halo (~0.8-1.1 km) rather than clipping to the exact tile.
NBHD_PAD_DEG = 0.01


def _neighbourhood_box():
    w, s, e, n = C.LIDAR_BOUNDS_WGS84
    return box(w - NBHD_PAD_DEG, s - NBHD_PAD_DEG, e + NBHD_PAD_DEG, n + NBHD_PAD_DEG)


def _ensure_tiger():
    """Download + cache the 2020 TIGER block shapefile for MA Middlesex County."""
    if TIGER_SHP.exists():
        return TIGER_SHP
    TIGER_DIR.mkdir(parents=True, exist_ok=True)
    print(f"  [tiger] downloading {TIGER_URL} (~107 MB) ...")
    r = requests.get(TIGER_URL, timeout=600)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        zf.extractall(TIGER_DIR)
    if not TIGER_SHP.exists():
        raise FileNotFoundError(f"TIGER shapefile missing after extract: {TIGER_SHP}")
    print(f"  [tiger] extracted -> {TIGER_DIR}")
    return TIGER_SHP


def _block_centroids() -> pd.DataFrame:
    """15-digit block GEOID -> centroid lon/lat, from TIGER internal points."""
    shp = _ensure_tiger()
    blocks = gpd.read_file(shp)
    df = pd.DataFrame({
        "block_code": blocks["GEOID20"].astype(str).str.strip(),
        "lat": blocks["INTPTLAT20"].astype(float),
        "lon": blocks["INTPTLON20"].astype(float),
    })
    df = df[df["block_code"].str.startswith(MIDDLESEX_PREFIX)]  # Middlesex only
    df = df[~df["block_code"].duplicated()].set_index("block_code")
    return df


def build_storm_drains() -> gpd.GeoDataFrame:
    """Union of municipal catch basins + storm inlets, clipped to the neighbourhood."""
    if not CATCH_BASINS.exists() or not STORM_INLETS.exists():
        raise FileNotFoundError(
            f"Missing drainage data: {CATCH_BASINS} / {STORM_INLETS}")
    cb = gpd.read_file(CATCH_BASINS).to_crs(C.WGS84)
    si = gpd.read_file(STORM_INLETS).to_crs(C.WGS84)
    cb = cb.copy(); cb["struct_type"] = "catch_basin"
    si = si.copy(); si["struct_type"] = "storm_inlet"
    keep = ["struct_type", "FacilityID", "geometry"]
    cb = cb[[c for c in keep if c in cb.columns]]
    si = si[[c for c in keep if c in si.columns]]
    drains = gpd.GeoDataFrame(pd.concat([cb, si], ignore_index=True), crs=C.WGS84)
    drains = drains[drains.geometry.notna() & ~drains.geometry.is_empty]
    nb = _neighbourhood_box()
    drains = drains[drains.geometry.intersects(nb)].reset_index(drop=True)
    return drains


def build_flood_complaints() -> gpd.GeoDataFrame:
    """311 flood/drain complaints, geolocated to block centroids, clipped to nbhd."""
    if not CSV_311.exists():
        raise FileNotFoundError(f"Missing 311 CSV: {CSV_311}")
    df = pd.read_csv(CSV_311, dtype=str)
    pat = "|".join(FLOOD_TERMS)
    mask = df["type"].fillna("").str.lower().str.contains(pat)
    df = df[mask].copy()
    n_flood = len(df)
    df["block_code"] = df["block_code"].astype(str).str.strip()

    cent = _block_centroids()
    joined = df.join(cent, on="block_code", how="inner")  # inner => drop unmatched
    n_matched = len(joined)

    gdf = gpd.GeoDataFrame(
        {
            "block_code": joined["block_code"].values,
            "type": joined["type"].values,
            "date": joined.get("date_created", pd.Series([""] * n_matched)).values,
            "resolution": "block",  # block-centroid, NOT exact coordinate
        },
        geometry=gpd.points_from_xy(joined["lon"], joined["lat"]),
        crs=C.WGS84,
    )
    nb = _neighbourhood_box()
    gdf = gdf[gdf.geometry.intersects(nb)].reset_index(drop=True)
    print(f"  [311] flood-type rows={n_flood}  block-matched={n_matched}  "
          f"in-neighbourhood={len(gdf)}  (dropped {n_flood - n_matched} unmatched)")
    return gdf


def main() -> None:
    drains = build_storm_drains()
    comp = build_flood_complaints()

    if len(drains) == 0:
        raise RuntimeError("storm_drains came out empty — check drainage GeoJSON")
    if len(comp) == 0:
        raise RuntimeError("flood_complaints came out empty — check 311 CSV / TIGER join")

    drains.to_file(DRAINS_OUT, driver="GeoJSON")
    comp.to_file(COMPLAINTS_OUT, driver="GeoJSON")

    print(json.dumps({
        "storm_drains": int(len(drains)),
        "storm_drains_by_type": drains["struct_type"].value_counts().to_dict()
            if "struct_type" in drains.columns else {},
        "flood_complaints": int(len(comp)),
        "flood_complaints_by_type": comp["type"].value_counts().head(8).to_dict(),
    }, indent=2))
    print(f"Wrote {DRAINS_OUT}")
    print(f"Wrote {COMPLAINTS_OUT}")


if __name__ == "__main__":
    main()
