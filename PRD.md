# Product Requirements Document
## CurbRisk — Street-Level Drainage Risk Scoring for Underwriting

**Version:** 0.2 — Hackathon Prototype  
**Date:** 2026-06-13  
**Status:** Draft

> **0.2 change note:** Aligned to the actual implementation plan (`implementation.md` + the `curbrisk/` pipeline). The product is now **CurbRisk**: an address-queryable drainage-risk API and browser-based Autodesk cross-section, sold first to property/flood insurers and catastrophe modelers. The Autodesk deliverable is **APS (Autodesk Platform Services) via `ezdxf`, rendered in the APS Viewer** — replacing the prior Civil 3D / InfoDrainage path, which is retained only as a future municipal-market option.

---

## 1. Overview

CurbRisk ingests Cyvl's LiDAR point cloud to automatically identify topographic low points on every street segment, computes each low point's catchment area and modeled ponding volume, and cross-references those against Cyvl's CV-detected pavement condition scores and existing catch basin locations to produce a per-block **drainage risk score**.

Boston and Somerville open data — 311 flooding complaints and storm sewer maps — are layered on top of the Cyvl geometry to validate and weight each score against real historical flood events at those exact coordinates.

The scored geometry is fed into **Autodesk Platform Services via `ezdxf`** to generate a 3D cross-section of each flagged low point — road profile, modeled water depth at a 2-inch rain event, and pavement condition — rendered in the **APS Viewer** as a measurable, browser-based deliverable an underwriter or actuary can open with no CAD software.

Each street segment's risk score, LiDAR geometry, 311 complaint history, and Autodesk cross-section are packaged into a **structured API response that an insurer queries by address** to receive a CurbRisk score at policy-underwriting time. The same terrain-and-pavement engine also serves municipal DPW/engineering teams as a secondary market.

---

## 2. Problem

