"""Shared LiDAR ground sampler.

The cloud is dense mobile-mapping data (~700 pts/m^2 on the road corridor) with
no ground classification. We approximate the bare-earth / road surface at any
(x, y) by taking a low Z percentile of nearby points: vehicles, curbs, poles and
canopy sit above grade, so a low quantile within a small radius reads the road.

This module loads the ground-band points once (cached to .npy for fast reloads),
builds a 2-D KDTree, and exposes point/line sampling helpers in UTM 19N meters.
Both the topo analysis and the cross-section renderer use it, so the ground
definition is identical everywhere.
"""
from __future__ import annotations

import numpy as np
import laspy
from scipy.spatial import cKDTree

from curbrisk import config as C

# Points above this global percentile are structures/canopy; below the low one
# are multipath. Keep the band in between as candidate ground.
_LOW_PCT, _HIGH_PCT = 0.5, 90.0
_GROUND_PCTILE = 15.0          # low percentile of nearby points = ground
_GROUND_NPY = C.PROCESSED_DIR / "ground_points.npy"


class GroundSampler:
    def __init__(self, radius_m: float = 2.5):
        self.radius = radius_m
        xyz = self._load_points()
        self.xy = xyz[:, :2]
        self.z = xyz[:, 2]
        self.tree = cKDTree(self.xy)

    @staticmethod
    def _load_points() -> np.ndarray:
        if _GROUND_NPY.exists():
            return np.load(_GROUND_NPY)
        las = laspy.read(C.LIDAR_LAZ)
        z = np.asarray(las.z, dtype=np.float64)
        x = np.asarray(las.x, dtype=np.float64)
        y = np.asarray(las.y, dtype=np.float64)
        lo, hi = np.percentile(z, [_LOW_PCT, _HIGH_PCT])
        m = (z >= lo) & (z <= hi)
        xyz = np.c_[x[m], y[m], z[m]].astype(np.float32)
        np.save(_GROUND_NPY, xyz)
        return xyz

    def elevation(self, x: float, y: float, radius_m: float | None = None) -> float:
        """Ground elevation (m) at a point, or NaN if no points nearby."""
        r = radius_m or self.radius
        idx = self.tree.query_ball_point([x, y], r=r)
        if not idx:
            return float("nan")
        return float(np.percentile(self.z[idx], _GROUND_PCTILE))

    def profile(self, line, spacing_m: float = C.SAMPLE_SPACING_M, radius_m: float | None = None):
        """Sample a shapely LineString (UTM) at regular stations.

        Returns (distances, elevations) arrays; elevations may contain NaN.
        """
        n = max(int(line.length // spacing_m) + 1, 2)
        dists = np.linspace(0.0, line.length, n)
        elev = np.array([self.elevation(*line.interpolate(d).coords[0], radius_m=radius_m)
                         for d in dists])
        return dists, elev

    def transect(self, center, bearing_rad: float, half_width_m: float = 8.0, step_m: float = 0.25):
        """Sample a cross-section perpendicular to a road at `center` (shapely Point).

        Returns (offsets, elevations): offset 0 at centerline, negative = left.
        """
        offs = np.arange(-half_width_m, half_width_m + step_m, step_m)
        # perpendicular direction
        px, py = -np.sin(bearing_rad), np.cos(bearing_rad)
        elev = np.array([self.elevation(center.x + o * px, center.y + o * py) for o in offs])
        return offs, elev


_SHARED: GroundSampler | None = None


def get_sampler(radius_m: float = 2.5) -> GroundSampler:
    """Process-wide singleton so the KDTree is built only once."""
    global _SHARED
    if _SHARED is None:
        _SHARED = GroundSampler(radius_m=radius_m)
    return _SHARED
