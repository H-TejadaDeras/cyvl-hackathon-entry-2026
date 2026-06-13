# Somerville 311 — Drainage & Pavement Service Requests

311 constituent service requests filtered to drainage- and pavement-relevant
types, for the CurbRisk **complaint component** (10% of the score) and pavement
cross-validation.

## Source
- **Portal:** City of Somerville Open Data (Socrata)
- **Dataset:** "311 Service, Information, and Feedback Requests" — id **`4pyi-uqq6`**
  https://data.somervillema.gov/d/4pyi-uqq6
- **API:** SODA — https://data.somervillema.gov/resource/4pyi-uqq6.csv
- **Coverage:** July 2015 → present, updated monthly
- **Fetched:** 2026-06-13 (no key required)

## Filter applied
`drainage_pavement_311.csv` — **26,994 rows** matching any of:
`type ILIKE` Pothole, Catch Basin, Flood, Sewer, Drain, Road Defect.
Water-billing / water-service inquiries were intentionally excluded.

Top contributing types: Pothole (21,674), Catch basin complaint (1,638),
Street/road defect (1,527), Sewer issue (1,337), Sewer Back-up (191),
Flooding Report (145), Sewers and Drains (98), Catch Basin Cleaning/Repair (62).

```bash
WHERE="upper(type) like '%POTHOLE%' OR upper(type) like '%CATCH BASIN%' \
OR upper(type) like '%FLOOD%' OR upper(type) like '%SEWER%' \
OR upper(type) like '%DRAIN%' OR upper(type) like '%ROAD DEFECT%'"
curl "https://data.somervillema.gov/resource/4pyi-uqq6.csv?\$where=$WHERE&\$limit=60000"
```

## ⚠️ Geolocation — read before joining to segments
This dataset has **no latitude/longitude**. Location is carried by two fields:
- `ward` — far too coarse for a 349 × 220 m tile (don't use for placement).
- `block_code` — a **15-digit U.S. Census block GEOID**, e.g.
  `250173501051006` = State 25 (MA) · County 017 (Middlesex) · Tract 3501.05 ·
  Block 1006.

**To place a complaint on the map, join `block_code` to a 2020 TIGER/Line
Census block polygon** (MA / Middlesex County) and use the block centroid or
polygon. This gives **block-level** resolution — coarser than the PRD's
"exact coordinates" framing, but tight enough to attribute complaints to the
demo footprint. The TIGER blocks are not yet downloaded; that's the next step
if we wire up this component.

## Columns
`id, classification, category, type, origin_of_request,
most_recent_status_date, most_recent_status, date_created, block_code, ward`
(+ several experience-survey columns, mostly empty for these types).