**For insurers:** Flood and property risk is priced from FEMA zone boundaries that stop at the parcel and ignore street-level terrain. Two homes on the same block — one at a topographic low point with a failing catch basin, one on a crest — carry the same FEMA-derived premium. Underwriters have no measured, coordinate-level signal for which specific addresses pond, and catastrophe modelers (Moody's RMS, Verisk) lack sub-zone drainage granularity.

**For cities:** Paving and drainage budgets are allocated reactively — the loudest complaint cluster or the most politically visible street wins. Streets are resurfaced over unresolved drainage failures and fail again within 18 months. Engineers spend 4–6 weeks assembling GIS data before they can identify which sites to study.

Climate change is compressing rainfall into shorter, more intense bursts, accelerating the mismatch between existing drainage capacity and actual storm loads — and widening the gap between FEMA-zone pricing and real loss exposure.

---

## 3. Goals

| # | Goal | Metric |
|---|---|---|
| G1 | Return a defensible street-level drainage risk score for any address in the demo footprint | API returns CurbRisk score + cross-section for any in-tile address |
| G2 | Deliver an underwriter-readable engineering artifact with no CAD software | 3D cross-section opens in the APS Viewer in a browser |
| G3 | Validate the model against ground truth | High-risk locations correspond to observed ponding, 311 complaints, or field-confirmed distress |
| G4 | Demonstrate the full pipeline end-to-end live | Judge enters an address → drainage risk report returned in < 10 seconds |
| G5 | Preserve the municipal/engineering market as an upsell | Scored geometry exportable to a CAD/hydraulic model without rework |

---

## 4. Users

### 4.1 Primary Users — Insurance & Risk

| Persona | Job to be done | Pain today |
|---|---|---|
| Property/flood underwriter | Price a policy at a specific address | FEMA zone is too coarse; no street-level terrain signal |
| Actuary | Model portfolio loss exposure below the FEMA zone | No measured drainage granularity per address |
| Catastrophe risk modeler (Moody's RMS, Verisk) | Enrich cat models with sub-zone drainage data | No coordinate-level ponding/drainage dataset |

### 4.2 Secondary Users — Municipal DPW / Engineering

| Persona | Job to be done | Pain today |
|---|---|---|
| DPW Director / City Engineer | Defend $2–10M capital allocation | No data-backed ranking; reacts to complaints and political pressure |
| Stormwater Program Manager | Document MS4/NPDES permit compliance | Manual assembly of inspection records and gap lists |
| Pavement / Asset Manager | Stop patching the same pothole each winter | No connection between drainage data and pavement failure history |
| Civil engineering consultants | Receive a starting engineering model | 2–4 weeks of GIS setup per engagement |

---

## 5. Business Model

CurbRisk packages each segment's score, geometry, complaint history, and cross-section into a structured API response, monetized three ways:

| Model | Buyer | Unit |
|---|---|---|
| Per-query | Insurer underwriting at point of sale | Per address lookup |
| Per-city license | Insurer or DPW covering a whole municipality | Annual, per city |
| Bulk dataset | Catastrophe risk modelers (Moody's RMS, Verisk) | One-time / refresh, per dataset |

---

## 6. Scope

### 6.1 In Scope — Prototype (Hackathon)

- Process one Cyvl LAZ tile (~349 × 220 m, one Somerville neighborhood) — defines the MVP footprint
- Extract a road-surface DEM from unclassified LiDAR (statistical ground filter, not a classification filter)
- Detect topographic low points / ponding points per street segment
- Compute catchment area and modeled ponding volume at a 2-inch rain event per low point
- Cross-reference low points against mapped catch basin locations (50 m influence radius)
- Join Cyvl PCI scores and 311 flood-complaint density (100 m radius) to each segment
- Compute a weighted composite CurbRisk score per segment (topo 40 / pavement 30 / basin 20 / complaint 10)
- Generate an Autodesk 3D cross-section per flagged low point via `ezdxf`, served in the APS Viewer
- Expose an address-query API backed by a SQLite score cache, returning score + cross-section in < 10 s
- Generate a plain-English summary of top-ranked locations using Claude
- Persist outputs with stable `inspect_id` and `client_seg` identifiers for cross-tile merging

### 6.2 Out of Scope — Prototype

- Real-time or forecast-driven flood alerts
- Full pipe-network hydraulic model (requires as-built invert and diameter records)
- Citywide LAZ processing (pipeline must support tiling; batch execution not required)
- Exact pothole location or date prediction
- Illicit discharge detection or pollutant tracking
- Field inspection workflow or mobile app
- Live 311 ingestion (batch export only)

---

## 7. Functional Requirements

### 7.1 Ingest (`curbrisk.ingest`)

| ID | Requirement |
|---|---|
| F1.1 | Read CRS and bounding box from the LAZ header; derive the demo tile footprint with no manual coordinate input |
| F1.2 | Clip pavement segments and catch basins to the tile (+20 m buffer) so all stages share one footprint |
| F1.3 | Reproject all vectors to EPSG:32619 (UTM 19N, meters) for analysis; persist in WGS84 for portability |
| F1.4 | Normalize Cyvl columns to a stable schema (`inspect_id`, `client_seg`, `street`, `pci`, …) |
| F1.5 | Filter above-ground assets to `asset_type == "CATCH_BASIN"` |

### 7.2 LiDAR & Terrain

| ID | Requirement |
|---|---|
| F2.1 | Classify ground points statistically (PDAL SMRF/CSF); do not use `classification == 2` (all points unclassified) |
| F2.2 | Interpolate a 0.5 m road-surface DEM, resolution confirmed after point-density checks |
| F2.3 | Flag DEM cells where stored Z precision (1 cm) is not absolute vertical accuracy |
| F2.4 | Sample elevation along each segment at 5 m spacing |

### 7.3 Hydrology & Low-Point Detection

| ID | Requirement |
|---|---|
| F3.1 | Detect topographic low points / sinks with no downslope outfall path |
| F3.2 | Delineate the catchment for each low point and compute contributing area |
| F3.3 | Model ponding volume and water depth at a 2-inch rain event per low point |
| F3.4 | Flag a low point as a drainage gap when no catch basin lies within 50 m |

### 7.4 Risk Scoring (`curbrisk.scoring`)

| ID | Requirement |
|---|---|
| F4.1 | Join each 30-ft segment to its DEM/low-point metrics via spatial join in EPSG:32619 |
| F4.2 | Incorporate Cyvl PCI score and CV-detected distress per segment |
| F4.3 | Join 311 flood/pothole complaint density within 100 m to each segment |
| F4.4 | Compute a 0–100 composite CurbRisk score: topo 40 + pavement 30 + basin 20 + complaint 10 |
| F4.5 | Assign a recommended action (inspect, crack-seal, clear drainage, monitor, reconstruct) |
| F4.6 | Export scored segments as GeoJSON and write to the SQLite score cache |

### 7.5 Autodesk APS Integration (`curbrisk.output`)

| ID | Requirement |
|---|---|
| F5.1 | Generate a DXF cross-section per flagged low point via `ezdxf`: road profile, modeled water depth at 2-in rain, pavement condition |
| F5.2 | Translate/serve the geometry through Autodesk Platform Services so it renders in the APS Viewer |
| F5.3 | Deliver the cross-section as a measurable, browser-based artifact requiring no CAD software |
| F5.4 | Label all assumed hydraulic inputs separately from Cyvl-measured data in the geometry |
| F5.5 | (Future / municipal) Export the same surface to LandXML/Civil 3D for a full hydraulic model |

### 7.6 Address-Query API (`curbrisk.api`)

| ID | Requirement |
|---|---|
| F6.1 | Accept an address (or lat/lon), geocode it, and resolve the nearest scored segment |
| F6.2 | Return a structured response: CurbRisk score + components, LiDAR-derived geometry, 311 history, APS cross-section link |
| F6.3 | Serve from the SQLite score cache so a lookup returns in < 10 s end-to-end |
| F6.4 | Return a clear out-of-coverage response for addresses outside the demo tile |

### 7.7 Claude Integration

| ID | Requirement |
|---|---|
| F7.1 | For each top-ranked low point, pass the nearest Cyvl image to Claude for visual description |
| F7.2 | Claude must report presence/absence of basin grate, ponding staining, curb orientation, and visible distress — without inventing defects not in the image |
| F7.3 | Generate a plain-English summary per top-ranked segment: catchment stats, risk rank, recommended action |

### 7.8 Outputs & Deliverables

| ID | Requirement |
|---|---|
| F8.1 | Scored segment layer (GeoJSON) with CurbRisk score, components, catchment area, ponding volume, complaint history |
| F8.2 | Low-point / drainage-gap layer (GeoJSON) with contributing area and 2-in ponding model |
| F8.3 | Per-low-point APS cross-section viewable in a browser |
| F8.4 | Address-query API returning the full CurbRisk record |
| F8.5 | One-page plain-English summary of top-ranked locations |

---

## 8. Non-Functional Requirements

| ID | Requirement |
|---|---|
| NF1 | An address lookup must return score + cross-section in < 10 s (served from the SQLite cache) |
| NF2 | Processing the prototype LAZ tile (53.5M points, ~349×220 m) must complete in < 30 min on a laptop-class machine |
| NF3 | ≥ 90% of 30-ft pavement sections intersecting the LAZ tile must receive surface metrics |
| NF4 | All vector layers must be reprojected to EPSG:32619 before any spatial join, buffer, or raster op |
| NF5 | Adding a second LAZ tile must require only a new input path, not changes to analysis logic |
| NF6 | All assumed hydraulic values must be clearly labeled in every output (GeoJSON properties, APS annotations, API response) |
| NF7 | Outputs must retain `inspect_id` and `client_seg` identifiers so results merge across tiles |

---

## 9. Architecture & Tech Stack

| Layer | Tooling |
|---|---|
| Pipeline package | `curbrisk/` — `config`, `ingest`, `scoring`, `output`, `api` |
| Geospatial | Python, GeoPandas, Shapely; analysis CRS EPSG:32619 (UTM 19N) |
| LiDAR / DEM | LAZ ingest, PDAL SMRF/CSF ground filter, 0.5 m DEM raster |
| Autodesk | `ezdxf` → DXF cross-sections, served via Autodesk Platform Services / APS Viewer |
| Serving | SQLite score cache (`scores.db`) behind the address-query API |
| Narrative | Claude (imagery description + plain-English summaries) |

**Key parameters** (`curbrisk/config.py`): DEM 0.5 m · along-segment sampling 5 m · design storm 2.0 in · basin influence 50 m · complaint influence 100 m · score weights topo 40 / pavement 30 / basin 20 / complaint 10. Cyvl project `f15b854a-d203-49c7-bc25-1350dd4a1cd6`.

---

## 10. Data Inputs

| Dataset | Source | Status |
|---|---|---|
| LiDAR point cloud (.laz) | Cyvl | In hand |
| 30-ft pavement condition scores | Cyvl | In hand |
| Street centerline | Cyvl | In hand |
| Above-ground assets (catch basins) | Cyvl | In hand |
| Plain / panoramic imagery index | Cyvl | In hand |
| Road markings (sam.geojson) | Cyvl | In hand |
| 311 flooding & pothole complaints | Somerville / Boston open data · SeeClickFix | Requires download |
| Storm sewer maps | Somerville / Boston open data | Requires download |
| Impervious surface layer | MassGIS | Public, free |
| Design storm depths | NOAA Atlas 14 | Public, free |
| FEMA National Flood Hazard Layer | FEMA | Public, free |
| Storm sewer as-builts (inverts, diameters) | City GIS / consultant | Requires city cooperation; prototype uses declared assumptions |

---

## 11. Assumptions and Constraints

- The prototype LAZ is unclassified (all classification and return-number values are zero). Ground extraction must use a statistical algorithm, not a classification filter.
- The prototype LAZ may not overlap a mapped catch basin. Drainage-to-basin validation may need to defer to a second tile.
- As-built sewer records are unlikely for the prototype. All hydraulic inputs without a Cyvl source must be declared as assumptions in every output.
- Stored Z precision in the LAZ (1 cm) is not absolute vertical accuracy. DEM-derived results must not claim sub-centimeter accuracy.
- The Cyvl dataset is a snapshot, not a live feed. No real-time data integration is in scope.
- Ponding volume at a 2-inch event is a simplified surface model, not a full pipe-network hydraulic simulation.

---

## 12. Success Criteria (Prototype)

| Criterion | Pass condition |
|---|---|
| LAZ processing | Tile ingested and DEM produced without manually editing coordinates or bounds |
| Coverage | ≥ 90% of intersecting 30-ft pavement sections receive surface metrics |
| Low-point detection | Catchment area and 2-in ponding volume computed per detected low point |
| Scoring | Composite CurbRisk score (0–100) produced per segment with labeled components |
| APS deliverable | At least one low-point 3D cross-section opens in the APS Viewer in a browser |
| Address API | An address lookup returns score + cross-section in < 10 s |
| Imagery linkage | Each top-ranked location links to at least one nearby Cyvl image for visual review |
| Tile portability | Adding a second LAZ requires only a new input path |
| Assumption labeling | Every assumed hydraulic input is labeled separately from measured Cyvl data in all outputs |

---

## 13. Milestones

| Phase | Deliverable | Target |
|---|---|---|
| 0 — Data prep | Local files loaded, clipped to tile, reprojected to EPSG:32619, extents verified | Day 1, morning |
| 1 — LiDAR pipeline | DEM produced, low points detected, catchments and 2-in ponding modeled | Day 1, midday |
| 2 — Risk scoring | Composite CurbRisk scores exported to GeoJSON + SQLite score cache | Day 1, afternoon |
| 3 — Autodesk APS | `ezdxf` cross-sections generated and rendering in the APS Viewer | Day 1, late afternoon |
| 4 — API + Claude | Address-query API live (< 10 s); imagery analysis and summaries generated | Day 1, evening |
| 5 — Demo package | Live address → drainage risk report; ranked maps and cross-sections packaged | Day 1, end |
