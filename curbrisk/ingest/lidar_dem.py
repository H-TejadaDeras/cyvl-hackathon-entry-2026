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
import rasterio
from rasterio.transform import from_origin
from scipy import ndimage

from curbrisk import config as C

GROUND_QUANTILE = 0.10   # per-cell low quantile used as the ground estimate
Z_CLIP_LOW, Z_CLIP_HIGH = 0.001, 0.999  # global percentile clip for outliers
CHUNK = 5_000_000        # points per read chunk (keeps memory bounded)


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

    # First pass: stream the cloud to get a global Z range for outlier clipping.
    t0 = time.time()
    las = laspy.read(C.LIDAR_LAZ)
    z_all = np.asarray(las.z, dtype=np.float64)
    lo, hi = np.quantile(z_all, [Z_CLIP_LOW, Z_CLIP_HIGH])
    print(f"Z clip range: [{lo:.2f}, {hi:.2f}] m  (read {len(z_all):,} pts in {time.time()-t0:.1f}s)")

    x_all = np.asarray(las.x, dtype=np.float64)
    y_all = np.asarray(las.y, dtype=np.float64)

    # Keep points inside the tile and within the sane Z band.
    m = (x_all >= minx) & (x_all < maxx) & (y_all >= miny) & (y_all < maxy) & (z_all >= lo) & (z_all <= hi)
    x, y, z = x_all[m], y_all[m], z_all[m]
    print(f"Points in tile after clip: {len(x):,}")

    # Cell indices. Row 0 = top (north), so flip the Y axis.
    ix = np.clip(((x - minx) / res).astype(np.int64), 0, ncols - 1)
    iy = np.clip(((maxy - y) / res).astype(np.int64), 0, nrows - 1)

    # Robust ground estimate per cell: a low quantile. We approximate it
    # efficiently by sorting points into cells and taking the q-th value.
    cell = iy * ncols + ix
    order = np.argsort(cell, kind="stable")
    cell_sorted = cell[order]
    z_sorted = z[order]
    # Boundaries between cells in the sorted array.
    starts = np.searchsorted(cell_sorted, np.arange(nrows * ncols), side="left")
    ends = np.searchsorted(cell_sorted, np.arange(nrows * ncols), side="right")

    dem = np.full(nrows * ncols, np.nan, dtype=np.float32)
    counts = ends - starts
    nonempty = np.where(counts > 0)[0]
    for c in nonempty:
        seg = z_sorted[starts[c]:ends[c]]
        # low quantile (nearest-rank) — robust to a few low outliers
        k = int(GROUND_QUANTILE * (len(seg) - 1))
        dem[c] = np.partition(seg, k)[k]
    dem = dem.reshape(nrows, ncols)
    filled_frac = np.isfinite(dem).mean()
    print(f"Cells with data: {filled_frac*100:.1f}%")

    # Fill nodata gaps by nearest-neighbour, then lightly smooth to suppress
    # residual decluttering noise without erasing real curb/gutter relief.
    nan_mask = ~np.isfinite(dem)
    if nan_mask.any():
        idx = ndimage.distance_transform_edt(nan_mask, return_distances=False, return_indices=True)
        dem = dem[tuple(idx)]
    dem = ndimage.median_filter(dem, size=3)
    dem = ndimage.gaussian_filter(dem, sigma=1.0)

    transform = from_origin(minx, maxy, res, res)
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
