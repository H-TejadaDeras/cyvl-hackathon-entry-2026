# CurbRisk — drainage risk scoring from Cyvl LiDAR + open data

Per-street-segment **CurbRisk** score (0–100) for Somerville, MA. Ingests Cyvl's
LiDAR point cloud and CV pavement scores, models road-surface ponding at a 2-inch
storm, cross-references municipal 311 flood complaints and storm-drain data, and
serves a queryable API that returns a drainage risk report (with a measurable
cross-section) for any address in seconds.

## Demo footprint
The supplied LiDAR is a single ~349 m × 220 m tile (`global_xyz_rgb_icgu_…laz`,
53.5 M points, UTM 19N). It densely covers the streets the survey vehicle drove —
in practice the **Avon Street** corridor — which is the MVP demo area. Pavement
scores cover all 199 segments in the tile; segments without LiDAR get an imputed
topo component, flagged `lidar_measured: false` in the API.

## Pipeline
```
ingest/cyvl_ingest.py   Cyvl pavement segments + catch basins → clipped to tile
ingest/lidar_dem.py     point cloud → corridor-masked bare-earth DEM (GeoTIFF)
ingest/lidar_ground.py  shared ground sampler (low-percentile Z, KDTree)
ingest/opendata.py      Somerville 311 flood complaints + storm drains (cached)
scoring/topo.py         street profiles → low points, catchment, ponding volume
scoring/risk.py         CurbRisk = topo(40)+pavement(30)+basin(20)+complaint(10)
ingest/imagery.py       per-segment nearest Cyvl street imagery index (for Claude)
output/narrative.py     Claude summary for top risks (structured offline fallback)
output/crosssection.py  ezdxf DXF + SVG cross-section per low point
output/aps_upload.py    DXF → Autodesk APS Viewer URN (SVG fallback w/o creds)
api/main.py             FastAPI: GET /risk?address=… → JSON report + cross-section;
                        GET /map → ranked risk map of the whole demo tile
```

## Run
```bash
pip install -r curbrisk/requirements.txt        # numpy<2 is required (see file)
python -m curbrisk.run_pipeline                  # builds all processed artifacts
uvicorn curbrisk.api.main:app --port 8000        # then open http://localhost:8000
```
Optional Autodesk APS Viewer (else SVG fallback is served):
```bash
export APS_CLIENT_ID=…  APS_CLIENT_SECRET=…
python -m curbrisk.output.aps_upload
```
Optional Claude summaries (the root `.env` is loaded automatically):
```bash
ANTHROPIC_API_KEY=… python -m curbrisk.output.narrative
```
The API also accepts coordinates: `/risk?lat=42.3855&lon=-71.1020`. Queries
outside the LiDAR tile return a clear out-of-coverage response. The ranked
risk map is at `/map` — every block colored by CurbRisk band, with modeled
low points, storm drains, and 311 flood reports overlaid and click-through to
each block's full report.

## Scoring model (auditable, weights in `config.py`)
| component | weight | signal |
|---|---|---|
| topo | 40 | modeled ponding depth + catchment at nearest low point (LiDAR) |
| pavement | 30 | Cyvl PCI — cracked/failed pavement pools water |
| basin | 20 | distance to nearest drainage structure (Cyvl basin / storm drain) |
| complaint | 10 | count of nearby 311 flood reports (ground truth) |

## Ponding model (per low point)
Runoff volume = catchment_area × (2 in / 12 × runoff_coeff 0.9). Depth = volume /
ponded footprint, **capped by spill depth** (rise from the sag to its overflow
crest, measured from the LiDAR profile). Volume = depth × footprint. All
assumptions are documented inline in `scoring/topo.py`.

## Status (this build)
- **Validated end-to-end on real data:** ingest (199 segments, 9 streets),
  DEM build (53.5 M pts → corridor DEM), topo (9 low points on Avon St, ponding
  0.3–5.9 in with coherent downhill drainage).
- **Authored, ready to run:** open-data fetch, risk scoring + SQLite cache,
  cross-section DXF/SVG, APS upload, FastAPI service. Run `run_pipeline` to
  produce `curbrisk_scores.geojson`, `scores.db`, and the cross-sections.
