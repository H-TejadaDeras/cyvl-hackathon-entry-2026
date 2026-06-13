# Product Requirements Document
## Urban Drainage Failure and Pothole Risk Mapper

**Version:** 0.1 — Hackathon Prototype  
**Date:** 2026-06-13  
**Status:** Draft

---

## 1. Overview

A terrain-informed infrastructure risk service that ranks streets and drainage gaps by flood and pavement-failure risk before capital and maintenance decisions are made. It fuses Cyvl LiDAR, pavement condition scores, catch basin locations, and public complaint records into a ranked priority list and an Autodesk-ready engineering model — compressing weeks of consultant scoping into hours.

---

## 2. Problem

Cities allocate paving and drainage budgets reactively: the loudest complaint cluster or the most politically visible street wins. Streets are resurfaced over unresolved drainage failures and fail again within 18 months. Maintenance crews respond to flooding only after basements flood. Engineers spend 4–6 weeks assembling GIS data before they can identify which sites to study.

Climate change is compressing rainfall into shorter, more intense bursts, accelerating the mismatch between existing drainage capacity and actual storm loads.

---

## 3. Goals

| # | Goal | Metric |
|---|---|---|
| G1 | Identify drainage gaps and high-risk pavement before a capital decision is made | ≥ 1 maintenance or capital recommendation changed in the pilot |
| G2 | Compress consultant scoping effort | Site-screening phase reduced from 4–6 weeks to < 1 day |
| G3 | Produce MS4-compliant documentation as a byproduct | Civil 3D drainage network and gap analysis accepted by city engineer |
| G4 | Validate model against ground truth | High-risk locations correspond to observed ponding, 311 complaints, or field-confirmed distress |
| G5 | Support federal grant applications | Quantified gap analysis usable in FEMA BRIC or EPA CWSRF submission |

---

## 4. Users

### 4.1 Primary Users — Municipal DPW / Engineering

| Persona | Job to be done | Pain today |
|---|---|---|
| DPW Director / City Engineer | Defend $2–10M capital allocation | No data-backed ranking; reacts to complaints and political pressure |
| Stormwater Program Manager | Document MS4/NPDES permit compliance | Manual assembly of inspection records and gap lists |
| Pavement or Asset Manager | Stop patching the same pothole each winter | No connection between drainage data and pavement failure history |
| Finance / Grant Writer | Justify and fund the capital plan | Weak project documentation; loses to competitors with pre-engineered submissions |

### 4.2 Secondary Users

| Buyer | Use case |
|---|---|
| Civil engineering consultants | Receive Civil 3D / InfoDrainage starting model, saving 2–4 weeks of setup per engagement |
| Emergency services (fire, OEM) | Pre-storm routing — which streets and underpasses flood first under a given rainfall scenario |
| Flood and property insurers | Street-level risk scores for underwriting and portfolio loss modeling beyond FEMA zone boundaries |
| State DOT / regional planning | Citywide risk rankings across multiple municipalities without per-city custom analysis |

---

## 5. Scope

### 5.1 In Scope — Prototype (Hackathon)

- Process one Cyvl LAZ tile (one street segment in Somerville, MA)
- Extract road-surface DTM from unclassified LiDAR using PDAL SMRF or CSF
- Compute D8 flow direction, flow accumulation, and sink detection
- Cross-reference flow accumulation against mapped catch basin locations
- Score 30-ft pavement sections on drainage exposure, pavement condition, and complaint density
- Produce ranked drainage gap list and pothole risk map
- Run at least one InfoDrainage baseline and one intervention scenario
- Generate a plain-English summary of top-ranked locations using Claude
- Export outputs with stable `inspect_id` and `client_seg` identifiers for cross-tile merging

### 5.2 Out of Scope — Prototype

- Real-time or forecast-driven flood alerts
- Full pipe network hydraulic model (requires as-built invert and diameter records)
- Citywide LAZ processing (tile-based pipeline must support it; batch execution is not required for the prototype)
- Exact pothole location or date prediction
- Illicit discharge detection or pollutant tracking
- Field inspection workflow or mobile app
- Live 311 ingestion (batch export only)

---

## 6. Functional Requirements

### 6.1 LiDAR Processing

