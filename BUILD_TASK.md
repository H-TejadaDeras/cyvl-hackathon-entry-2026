# CurbRisk — Autonomous Build Task

Re-read this file at the start of every iteration. Fix the FIRST failing step,
re-run, print a one-line PASS/FAIL with the artifact path, verify before moving on.

---

## PART 1 — Core pipeline  ✅ DONE (baseline, do not regress)

The end-to-end pipeline is built and validated against REAL Somerville data:
- `curbrisk/run_pipeline.py` stages: cyvl_ingest → opendata → lidar_dem → topo →
  risk → narrative → crosssection → aps_upload.
- Real data only (no sample fallbacks): `data/somerville_drainage/*` (66 catch
  basins, 577 storm inlets), `data/somerville_311/drainage_pavement_311.csv`
  geolocated via 2020 TIGER blocks (MA state file `tl_2020_25_tabblock20.zip`;
  the county-level URL 404s), `ground_points.npy` (575 MB, reuse — never delete).
- `lidar_dem.py` streams the 53M-pt LAZ in chunks (seeded subsample) to stay in
  RAM. `aps_upload.py` coalesces an empty `APS_BUCKET`, surfaces APS error bodies.
- API: `/risk`, `/map`, `/segments.geojson`, `/viewer/{id}` (Autodesk GuiViewer3D
  on the SVF2 model), `/aps/token` (2-legged `viewables:read`).
- DONE criteria still hold: `python -m curbrisk.run_pipeline` completes on real
  data; `curbrisk_scores.geojson` + `scores.db` carry 0-100 scores + 4 components;
  the API answers in-tile <10 s and returns a clean out-of-coverage 404.

---

## PART 2 — NEW WORK (this iteration)

Goal: make the Autodesk APS Viewer the centrepiece, put per-crack interaction on
the LiDAR model, add a live rain/snow simulator, and replace the report body with
five actuarial insights. **Finish with `uvicorn ... --port 8000` running so the
demo opens on localhost and the APS Viewer works.**

### Data-reality note (important, keep labelled in the UI)
There is **no real crack geometry** in the deliverables — pavement data is
LineString segments with one PCI `score` each, no per-distress vectors. So cracks
are **synthetic**, generated deterministically (seeded) from PCI (lower PCI ⇒ more
/ wider cracks) and placed along the LiDAR road profile near the low point. Depth
is a placeholder (random, seeded) and **editable**, to be replaced when real
distress data arrives. Everything synthetic is explicitly labelled in the UI.

### Step 1 — `curbrisk/scoring/insights.py` (the 5 actuarial insights)
Compute from an existing scored segment row (+ optional storm override). Replace
the current report body with these as "Actionable Insights":
1. **Ponding Volume (cf)** = `catchment_sqft × ponding_depth_ft × 0.9` (runoff coeff).
2. **Storm Return Period (yr)** — map modeled ponding depth → rainfall intensity →
   return period via a bundled **NOAA Atlas 14** IDF table for Somerville, MA
   (point ~42.39,-71.10; 24-hr depths for 1/2/5/10/25/50/100-yr). Label the source.
3. **Foundation Flow Vector (% grade + direction)** =
   `(elev_lowpoint − elev_foundation_entry) / horizontal_dist × 100`. No building
   footprints yet → foundation entry elevation is ESTIMATED from LiDAR grade at a
   standard setback; label it estimated. Sign: + = water flows toward structure.
4. **Crack Infiltration Index (Low/Med/High)** — from synthetic crack width+depth
   weighted by proximity to the low point.
5. **Drainage Relief Score (0-100)** =
   `100 − [(drain_dist_m × 0.8) + (311_count × 0.5) + (catchment_sqft/100 × 0.3)]`,
   clamped to [0,100]. Lower = water sits longer = higher exposure.
PASS: `python -m curbrisk.scoring.insights` prints all five for a known segment.

### Step 2 — `curbrisk/output/cracks.py` (synthetic cracks)
Deterministic per low-point segment: list of cracks with
`{id, t (0-1 along profile), offset_m, length_m, width_mm, depth_mm, severity,
dist_to_low_m}`. Write `data/processed/cracks_index.json` keyed by segment_id.
PASS: non-empty cracks for each cross-section segment; counts scale inversely with PCI.

### Step 3 — cracks in the 3-D model (`crosssection.py`)
Add each crack to the DXF as its **own named layer/object** `CRACK_<id>` (a short
3-D polyline / thin trench on the road surface, colour by severity) so it is a
selectable, toggleable object in the APS Viewer. Keep ROAD + WATER. Re-run
`crosssection` + `aps_upload` to retranslate. PASS: viewer object tree lists cracks.

### Step 4 — API
- `/risk` JSON gains `insights` (the 5) and `cracks` (list + per-crack dims).
- `GET /simulate?segment_id=&rain_in=&snow_in=` → recomputed ponding depth, topo,
  curb_risk, and the 5 insights for that storm (snow via 10:1 SWE on melt; label).
- `PATCH/GET /cracks/{segment_id}` depth override is in-memory/JSON (editable depth).
PASS: `/simulate` raises the score as rain increases; `/risk` carries insights+cracks.

### Step 5 — Interactive studio = upgrade `/viewer/{segment_id}`
One page with the APS GuiViewer3D PLUS:
- **Crack panel**: checkbox per crack → `viewer.hide/show(dbId)`; selecting a crack
  (panel or 3-D click via SELECTION_CHANGED) shows its dimensions with an
  **editable depth** field.
- **Rain/Snow simulator**: two sliders → live `/simulate` → update CurbRisk score +
  the 5 insights, AND drive rain **rendered in the viewer** (THREE particle overlay
  + rising WATER plane; CSS/canvas fallback if the overlay API is unavailable).
- Show the 5 insights live. Map crack object names → dbId after GEOMETRY_LOADED.

### Step 6 — Home `/` report
Primary body = the 5 insights. Embed (iframe) or prominently link the studio.
**Remove the 360° panorama** and de-emphasise raw street imagery. Keep score gauge.

### DONE criteria (all true)
- `python -m curbrisk.run_pipeline` still completes on real data; cracks_index.json
  + cross-section models regenerate.
- `/risk` returns the 5 insights + cracks; `/simulate` changes the score with rain.
- The studio page loads the APS Viewer with toggleable, clickable cracks (dimensions
  on click, editable depth) and a working rain/snow simulator that rerenders rain
  and updates the score. Server is left running on :8000 and opens on localhost.

When ALL are verified, print a per-feature PASS/FAIL summary, the demo URL, a
known-working address/segment, and output:  <promise>CURBRISK STUDIO DONE</promise>
