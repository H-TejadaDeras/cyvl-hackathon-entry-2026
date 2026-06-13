"""Phase 2a: build a bare-earth Digital Elevation Model (DEM) from the LiDAR.

The point cloud is unclassified (every point is ASPRS class 0) and colorized
mobile-mapping data, so we cannot filter by a ground class. Instead we grid the
points and take a LOW Z percentile per cell: cars, trees, poles and building
faces sit above the ground, so a low quantile of the points falling in a cell
approximates the bare-earth / road surface. Gross outliers (e.g. multipath
points tens of meters below grade) are clipped globally first.

Output: a single-band GeoTIFF DEM (meters, UTM 19N) over the demo tile, plus
nodata gaps filled by nearest-neighbour and a light smoothing pass.

Run:
    python -m curbrisk.ingest.lidar_dem
"""
from __future__ import annotations

import time

import numpy as np
import laspy
import geopandas as gpd
import rasterio
from rasterio.features import geometry_mask
from rasterio.transform import from_origin
from scipy import ndimage

from curbrisk import config as C

CORRIDOR_BUFFER_M = 8.0  # keep DEM cells within this distance of pavement

GROUND_QUANTILE = 0.10   # per-cell low quantile used as the ground estimate
# This cloud's ground sits in the lower Z band; building tops / tree canopy are
# the highest points. Drop the lowest sliver (multipath) and the top decile
# (structures/vegetation) before gridding so cells read bare-earth, not rooftops.
Z_CLIP_LOW_PCT = 0.5     # drop points below this global percentile (low multipath)
Z_CLIP_HIGH_PCT = 90.0   # drop points above this global percentile (buildings/trees)

# This is a dense mobile cloud (50M+ pts, ~200 MB LAZ). Holding it as float64
# x/y/z peaks past available RAM, so we stream it in chunks and keep only a
# compact (cell_id int64, z float32) representation of the in-tile points.
CHUNK = 8_000_000             # points per streaming chunk (bounds peak RAM)
Z_SAMPLE_STRIDE = 10          # stride for the global Z-percentile sample pass
MAX_GRID_POINTS = 12_000_000  # cap on collected in-tile pts (subsample if above)


def _accumulate_low_z(grid_min: np.ndarray, ix: np.ndarray, iy: np.ndarray, z: np.ndarray) -> None:
    """In-place per-cell minimum of z into grid_min[iy, ix]."""
    flat = iy * grid_min.shape[1] + ix
    np.minimum.at(grid_min.reshape(-1), flat, z)