| ID | Requirement |
|---|---|
| F1.1 | Ingest a LAZ file and read CRS and bounding box from the header without manual coordinate input |
| F1.2 | Clip point cloud to buffered road corridors derived from the centerline shapefile |
| F1.3 | Classify ground points using PDAL SMRF or CSF (do not use `classification == 2` filter; all points are unclassified) |
| F1.4 | Interpolate a road-surface DTM at a resolution selected after point-density checks |
| F1.5 | Flag DTM cells where stored precision does not equal absolute vertical accuracy |
| F1.6 | Produce tile-level outputs with stable identifiers so outputs can merge across tiles without reprocessing |

### 6.2 Hydrologic Analysis

| ID | Requirement |
|---|---|
| F2.1 | Compute D8 or D-infinity flow direction on the DTM |
| F2.2 | Compute flow accumulation raster from flow direction |
| F2.3 | Detect sinks and depressions with no downslope outfall path |
| F2.4 | Overlay catch basin coordinates (from `aboveGroundAssets.geojson`, filtered to `asset_type == "CATCH_BASIN"`) onto the flow accumulation raster |
| F2.5 | Flag cells with high flow accumulation and no detected catch basin within a configurable radius as drainage gaps |
| F2.6 | Delineate catchment polygons and compute area, mean slope, longest flow path, and estimated time of concentration per catchment |
| F2.7 | Estimate peak runoff at each node using Rational Method with NOAA Atlas 14 design storm depths and MassGIS impervious fractions |

### 6.3 Pavement Risk Scoring

| ID | Requirement |
|---|---|
| F3.1 | Join 30-ft pavement segments to DTM-derived metrics (depression depth, cross-slope, flow accumulation exposure) via spatial join in EPSG:32619 |
| F3.2 | Incorporate Cyvl PCI score, crack and patch indicators from imagery, and LiDAR deformation metrics per segment |
| F3.3 | Join 311 pothole and flooding complaint history to each segment (count within 100 m, years of repeat complaints) |
| F3.4 | Compute a composite pothole risk score per segment on a 3-, 6-, and 12-month horizon |
| F3.5 | Assign a recommended action to each segment: inspect, crack-seal, clear drainage, monitor, or reconstruct |
| F3.6 | Export ranked segment list as GeoJSON and CSV with all input features and score components |

### 6.4 Drainage Gap Scoring

| ID | Requirement |
|---|---|
| F4.1 | Assign each drainage gap a composite risk score combining flow accumulation, impervious fraction, 311 complaint density, FEMA flood zone overlap, and distance to nearest alternative basin |
| F4.2 | Annotate each gap with: contributing area, estimated peak runoff under 10-year storm, complaint history, FEMA zone flag |
| F4.3 | Export ranked gap list as GeoJSON and CSV |

### 6.5 Autodesk Integration

| ID | Requirement |
|---|---|
| F5.1 | Export DTM as LandXML surface importable into Civil 3D |
| F5.2 | Export catchment polygons and catch basin node coordinates for Civil 3D pipe network |
| F5.3 | Label all assumed hydraulic inputs (grate capacity, pipe diameter, invert elevation) separately from Cyvl-measured data |
| F5.4 | Run at least one InfoDrainage baseline simulation and one intervention scenario (e.g., larger grate, added basin, upsized pipe) |
| F5.5 | Deliver simulation tables for peak flow, surcharge, flood volume, and drainage time |

### 6.6 Claude Integration

| ID | Requirement |
|---|---|
| F6.1 | For each top-ranked drainage gap, retrieve the nearest plain or panoramic image URL from local imagery files via spatial join and pass to Claude for visual description |
| F6.2 | Claude output must identify presence or absence of: basin grate, ponding staining, curb orientation, visible pavement distress — without inventing defects not visible in the image |
| F6.3 | Generate a plain-English summary for each top-ranked segment and gap, including contributing catchment stats, risk rank, and recommended action |
| F6.4 | Cross-reference incoming 311 complaints against the drainage gap database and return: flagged status, risk rank, modeled explanation |

### 6.7 Outputs and Deliverables

| ID | Requirement |
|---|---|
| F7.1 | Ranked drainage gap map (GeoJSON) with risk score, contributing area, peak runoff estimate, complaint history, FEMA flag |
| F7.2 | Ranked pavement segment risk map (GeoJSON + CSV) with 3/6/12-month risk, score components, and recommended action |
| F7.3 | Civil 3D drawing with LandXML surface, catchment polygons, and annotated gap locations |
| F7.4 | InfoDrainage model with baseline and at least one intervention scenario |
| F7.5 | One-page plain-English summary of top 5 gaps and top 5 pavement segments, suitable for a DPW director |

