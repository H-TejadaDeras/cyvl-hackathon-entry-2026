"""Phase 1 ingest: load the local Cyvl deliverables, clip them to the LiDAR
demo tile, reproject to UTM 19N (meters), and write clean processed layers.

The LiDAR point cloud is a single ~349m x 220m tile, so it defines the MVP
footprint. We clip the pavement segments and catch basins to that tile (plus a
small buffer) so every downstream stage operates on a consistent area.

Run:
    python -m curbrisk.ingest.cyvl_ingest
"""
from __future__ import annotations

import json

import geopandas as gpd
from shapely.geometry import box

from curbrisk import config as C


def _tile_polygon_utm() -> gpd.GeoSeries:
    """The LiDAR tile footprint as a buffered polygon in UTM 19N."""
    minx, miny, maxx, maxy = C.LIDAR_BOUNDS_UTM
    poly = box(minx, miny, maxx, maxy).buffer(C.TILE_BUFFER_M)
    return gpd.GeoSeries([poly], crs=C.UTM19N)


def load_segments() -> gpd.GeoDataFrame:
    """Pavement segments (30ft) with PCI score, clipped to the demo tile."""
    g = gpd.read_file(C.PAVEMENT_SHP).to_crs(C.UTM19N)
    # Normalize columns to a stable schema.
    g = g.rename(columns={"address_st": "street", "score": "pci", "label": "pci_label"})
    keep = ["inspect_id", "client_seg", "street", "length_ft", "area_sqft",
            "pci", "pci_label", "geometry"]
    g = g[[c for c in keep if c in g.columns]]
    tile = _tile_polygon_utm()
    clipped = gpd.clip(g, tile)
    clipped = clipped[~clipped.geometry.is_empty & clipped.geometry.notna()]
    return clipped.reset_index(drop=True)


def load_catch_basins() -> gpd.GeoDataFrame:
    """Catch basins from the above-ground asset layer, clipped to the demo tile."""
    g = gpd.read_file(C.ASSETS_GEOJSON)
    g = g[g["asset_type"] == "CATCH_BASIN"].to_crs(C.UTM19N)
    keep = ["feature_id", "asset_type", "image_url", "condition", "geometry"]
    g = g[[c for c in keep if c in g.columns]]
    tile = _tile_polygon_utm()
    clipped = gpd.clip(g, tile)
    clipped = clipped[~clipped.geometry.is_empty & clipped.geometry.notna()]
    return clipped.reset_index(drop=True)


def main() -> None:
    segments = load_segments()
    basins = load_catch_basins()

    # Persist in WGS84 for portability/inspection; downstream code reprojects as needed.
    segments.to_crs(C.WGS84).to_file(C.SEGMENTS_OUT, driver="GeoJSON")
    basins.to_crs(C.WGS84).to_file(C.BASINS_OUT, driver="GeoJSON")

    summary = {
        "demo_tile_wgs84": C.LIDAR_BOUNDS_WGS84,
        "segments_in_tile": int(len(segments)),
        "catch_basins_in_tile": int(len(basins)),
        "pci_min": float(segments["pci"].min()) if len(segments) else None,
        "pci_max": float(segments["pci"].max()) if len(segments) else None,
        "pci_mean": round(float(segments["pci"].mean()), 1) if len(segments) else None,
        "streets": sorted(segments["street"].dropna().unique().tolist()),
    }
    print(json.dumps(summary, indent=2))
    print(f"\nWrote {C.SEGMENTS_OUT}")
    print(f"Wrote {C.BASINS_OUT}")


if __name__ == "__main__":
    main()