def build_dem() -> None:
    minx, miny, maxx, maxy = C.LIDAR_BOUNDS_UTM
    res = C.DEM_RES_M
    ncols = int(np.ceil((maxx - minx) / res))
    nrows = int(np.ceil((maxy - miny) / res))
    print(f"DEM grid: {nrows} rows x {ncols} cols @ {res} m  "
          f"({nrows * ncols:,} cells)")

    minx_f, miny_f, maxx_f, maxy_f = map(float, (minx, miny, maxx, maxy))
    t0 = time.time()

    # --- Pass 1: global Z-clip thresholds (strided sample) + in-tile count ----
    # Stream the cloud so we never hold all 50M+ points in RAM at once.
    z_samp, n_tile, n_total = [], 0, 0
    with laspy.open(C.LIDAR_LAZ) as f:
        for pts in f.chunk_iterator(CHUNK):
            x = np.asarray(pts.x); y = np.asarray(pts.y); z = np.asarray(pts.z)
            n_total += len(z)
            z_samp.append(z[::Z_SAMPLE_STRIDE].astype(np.float32))
            n_tile += int(((x >= minx_f) & (x < maxx_f)
                           & (y >= miny_f) & (y < maxy_f)).sum())
    lo, hi = np.percentile(np.concatenate(z_samp), [Z_CLIP_LOW_PCT, Z_CLIP_HIGH_PCT])
    del z_samp
    print(f"Ground band: [{lo:.2f}, {hi:.2f}] m  "
          f"(streamed {n_total:,} pts in {time.time()-t0:.1f}s)")

    # If the in-tile cloud is huge, subsample so the gridding stays in memory.
    # A low per-cell quantile is statistically stable under uniform subsampling.
    keep = min(1.0, MAX_GRID_POINTS / max(n_tile, 1))
    print(f"Points in tile: {n_tile:,}"
          + ("" if keep >= 1.0 else f"  (subsampling ~{keep*100:.0f}% to cap RAM)"))

    # --- Pass 2: collect compact in-tile (cell_id, z) -------------------------
    rng = np.random.default_rng(42)   # fixed seed => reproducible subsample/DEM
    cell_parts, z_parts = [], []
    with laspy.open(C.LIDAR_LAZ) as f:
        for pts in f.chunk_iterator(CHUNK):
            x = np.asarray(pts.x); y = np.asarray(pts.y); z = np.asarray(pts.z)
            m = ((x >= minx_f) & (x < maxx_f) & (y >= miny_f) & (y < maxy_f)
                 & (z >= lo) & (z <= hi))
            if keep < 1.0:
                m &= rng.random(len(x)) < keep
            xi, yi = x[m], y[m]
            zi = z[m].astype(np.float32)
            # Cell indices. Row 0 = top (north), so flip the Y axis.
            ix = np.clip(((xi - minx_f) / res).astype(np.int64), 0, ncols - 1)
            iy = np.clip(((maxy_f - yi) / res).astype(np.int64), 0, nrows - 1)
            cell_parts.append(iy * ncols + ix)
            z_parts.append(zi)
    cell = np.concatenate(cell_parts)
    z = np.concatenate(z_parts)
    del cell_parts, z_parts
    print(f"Gridding {len(z):,} points into {nrows * ncols:,} cells")

    # Robust ground estimate per cell: a low quantile, computed by sorting points
    # into cells and taking the q-th value (nearest-rank, robust to low outliers).
    order = np.argsort(cell, kind="stable")
    cell_sorted = cell[order]
    z_sorted = z[order]
    del cell, z, order
    # Boundaries between cells in the sorted array.
    starts = np.searchsorted(cell_sorted, np.arange(nrows * ncols), side="left")
    ends = np.searchsorted(cell_sorted, np.arange(nrows * ncols), side="right")

    dem = np.full(nrows * ncols, np.nan, dtype=np.float32)
    counts = ends - starts
    for c in np.where(counts > 0)[0]:
        seg = z_sorted[starts[c]:ends[c]]
        k = int(GROUND_QUANTILE * (len(seg) - 1))
        dem[c] = np.partition(seg, k)[k]
    dem = dem.reshape(nrows, ncols)
    filled_frac = np.isfinite(dem).mean()
    print(f"Cells with data (raw): {filled_frac*100:.1f}%")

    transform = from_origin(minx, maxy, res, res)

    # Restrict to the road corridor: off-road cells are contaminated by building
    # facades / tree canopy and are not part of any street profile anyway.
    seg = gpd.read_file(C.SEGMENTS_OUT).to_crs(C.UTM19N)
    corridor = seg.geometry.buffer(CORRIDOR_BUFFER_M).union_all()
    outside = geometry_mask([corridor], out_shape=(nrows, ncols),
                            transform=transform, invert=False)
    dem[outside] = np.nan
    corridor_frac = np.isfinite(dem).mean()
    print(f"Cells in road corridor with data: {corridor_frac*100:.1f}%")

    # Fill small nodata gaps inside the corridor by nearest-neighbour, then
    # lightly smooth to suppress decluttering noise without erasing curb/gutter
    # relief. Cells outside the corridor stay nodata.
    inside = ~outside
    # Nearest-neighbour fill across the whole grid first (gives every cell a
    # valid ground value via extrapolation), smooth that continuous field, then
    # re-apply the corridor mask. This avoids smoothing against nodata/zeros.
    known = np.isfinite(dem)
    idx = ndimage.distance_transform_edt(~known, return_distances=False, return_indices=True)
    filled = dem[tuple(idx)]
    filled = ndimage.median_filter(filled, size=3)
    filled = ndimage.gaussian_filter(filled, sigma=1.0)
    dem = np.where(inside, filled, np.nan)
    with rasterio.open(
        C.DEM_OUT, "w", driver="GTiff", height=nrows, width=ncols, count=1,
        dtype="float32", crs=C.UTM19N, transform=transform, nodata=np.nan,
        compress="deflate",
    ) as dst:
        dst.write(dem.astype(np.float32), 1)

    print(f"\nDEM elevation range: {np.nanmin(dem):.2f} – {np.nanmax(dem):.2f} m "
          f"(relief {np.nanmax(dem)-np.nanmin(dem):.2f} m)")
    print(f"Wrote {C.DEM_OUT}  in {time.time()-t0:.1f}s total")


if __name__ == "__main__":
    build_dem()
