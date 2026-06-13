"""Build a per-segment imagery index from the Cyvl plain-imagery shapefile.

For each scored segment we find the N nearest plain (forward-facing) images
within a search radius and store their CDN URLs.  The result is a JSON file
at data/processed/imagery_index.json used by the API and the narrative
generator.

The plain-imagery CDN links are direct JPEG URLs suitable for Claude vision.
Panoramic links point to a 3-D viewer and are included separately for
reference.

Run:
    python -m curbrisk.ingest.imagery
"""
from __future__ import annotations

import json
import sqlite3

import numpy as np
import geopandas as gpd
from scipy.spatial import cKDTree
from pyproj import Transformer

from curbrisk import config as C

PLAIN_SHP = (
    C.RAW_DIR
    / "CityofSomervilleMAMarketingDemo-plainImagery"
    / "layer_zip.shp"
)
PANO_SHP = (
    C.RAW_DIR
    / "CityofSomervilleMAMarketingDemo-panoramicImagery"
    / "layer_zip.shp"
)
IMAGERY_OUT = C.PROCESSED_DIR / "imagery_index.json"

MAX_IMAGES = 3       # per segment
SEARCH_RADIUS_M = 40.0


def build_index() -> dict:
    # Load imagery points in UTM 19N for distance math
    plain = gpd.read_file(PLAIN_SHP).to_crs(C.UTM19N)
    pano = gpd.read_file(PANO_SHP).to_crs(C.UTM19N)

    plain_xy = np.c_[plain.geometry.x, plain.geometry.y]
    pano_xy = np.c_[pano.geometry.x, pano.geometry.y]
    plain_tree = cKDTree(plain_xy)
    pano_tree = cKDTree(pano_xy)

    # Transformer to convert WGS84 segment centroids → UTM 19N
    to_utm = Transformer.from_crs(C.WGS84, C.UTM19N, always_xy=True)

    con = sqlite3.connect(C.SCORES_DB)
    rows = con.execute("SELECT segment_id, lat, lon FROM segments").fetchall()
    con.close()

    index: dict[str, dict] = {}
    for seg_id, lat, lon in rows:
        cx, cy = to_utm.transform(lon, lat)
        pt = np.array([[cx, cy]])

        # plain images
        dists, idxs = plain_tree.query(pt, k=MAX_IMAGES, distance_upper_bound=SEARCH_RADIUS_M)
        plain_imgs = []
        for d, i in zip(dists[0], idxs[0]):
            if i >= len(plain) or not np.isfinite(d):
                continue
            row = plain.iloc[i]
            plain_imgs.append({
                "id": row["id"],
                "url": row["image_url"],
                "dist_m": round(float(d), 1),
                "bearing": round(float(row["bearing"]), 1) if row["bearing"] is not None else None,
            })

        # panoramic (viewer link, not a raw image)
        dists_p, idxs_p = pano_tree.query(pt[0], k=1, distance_upper_bound=SEARCH_RADIUS_M)
        pano_img = None
        if np.isscalar(idxs_p):
            dp, ip = float(dists_p), int(idxs_p)
        else:
            dp, ip = float(dists_p[0]), int(idxs_p[0])
        if ip < len(pano) and np.isfinite(dp):
            rp = pano.iloc[ip]
            pano_img = {
                "id": rp["id"],
                "viewer_url": rp["image_url"],
                "dist_m": round(dp, 1),
            }

        index[seg_id] = {
            "plain_images": plain_imgs,
            "panoramic": pano_img,
        }

    IMAGERY_OUT.write_text(json.dumps(index, indent=2))
    with_imgs = sum(1 for v in index.values() if v["plain_images"])
    print(f"Imagery index: {len(index)} segments, {with_imgs} have nearby plain images")
    print(f"Wrote {IMAGERY_OUT}")
    return index


def main() -> None:
    build_index()


if __name__ == "__main__":
    main()