---

## 7. Non-Functional Requirements

| ID | Requirement |
|---|---|
| NF1 | Processing the prototype LAZ tile (53.5M points, ~349×220 m) must complete in under 30 minutes on a laptop-class machine |
| NF2 | At least 90% of 30-ft pavement sections intersecting the LAZ tile must receive surface metrics |
| NF3 | All vector layers must be reprojected to EPSG:32619 before any spatial join, buffer, or raster operation |
| NF4 | Adding a second LAZ tile must require only a new input path, not changes to analysis logic |
| NF5 | All assumed hydraulic values must be clearly labeled in every output (GeoJSON properties, Civil 3D annotations, InfoDrainage node metadata) |
| NF6 | Outputs must retain `inspect_id` and `client_seg` identifiers so results can be merged across tiles |

---

## 8. Data Inputs

| Dataset | Source | Status |
|---|---|---|
| LiDAR point cloud (.laz) | Cyvl | In hand |
| 30-ft pavement condition scores | Cyvl | In hand |
| Segment-level pavement scores | Cyvl | In hand |
| Street centerline | Cyvl | In hand |
| Above-ground assets (catch basins) | Cyvl | In hand |
| Plain imagery index | Cyvl | In hand |
| Panoramic imagery index | Cyvl | In hand |
| Road markings (sam.geojson) | Cyvl | In hand |
| 311 flooding and pothole complaints | Somerville open data / SeeClickFix | Requires download |
| Impervious surface layer | MassGIS | Public, free |
| Design storm depths | NOAA Atlas 14 | Public, free |
| FEMA National Flood Hazard Layer | FEMA | Public, free |
| Pavement repair and work order history | City public works records | Requires city cooperation |
| Storm sewer as-builts (pipe inverts, diameters) | City GIS or consultant | Requires city cooperation; prototype uses declared assumptions |

---

## 9. Assumptions and Constraints

- The prototype LAZ is unclassified (all classification and return-number values are zero). Ground extraction must use a statistical algorithm, not a classification filter.
- The prototype LAZ does not overlap a mapped catch basin. Drainage-to-basin validation must be deferred to a second tile.
- As-built sewer records are unlikely to be available for the prototype. All hydraulic inputs without a Cyvl source must be declared as assumptions in every output.
- Stored Z precision in the LAZ (1 cm) is not the same as absolute vertical accuracy. DTM-derived results must not claim sub-centimeter accuracy.
- The Cyvl dataset is a snapshot, not a live feed. No real-time data integration is in scope.

---

## 10. Success Criteria (Prototype)

| Criterion | Pass condition |
|---|---|
| LAZ processing | Tile ingested and DTM produced without manually editing coordinates or bounds |
| Coverage | ≥ 90% of intersecting 30-ft pavement sections receive surface metrics |
| Imagery linkage | Each top-ranked location links to at least one nearby Cyvl image for visual review |
| Tile portability | Adding a second LAZ requires only a new input path |
| Autodesk output | InfoDrainage completes ≥ 1 baseline and ≥ 1 intervention simulation |
| Assumption labeling | Every assumed hydraulic input is labeled separately from measured Cyvl data in all outputs |
| Decision change | At least one drainage or paving recommendation is demonstrably different from what the city would have chosen without the tool |

---

## 11. Milestones

| Phase | Deliverable | Target |
|---|---|---|
| 0 — Data prep | All local files loaded, reprojected to EPSG:32619, spatial extents verified | Day 1, morning |
| 1 — LiDAR pipeline | DTM produced, flow direction and accumulation computed, sinks detected | Day 1, midday |
| 2 — Risk scoring | Drainage gap list and pavement segment risk scores exported as GeoJSON + CSV | Day 1, afternoon |
| 3 — Autodesk model | LandXML exported to Civil 3D, InfoDrainage baseline and one alternative scenario complete | Day 1, late afternoon |
| 4 — Claude layer | Imagery analysis and plain-English summaries generated for top-ranked locations | Day 1, evening |
| 5 — Demo package | One-page summary, ranked maps, and Civil 3D / InfoDrainage outputs packaged for presentation | Day 1, end |
