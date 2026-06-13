"""Phase 3a: fetch and cache municipal open data that validates/weights risk.

Two layers, both clipped to the demo tile:
  * 311 flooding complaints  — Somerville's Socrata 311 dataset, filtered to
    flooding / storm / catch-basin / standing-water service types. These are
    ground-truth flood reports at real coordinates.
  * storm-drain infrastructure — Cyvl found no catch basins inside this tile, so
    the drainage-infrastructure signal comes from the municipal storm-drain
    network (MassGIS / Somerville GIS). A low point far from any drain structure
    is higher risk.

Both fetchers cache their GeoJSON under data/processed/ so the rest of the
pipeline (and the API) runs offline. If a live endpoint is unreachable, we fall
back to a bundled sample so the demo still runs end-to-end.

Run:
    python -m curbrisk.ingest.opendata
"""
from __future__ import annotations

import json
from pathlib import Path

import requests
import geopandas as gpd
from shapely.geometry import Point, box

from curbrisk import config as C

COMPLAINTS_OUT = C.PROCESSED_DIR / "flood_complaints.geojson"
DRAINS_OUT = C.PROCESSED_DIR / "storm_drains.geojson"

# Somerville Socrata 311 service-requests dataset.
SOMERVILLE_311 = "https://data.somervillema.gov/resource/sxulr-rmsq.json"
FLOOD_TERMS = ["flood", "storm", "catch basin", "standing water", "drain", "sewer"]

# MassGIS storm-drain structures (ArcGIS FeatureServer) — point query by envelope.
# Endpoint may change; we degrade gracefully to a bundled sample on failure.
MASSGIS_DRAINS = (
    "https://services1.arcgis.com/hGdibHYSPO59RG1h/arcgis/rest/services/"
    "Massachusetts_Storm_Drains/FeatureServer/0/query"
)


def _tile_bbox_wgs84():
    return C.LIDAR_BOUNDS_WGS84  # (w, s, e, n)


def fetch_flood_complaints() -> gpd.GeoDataFrame:
    """311 flood-related complaints within (a generous buffer around) the tile."""
    w, s, e, n = _tile_bbox_wgs84()
    # widen to the neighbourhood so we capture nearby historical reports
    pad = 0.01
    where = " OR ".join([f"lower(case_title) like '%{t}%'" for t in FLOOD_TERMS])
    params = {
        "$where": f"({where}) AND latitude > {s-pad} AND latitude < {n+pad} "
                  f"AND longitude > {w-pad} AND longitude < {e+pad}",
        "$limit": 5000,
    }
    try:
        r = requests.get(SOMERVILLE_311, params=params, timeout=30)
        r.raise_for_status()
        rows = r.json()
    except Exception as exc:  # noqa: BLE001
        print(f"  [311] live fetch failed ({exc}); using bundled sample")
        rows = _sample_complaints()

    feats = []
    for row in rows:
        lat = row.get("latitude") or (row.get("location") or {}).get("latitude")
        lon = row.get("longitude") or (row.get("location") or {}).get("longitude")
        if lat is None or lon is None:
            continue
        feats.append({
            "geometry": Point(float(lon), float(lat)),
            "case_title": row.get("case_title") or row.get("type") or "flood report",
            "date": row.get("ticket_created_date_time") or row.get("open_dt") or "",
        })
    gdf = gpd.GeoDataFrame(feats, crs=C.WGS84) if feats else \
        gpd.GeoDataFrame(columns=["geometry", "case_title", "date"], crs=C.WGS84)
    return gdf


def fetch_storm_drains() -> gpd.GeoDataFrame:
    """Municipal storm-drain structures within the tile (with neighbourhood pad)."""
    w, s, e, n = _tile_bbox_wgs84()
    pad = 0.005
    params = {
        "where": "1=1",
        "geometry": f"{w-pad},{s-pad},{e+pad},{n+pad}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326", "outSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*", "f": "geojson",
    }
    try:
        r = requests.get(MASSGIS_DRAINS, params=params, timeout=30)
        r.raise_for_status()
        gj = r.json()
        gdf = gpd.GeoDataFrame.from_features(gj.get("features", []), crs=C.WGS84)
        if len(gdf) == 0:
            raise ValueError("no drains returned")
    except Exception as exc:  # noqa: BLE001
        print(f"  [drains] live fetch failed ({exc}); using bundled sample")
        gdf = _sample_drains()
    return gdf


def _sample_complaints():
    """Minimal bundled fallback so the pipeline runs without network.

    Two representative historical flood reports near the Avon St low corridor.
    """
    w, s, e, n = _tile_bbox_wgs84()
    cx, cy = (w + e) / 2, (s + n) / 2
    return [
        {"latitude": cy - 0.0006, "longitude": cx + 0.0004,
         "case_title": "Street flooding / standing water", "open_dt": "2023-09-12"},
        {"latitude": cy - 0.0009, "longitude": cx + 0.0007,
         "case_title": "Catch basin clogged - flooding", "open_dt": "2021-07-18"},
    ]


def _sample_drains():
    w, s, e, n = _tile_bbox_wgs84()
    cx, cy = (w + e) / 2, (s + n) / 2
    pts = [Point(cx - 0.0008, cy + 0.0005), Point(cx + 0.0010, cy - 0.0010)]
    return gpd.GeoDataFrame({"type": ["storm_drain"] * len(pts)}, geometry=pts, crs=C.WGS84)


def main() -> None:
    comp = fetch_flood_complaints()
    drains = fetch_storm_drains()
    # write (GeoJSON requires at least the schema; handle empties)
    comp.to_file(COMPLAINTS_OUT, driver="GeoJSON")
    drains.to_file(DRAINS_OUT, driver="GeoJSON")
    print(json.dumps({
        "flood_complaints": int(len(comp)),
        "storm_drains": int(len(drains)),
    }, indent=2))
    print(f"Wrote {COMPLAINTS_OUT}\nWrote {DRAINS_OUT}")


if __name__ == "__main__":
    main()
