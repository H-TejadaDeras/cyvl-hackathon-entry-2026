# CurbRisk — Autonomous Build Task (Ralph Loop spec)

Re-read this file at the start of every iteration. The terrain half of the
pipeline (Cyvl ingest, LiDAR DEM, topo/low-points) is already built and
validated. Your job is stages 3, 5, 6, 7 plus the live API. After EACH stage,
print a one-line PASS/FAIL with the artifact path, and verify before continuing.

## Critical context
- Orchestrator: `curbrisk/run_pipeline.py` (stages: cyvl_ingest, opendata,
  lidar_dem, scoring.topo, scoring.risk, output.crosssection, output.aps_upload).
- Real municipal data is ALREADY downloaded — USE IT, never the sample fallbacks:
  - `data/somerville_drainage/{catch_basins(66),storm_inlets(577),catch_basin_laterals,sw_gravity_mains}.geojson`
    (WGS84; `sw_gravity_mains` has UPELEV/DOWNELEV/SLOPE/Diameter).
  - `data/somerville_311/drainage_pavement_311.csv` (26,994 rows). No lat/lon;
    location = `block_code` (15-digit Census block GEOID, e.g. 250173501051006 =
    MA / Middlesex / tract 3501.05 / block 1006) + `ward`.
- BUG in `curbrisk/ingest/opendata.py`: it queries 311 dataset `sxulr-rmsq` on
  `case_title`/`latitude`/`longitude` — wrong dataset, wrong columns. The real
  dataset is `4pyi-uqq6` with `block_code` and no coords. Rewire opendata.py to
  build its outputs from the downloaded files instead of stale endpoints/samples:
  - `storm_drains.geojson`  <- catch_basins.geojson + storm_inlets.geojson
  - `flood_complaints.geojson` <- the 311 CSV (filter to flooding / catch-basin /
    sewer / drain types), geolocated by joining `block_code` -> 2020 TIGER/Line
    block centroids for MA Middlesex County
    (https://www2.census.gov/geo/tiger/TIGER2020/TABBLOCK20/tl_2020_25017_tabblock20.zip).
    Drop unmatched blocks. Label results BLOCK-level, not exact-coordinate.
- Env: deps installed (numpy pinned <2). `.env` (gitignored) has valid
  APS_CLIENT_ID, APS_CLIENT_SECRET, ANTHROPIC_API_KEY. NOTHING auto-loads `.env`
  yet — add `from dotenv import load_dotenv; load_dotenv()` at the top of
  `curbrisk/config.py` (python-dotenv is installed).

## Steps (in order; fix the FIRST failing one each iteration, then re-run)
1. Add `load_dotenv()` to config.py; confirm `os.environ` sees APS_CLIENT_ID.
2. Download TIGER blocks; build block_code -> centroid lookup; rewire opendata.py;
   `python -m curbrisk.ingest.opendata` -> confirm REAL non-zero counts (not the
   2-point samples).
3. `python -m curbrisk.scoring.risk` -> confirm `data/processed/curbrisk_scores.geojson`
   + `scores.db` with a 0-100 score + 4 labeled components per segment; spot-check
   that low-lying Avon St segments score higher.
4. `python -m curbrisk.output.crosssection` (DXF + SVG), then
   `python -m curbrisk.output.aps_upload` -> confirm real APS auth + a Viewer URN
   (NOT the SVG fallback). If APS auth fails, print the exact error.
5. `uvicorn curbrisk.api.main:app --port 8000`; test
   `GET /risk?address=<a real Somerville address in the tile>` -> full JSON in
   <10s; an out-of-tile address -> clean out-of-coverage response. Time it.
6. `python -m curbrisk.run_pipeline` fresh -> confirm reproducibility.

## Rules
- Real data only — no sample fallbacks. Never commit `.env`/secrets.
- Do NOT delete the 575 MB `data/processed/ground_points.npy` cache (reuse it).
- Keep all assumed hydraulic values labeled in outputs.
- Don't loop on the same error twice without changing approach.

## DONE criteria (all must be true)
- `python -m curbrisk.run_pipeline` completes with no error, using real data.
- `curbrisk_scores.geojson` + `scores.db` exist with 0-100 scores + 4 components.
- The API returns a valid JSON risk report for an in-tile address in <10s and a
  clean out-of-coverage response for an out-of-tile address.

When ALL DONE criteria are verified, print a final summary (per-stage PASS/FAIL,
score range, whether the APS URN works, the demo curl command + a known-working
address) and output the tag:  <promise>CURBRISK DONE</promise>
