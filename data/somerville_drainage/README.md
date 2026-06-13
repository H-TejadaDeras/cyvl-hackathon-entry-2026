# Somerville Drainage / Storm-Sewer GIS

Storm-drainage network features for the CurbRisk demo footprint, pulled from the
City of Somerville's public ArcGIS service. Fills the "storm sewer maps" (medium
priority) and rescues the catch-basin component, which had **0 features inside
the raw Cyvl LAZ tile** but 66 within a ~500 m buffer of it.

## Source
- **Service:** `UtilitiesAndAssets2` MapServer
  https://maps.somervillema.gov/arcgis/rest/services/UtilitiesAndAssets2/MapServer
- **Owner:** City of Somerville GIS (public, no key required)
- **Fetched:** 2026-06-13
- **Method:** ArcGIS REST `query` endpoint, no scraping.

## Spatial query
- **CRS in/out:** EPSG:4326 (WGS84 lon/lat) — `inSR=4326&outSR=4326`
- **Clip:** envelope intersect, `spatialRel=esriSpatialRelIntersects`
- **Bounding box (≈500 m buffer around the LAZ tile):**
  `minx=-71.110094, miny=42.380102, maxx=-71.093723, maxy=42.391156`
- The buffer is intentional: the network that drains our streets extends past
  the tile edge (basins sit at the downstream end of a block). Re-clip to the
  exact tile in `curbrisk.ingest` if you want strictly in-tile features.

## Files (all GeoJSON, WGS84)

| File | Layer ID | Geometry | Features | Notes |
|---|---|---|---|---|
| `catch_basins.geojson` | 8 | Point | 66 | `WaterType`, `RimElevati`, `Invert` (many = 9999 / no data) |
| `storm_inlets.geojson` | 13 | Point | 577 | densest layer; inlet structures |
| `catch_basin_laterals.geojson` | 14 | LineString | 61 | `Diameter`, `Material` |
| `sw_gravity_mains.geojson` | 19 | LineString | 145 | **as-built hydraulics:** `UPELEV`/`DOWNELEV`, `SLOPE`, `Diameter`, `Streetname`, `CatchArea` |

Layers **5 Outfalls** and **15 Storm Discharge Points** returned 0 features in
this area (they sit at the Mystic River, outside our inland footprint) and were
not saved.

## Reproduce
```bash
BBOX="-71.110094,42.380102,-71.093723,42.391156"
BASE="https://maps.somervillema.gov/arcgis/rest/services/UtilitiesAndAssets2/MapServer"
# Point layers (8, 13) support f=geojson directly:
curl "$BASE/8/query?where=1=1&geometry=$BBOX&geometryType=esriGeometryEnvelope&inSR=4326&outSR=4326&spatialRel=esriSpatialRelIntersects&outFields=*&f=geojson"
# Line layers (14, 19) error on f=geojson — fetch f=json and convert paths -> LineString.
```

## Caveats
- Elevation fields are inconsistently populated (`9999` and `-1325462400000`
  epoch placeholders appear). Validate before trusting inverts/rim elevations.
- Positional accuracy varies; several basins are flagged "ASSUMED FROM PLAN".
- Snapshot as of the fetch date; the city service updates over time.
