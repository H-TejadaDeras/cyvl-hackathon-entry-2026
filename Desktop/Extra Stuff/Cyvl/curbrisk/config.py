"""Central configuration for the CurbRisk pipeline.

All paths are absolute and rooted at the repo so any module can `from curbrisk.config import ...`
regardless of the working directory it is launched from.
"""
from __future__ import annotations

from pathlib import Path

# --- Paths -------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR                       # the raw Cyvl deliverables live directly in data/
PROCESSED_DIR = DATA_DIR / "processed"   # clean, reprojected layers we generate
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

# Raw Cyvl deliverables (local copies of the Marketing Demo project)
PAVEMENT_SHP = RAW_DIR / "CityofSomervilleMAMarketingDemo-30ft Pavement Scores" / "layer_zip.shp"
ASSETS_GEOJSON = RAW_DIR / "CityofSomervilleMAMarketingDemo-aboveGroundAssets.geojson"
CENTERLINE_SHP = RAW_DIR / "CityofSomervilleMAMarketingDemo-centerline" / "somerville_ma_streets_final_2.shp"
LIDAR_LAZ = RAW_DIR / "global_xyz_rgb_icgu_5122_4000_4988.laz"

# Processed outputs
SEGMENTS_OUT = PROCESSED_DIR / "segments.geojson"        # pavement segments in the demo tile
BASINS_OUT = PROCESSED_DIR / "catch_basins.geojson"      # catch basins in the demo tile
DEM_OUT = PROCESSED_DIR / "dem.tif"                      # gridded ground-surface DEM (UTM)
LOWPOINTS_OUT = PROCESSED_DIR / "low_points.geojson"     # detected ponding points
SCORES_OUT = PROCESSED_DIR / "curbrisk_scores.geojson"  # final scored segments
SCORES_DB = PROCESSED_DIR / "scores.db"                 # SQLite cache for the API

# --- Coordinate systems ------------------------------------------------------
WGS84 = "EPSG:4326"         # lat/lon, as delivered for vectors
UTM19N = "EPSG:32619"       # meters, the LiDAR's native CRS — all analysis happens here

# --- Cyvl project ------------------------------------------------------------
PROJECT_ID = "f15b854a-d203-49c7-bc25-1350dd4a1cd6"

# --- Demo tile ---------------------------------------------------------------
# The LiDAR is a single ~349m x 220m tile; it defines the MVP demo footprint.
# Bounds taken from the LAZ header (UTM 19N meters).
LIDAR_BOUNDS_UTM = (326801.79, 4694623.82, 327150.82, 4694843.35)  # (minx, miny, maxx, maxy)
LIDAR_BOUNDS_WGS84 = (-71.103994, 42.384602, -71.099823, 42.386656)
# Small buffer (m) so segments straddling the tile edge are still captured.
TILE_BUFFER_M = 20.0

# --- Hydrology / risk parameters --------------------------------------------
DEM_RES_M = 0.5            # DEM grid cell size in meters
SAMPLE_SPACING_M = 5.0     # along-segment elevation sampling interval
RAIN_EVENT_IN = 2.0        # design storm depth (inches) for ponding model
BASIN_INFLUENCE_M = 50.0   # a catch basin within this radius "serves" a low point
COMPLAINT_INFLUENCE_M = 100.0  # 311 flood complaint radius for weighting

# Risk score component weights (sum = 100)
W_TOPO = 40.0
W_PAVEMENT = 30.0
W_BASIN = 20.0
W_COMPLAINT = 10.0
