# CurbRisk — Frozen Interface Contracts

These four contracts are the **only** hard dependencies between the three teams. Freeze them; build
against the stubs in `sample/`. If a contract must change, announce it — it breaks another team.

Coordinate convention everywhere: **geometry is processed in EPSG:32619 (UTM 19N, meters)** and
**served / stored on disk as EPSG:4326 (WGS84)** — matching the existing `cyvl_ingest.py` pattern.

---

## C1 · `scores.db` (SQLite) + `scores.geojson`  —  Pipeline → API / AI / Autodesk

Owner: **Team A**. Consumers: Team C (API/AI), Team B (ids for the export bundle).

One row per 30-ft pavement segment, plus rows for detected drainage gaps (`kind` distinguishes them).
SQLite table `scores`; `scores.geojson` is the same rows as a FeatureCollection (WGS84).

| field | type | source | notes |
|---|---|---|---|
| `inspect_id` | str | Cyvl 30ft pavement | stable id (NF6) |
| `client_seg` | str | Cyvl | stable id, cross-tile merge key (NF6) |
| `kind` | str | pipeline | `"segment"` or `"gap"` |
| `street` | str | Cyvl | |
| `pci` | float | Cyvl | 0–100 |
| `drainage_gap_score` | float | scoring | 0–100, weighted composite |
| `pothole_risk_3mo` | float | scoring | 0–1 |
| `pothole_risk_6mo` | float | scoring | 0–1 |
| `pothole_risk_12mo` | float | scoring | 0–1 |
| `flow_accum` | float | hydro | upstream cell count |
| `sink_depth_m` | float | hydro | 0 if not a sink |
| `nearest_basin_m` | float | hydro | distance to nearest catch basin |
| `complaint_count_100m` | int | external 311 | within 100 m |
| `fema_zone` | str\|null | FEMA NFHL | e.g. `"AE"`, null if none |
| `action` | str | scoring | one of: inspect, seal, drain, monitor, reconstruct |
| `infodrainage` | json\|null | **loop-back C3** | nullable; `{peak_flow_cfs, surcharge_ft, flood_volume_cf, drainage_time_min}` |
| `geometry` | geom | Cyvl | LineString (segment) / Point (gap), WGS84 on disk |

> `infodrainage` is **nullable by design** — the app renders fully without it. It is populated only
> after Team B returns `results.csv` (C3). A CAD delay never blocks the demo.

---

## C2 · Autodesk export bundle (folder per tile)  —  Pipeline → Civil 3D

Owner: **Team A** (`curbrisk/export`). Consumer: **Team B**. Stub lives in `sample/`.

```
sample/                       (one such folder per tile)
  surface.landxml             # DTM as a LandXML TIN surface, Civil 3D imports natively
  catchments.geojson          # delineated catchment polygons (UTM19N) — see fields below
  basins.geojson              # catch-basin nodes from asset_type=="CATCH_BASIN"
  manifest.json               # provenance: every hydraulic field tagged measured|assumed (NF5)
```

`catchments.geojson` feature props: `catchment_id`, `area_m2`, `mean_slope_pct`,
`time_of_conc_min`, `peak_runoff_cfs` (Rational Method, 10-yr NOAA Atlas 14), `inspect_id`,
`client_seg`.

`basins.geojson` feature props: `feature_id`, `asset_type`, `grate_capacity_cfs` *(assumed)*,
`pipe_diameter_in` *(assumed)*, `invert_elev_m` *(assumed)*, `condition`, `image_url`.

`manifest.json`: `{ "tile_id", "crs", "generated_from", "fields": { "<field>": "measured"|"assumed" } }`.

---

## C3 · `results.csv`  —  InfoDrainage → Pipeline (loop-back)

Owner: **Team B**. Consumer: **Team A** (`curbrisk/export/infodrainage_ingest.py`).

Joined back into `scores.db` on `id`. One row per node per scenario:

| column | type | notes |
|---|---|---|
| `id` | str | matches `feature_id` (basin) or gap id from C1 |
| `scenario` | str | `baseline` or `intervention` |
| `peak_flow_cfs` | float | |
| `surcharge_ft` | float | |
| `flood_volume_cf` | float | |
| `drainage_time_min` | float | |

---

## C4 · API response  —  API → Web

Owner: **Team C** (`curbrisk/api`). Consumer: frontend.

- `GET /segments` → GeoJSON FeatureCollection of all segments (C1 props) for the map.
- `GET /gaps` → GeoJSON FeatureCollection of drainage gaps.
- `GET /crosssection/{inspect_id}` → `{ station[], ground_z[], water_z[] }` (water at 2-in storm).
- `GET /score?address=<str>` → geocode → nearest segment →
  ```json
  {
    "...C1 fields...": "...",
    "crosssection": { "station": [], "ground_z": [], "water_z": [] },
    "summary": "<Claude plain-English text>",
    "images": ["<nearest Cyvl image url>"]
  }
  ```
  Target: returns in **< 10 s**.
