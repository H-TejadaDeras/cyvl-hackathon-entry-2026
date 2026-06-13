"""Run the full CurbRisk pipeline end-to-end, then print a demo query.

    python -m curbrisk.run_pipeline

Stages (each is independently runnable as `python -m curbrisk.<module>`):
  1. ingest.cyvl_ingest   — clip Cyvl pavement + catch basins to the LiDAR tile
  2. ingest.lidar_dem     — build the corridor DEM (optional visual)
  3. ingest.opendata      — fetch 311 flood complaints + storm drains
  4. scoring.topo         — low points, catchment, ponding from the point cloud
  5. scoring.risk         — CurbRisk score + SQLite cache
  6. output.crosssection  — DXF + SVG cross-sections per low point
  7. output.aps_upload    — translate to APS Viewer (or SVG fallback)
"""
from __future__ import annotations

import time

from curbrisk.ingest import cyvl_ingest, opendata, lidar_dem
from curbrisk.scoring import topo, risk
from curbrisk.output import crosssection, aps_upload


def main(build_dem: bool = True) -> None:
    t0 = time.time()
    steps = [
        ("Cyvl ingest", cyvl_ingest.main),
        ("Open data (311 + storm drains)", opendata.main),
    ]
    if build_dem:
        steps.append(("LiDAR DEM", lidar_dem.build_dem))
    steps += [
        ("Topo / low points", topo.analyze),
        ("Risk scoring", risk.compute),
        ("Cross-sections", crosssection.main),
        ("APS upload", aps_upload.upload_all),
    ]
    for name, fn in steps:
        print(f"\n{'='*60}\n>>> {name}\n{'='*60}")
        fn()
    print(f"\nPipeline complete in {time.time()-t0:.1f}s. "
          f"Start the API:  uvicorn curbrisk.api.main:app --port 8000")


if __name__ == "__main__":
    main()
