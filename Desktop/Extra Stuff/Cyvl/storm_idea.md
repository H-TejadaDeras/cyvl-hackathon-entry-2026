# Urban Drainage Failure and Pothole Risk Mapper

## Business Value

### What This Is

A data-driven drainage and pavement risk service that helps cities stop spending money in the wrong places. It combines LiDAR-derived terrain, pavement condition scores, catch basin locations, and public complaint records to answer one question before a paving or drainage project is approved: **is water going to destroy this repair again?**

---

### Who Buys It and Why

**Primary buyer — municipal Department of Public Works or Engineering**

| Buyer role | Decision they face | Why this product moves them |
|---|---|---|
| DPW Director / City Engineer | Where to spend $2–10M in paving and drainage capital this year | Replaces gut-feel prioritization with ranked, evidence-backed project list |
| Stormwater Program Manager | How to document MS4/NPDES permit compliance | Produces defensible gap analysis and capital plan exactly in the format EPA audits expect |
| Pavement or Asset Manager | How to stop patching the same pothole every winter | Identifies which segments fail repeatedly because of drainage, not just surface wear |
| Finance / Grant Writer | How to justify and fund the capital plan | Supplies mapped quantities, modeled benefits, and cost estimates suitable for FEMA BRIC and EPA CWSRF grant applications |

**Secondary buyers**

- **Civil engineering consultants** who deliver municipal drainage and roadway projects — they can license the workflow or receive the Autodesk Civil 3D / InfoDrainage starting model as a paid deliverable, saving 2–4 weeks of survey and setup work per engagement
- **State DOT and regional planning agencies** managing state-aid roads with recurring flood complaints across multiple municipalities
- **Flood insurance and infrastructure finance** — not near-term, but a city's quantified risk map has actuarial value

---

### Clear Value Delivered

**1. Stop repaving over unresolved drainage problems**
The most expensive mistake in public works is resurfacing a street that fails again in 18 months because the catch basin upstream is undersized. This product flags those streets before the contract is signed.

**2. Turn complaint clusters into defensible priority lists**
Right now, the loudest neighborhood gets the repair budget. This replaces political prioritization with a ranked list backed by terrain data, pavement scores, and 311 complaint history that any city councilmember can audit.

**3. Compress $50,000 of consultant scoping into hours**
A licensed engineer still stamps the final design. What this removes is the 4–6 week, $30,000–$60,000 GIS survey, data assembly, and site-screening phase that happens before design begins. The engineer receives a Civil 3D surface, catchment polygons, and an InfoDrainage baseline model on day one.

**4. Produce MS4 permit documentation automatically**
Every US municipality with a storm sewer system is required under NPDES to map its drainage network, identify failing infrastructure, and maintain a capital improvement plan. This tool generates exactly that documentation as a byproduct of the analysis.

**5. Move to the front of federal grant queues**
FEMA BRIC and EPA Clean Water State Revolving Fund both prioritize applicants who can show a pre-engineered, quantified gap analysis. Cities with this output skip the first round of eligibility screening.

---

### Data Required

| Dataset | Source | Role |
|---|---|---|
| LiDAR point cloud (.laz) | Cyvl | Extract road surface, micro-topography, flow paths, and depressions |
| 30-ft pavement condition scores | Cyvl | Identify structurally weak segments before scoring drainage exposure |
| Catch basin locations and imagery | Cyvl above-ground assets | Map existing drainage infrastructure against modeled flow accumulation |
| Street-level and panoramic imagery | Cyvl | Visual confirmation of flagged locations; Claude vision review |
| 311 flooding and pothole complaints | Somerville open data / SeeClickFix | Ground-truth validation and complaint-density scoring |
| Impervious surface layer | MassGIS | Scale raw terrain accumulation to actual runoff volume |
| Design storm precipitation depths | NOAA Atlas 14 | Compute peak flows at each node under 10-, 25-, 100-year events |
| FEMA National Flood Hazard Layer | FEMA | Add regulatory consequence weight to drainage gaps in mapped floodplains |
| Pavement repair and work order history | City public works records | Label historical failures for the pothole risk model |
| Storm sewer as-built records (pipe inverts, diameters) | City GIS or consultant | Required for full hydraulic simulation; declared assumptions if unavailable |

**What is already in hand:** Cyvl provides LiDAR, pavement scores, catch basin locations, and imagery for Somerville. The MassGIS and NOAA datasets are public and free. The 311 data requires a one-time download. As-built sewer records are the hardest input and are often incomplete — the prototype handles this by labeling assumed values separately from measured data.

---

### Steps to Market

**Step 1 — Prove it on one corridor (0–3 months)**
Run the full pipeline on a single Somerville street segment with known drainage complaints. Produce: a ranked gap list, a pothole risk map, an InfoDrainage baseline simulation, and a one-page summary a DPW director can read in five minutes. This is the sales artifact, not the software.

**Step 2 — Sell a fixed-scope paid pilot to one city ($20,000–$50,000)**
Scope: one paving package or complaint corridor. Deliverable: the study, ranked list, and Autodesk model. The city gets something it can act on. You get a paying reference customer, real work-order data to validate the model, and a case study. Somerville is the natural first target given the data already in hand.

**Step 3 — Validate the ROI claim**
After the pilot, track whether the city changed at least one capital or maintenance decision based on the output. Document the avoided cost. This single data point — "they stopped a $400,000 resurfacing job and addressed the drain first" — is worth more in the next sales conversation than any feature list.

**Step 4 — Expand through the consultant channel**
Engineering firms that already work on municipal drainage and roadway projects are a faster distribution path than selling city by city. Offer the Autodesk Civil 3D starting model as a licensed deliverable. The firm brings its own municipal relationships; the product compresses their scoping phase and improves their proposal win rate.

**Step 5 — Productize for recurring annual contracts**
After two or three cities, convert the service to a repeatable workflow: ingest new Cyvl surveys each year, update the risk scores, compare against completed projects, and refresh the capital plan. Annual contract priced by road miles or analyzed pavement sections.

**Step 6 — Layer in grant-writing and compliance reporting**
Once the capital plan output is proven, add a reporting module that generates MS4 permit documentation and grant application exhibits directly from the analysis results. This moves the product from a project tool to a compliance infrastructure subscription.

---

### Why This Wins Against the Alternatives

Generic pavement management software scores surface condition but does not simulate water. Flood models exist but don't explain which pavement repairs will fail again. Engineering consultants can build detailed drainage models — but after a project is already selected and funded. This product does the one thing none of them do: **connects drainage terrain and pavement condition before the capital plan is locked**, and hands the engineer a usable Autodesk starting point on day one.

The moat is the combination of Cyvl's measured LiDAR and pavement data with hydrologic modeling and Autodesk deliverables — no one else has all four layers integrated today.

---

## The Problem

Cities spend billions on stormwater infrastructure guided almost entirely by models built on assumptions. They don't know exactly where water pools after a storm. They don't know which streets act as open channels routing runoff toward basements and underpasses. They don't know whether the catch basin at the bottom of a hill was sized for the impervious surface that now drains into it, because that basin was designed in 1970 and the parking lot upslope was built in 2003.

The result: flooding complaints cluster around the same addresses year after year, maintenance crews respond reactively, and capital improvement dollars go to the loudest neighborhoods rather than the most hydraulically stressed ones.

Climate change is compressing rainfall into shorter, more intense bursts. A drainage system that handled a 10-year storm in 2000 may now face 25-year loads in the same pipe. Cities don't have the measurement infrastructure to know which of their drains are already undersized before the next major event — until something fails, and people's cars and basements are the sensors.

This project replaces the complaint-driven, reactive model with a terrain-informed, data-driven one.

---

## Customer and Business Value

### Best Initial Customer

The beachhead customer is a **mid-sized, cold-climate municipality that already has pavement-condition data, recurring drainage complaints, and an upcoming paving or stormwater capital plan**. Somerville is a strong example.

The customer organization is the Department of Public Works or Engineering Department:

| Role | Why they care |
|---|---|
| DPW Director or City Engineer | Economic buyer; must defend maintenance and capital spending |
| Stormwater Program Manager | Needs drainage priorities, permit documentation, and project candidates |
| Pavement or Asset Manager | Wants to prevent repeat potholes and coordinate paving with drainage repairs |
| GIS Manager | Supplies asset, complaint, and work-order data and maintains the resulting layers |
| Engineering consultant | Uses Civil 3D and InfoDrainage to validate findings and design the selected projects |

The consultant is an important channel and user, but the municipality is the best initial buyer because it owns the maintenance budget, complaints, infrastructure risk, and capital plan.

### Product Wedge

Do not initially sell this as a citywide digital twin or a promise to predict every pothole. Sell a fixed-scope **Drainage-Aware Street Maintenance Study** for one neighborhood, paving package, or known complaint corridor.

The study answers a budget decision:

> Before we repave these streets, where is water causing repeat pavement failure, and which drainage intervention should be included so we do not pay to repair the same location again?

The deliverable includes:

- Ranked 30-foot pavement sections and catchments requiring inspection
- Evidence for each location: pavement score, LiDAR depression, modeled ponding, imagery, complaints, and repair history
- Autodesk InfoDrainage comparison of the existing condition and practical interventions
- Recommended action: clean inlet, seal cracks, patch, adjust grading, add drainage, or reconstruct
- Civil 3D and GIS files that the city's engineer or consultant can continue using
- A budget-ready table with intervention type, quantity, urgency, and planning-level cost

### Economic Value

The value is not the map itself. It is avoiding bad capital and maintenance decisions.

| Current cost | Product value |
|---|---|
| Repaving over an unresolved drainage problem | Identifies drainage work that should occur before paving |
| Repeated pothole patching at the same location | Flags chronic moisture and deformation drivers |
| Broad field surveys before engineers know where to focus | Screens the network and narrows field validation to the highest-risk sites |
| Separate pavement and stormwater project lists | Creates one coordinated intervention plan |
| Complaint-driven prioritization | Adds measured terrain and hydraulic evidence |
| Consultant time spent assembling and cleaning data | Delivers an Autodesk-ready starting model |
| Weak grant or capital requests | Supplies maps, quantities, alternatives, and modeled outcomes |

The core ROI calculation for a pilot should be:

```
avoided repeat repairs
+ avoided premature resurfacing
+ reduced survey and model setup effort
+ avoided flood-response costs
- study and intervention cost
```

For each recommended project, report a simple benefit case: current annual repair burden, expected remaining pavement life, modeled flood or ponding reduction, estimated intervention cost, and estimated payback period. Do not claim savings until they are validated against municipal work-order and cost data.

### Regulatory and Stormwater-Fee Value

EPA does not impose a routine “stormwater tax” on municipalities. Two different mechanisms are often confused:

1. **Regulatory enforcement:** Municipal storm-sewer operators must comply with their MS4/NPDES permits. EPA or an authorized state can issue compliance orders and pursue civil penalties for permit violations. Citizen suits are also possible under the Clean Water Act.
2. **Stormwater utility fees:** A city may establish a local fee, often based on impervious area, to pay for drainage operations, maintenance, permit compliance, and capital projects. This is a municipal financing mechanism, not an EPA fine.

The larger financial exposure is often not the fine alone. A compliance order or settlement can require investigation, monitoring, reporting, accelerated maintenance, and capital improvements on a legally enforceable schedule. Those obligations can materially affect a city's budget.

This product creates business value by helping a city:

- Document a repeatable, data-driven process for inspecting and prioritizing stormwater assets
- Identify likely maintenance and capacity problems before they become documented permit failures
- Maintain evidence showing why projects were selected and how alternatives were evaluated
- Build an Autodesk-backed capital plan for correcting identified deficiencies
- Produce maps, model results, and progress metrics for permit reports, grant applications, and public review
- Direct stormwater utility revenue toward interventions with modeled benefits
- Support a future utility-fee or credit program with transparent project and impervious-area data, if the city operates such a program

The sales message should be **“reduce compliance risk and make stormwater spending defensible,”** not “buy this software and avoid EPA fines.” Hydraulic modeling alone does not demonstrate full MS4 compliance because permits also cover pollutant control, illicit discharges, construction activities, public education, monitoring, recordkeeping, and reporting.

Useful customer-facing metrics include:

| Metric | Business relevance |
|---|---|
| Percent of catch basins and high-risk areas screened | Demonstrates inspection and planning coverage |
| High-risk sites investigated or corrected | Shows progress against identified deficiencies |
| Modeled flood volume reduced | Quantifies hydraulic benefit |
| Repeat complaints or work orders avoided | Connects compliance work to operating savings |
| Projects completed by permit or capital-plan deadline | Supports management and reporting |
| Stormwater-fee dollars tied to ranked projects | Improves budget transparency |

The regulatory buyer may include the Stormwater Program Manager, Environmental Compliance Manager, or municipal counsel. The economic buyer remains the DPW Director, City Engineer, or utility director who controls the operating and capital budget.

Regulatory references:

- [EPA: Stormwater Discharges from Municipal Sources](https://www.epa.gov/npdes/stormwater-discharges-municipal-sources)
- [EPA: Clean Water Act enforcement authorities](https://www.epa.gov/enforcement/clean-water-act-cwa-and-federal-facilities)
- [Clean Water Act Section 309](https://www.law.cornell.edu/uscode/text/33/1319)

### Commercial Offering

Use a service-led model first because cities need engineering confidence and the workflow still depends on local data quality.

1. **Paid pilot:** one corridor or neighborhood, delivered as a study and Autodesk model.
2. **Capital-plan expansion:** process all streets in the next paving or drainage program.
3. **Annual refresh:** ingest new Cyvl surveys, complaints, work orders, and completed projects.
4. **Consultant workflow:** license or partner with civil engineering firms that already deliver municipal drainage and roadway projects.

A reasonable pricing hypothesis to test is a fixed-fee pilot in the **$20,000-$50,000** range, followed by citywide or annual contracts priced by road miles, LAZ volume, or number of analyzed pavement sections. This is a hypothesis for customer interviews, not a validated market price.

### Why It Wins

The differentiated value is the connection between four systems that are usually separate:

1. Cyvl's measured street condition and imagery
2. LiDAR-derived micro-topography and ponding
3. Autodesk hydraulic simulation and engineering deliverables
4. Maintenance history and capital-budget decisions

Generic flood models do not explain which pavement repairs will fail again. Pavement-management tools generally score surface condition without simulating water. Engineering consultants can build detailed models, but usually after a project has already been selected. This product helps select the right projects first and hands the engineer a usable Autodesk starting point.

### Proof Required

The pilot succeeds commercially only if it demonstrates:

- High-risk locations correspond to observed ponding, repeat repairs, or field-confirmed distress
- The analysis changes at least one maintenance or capital recommendation
- Autodesk scenario testing identifies a practical intervention with measurable benefit
- Staff spend less time assembling data and screening candidate locations
- The city can explain the resulting priority list to engineers, finance staff, and residents

The strongest case study is not “we produced a sophisticated model.” It is “the city changed a paving or drainage decision, avoided a repeat failure, and had evidence to defend the investment.”

---

If water accumulates in cracks or depressions, it may further weaken the pavement structure.

## Why Potholes Belong in This Model

Potholes are often the visible end of a drainage failure. Water enters pavement through cracks, poorly sealed utility cuts, and failed patches. Ponding keeps the pavement saturated; freeze-thaw cycles and traffic loading then break the weakened material apart. The same terrain model that identifies where runoff accumulates can therefore help identify where pavement is most likely to deteriorate next.

The defensible output is a **pothole risk forecast**, not a claim that a pothole will appear at an exact coordinate on an exact date. A single survey can detect existing depressions and distress. Predicting future failure requires combining those observations with drainage exposure, pavement condition, weather, traffic, repair history, and ideally repeated Cyvl surveys.

For each pavement segment, estimate the probability of a pothole report or confirmed failure within a chosen horizon, such as the next 3, 6, or 12 months. This turns the drainage analysis into a preventive maintenance tool: clean a blocked inlet, seal a crack, or patch a weak area before water and winter loading produce a larger failure.

---

## Why LiDAR Changes This

Traditional drainage modeling starts with survey-grade topographic maps or coarse DEMs, which miss the micro-topography that determines where water actually goes at street level. A 1-meter-resolution elevation model cannot see a two-inch crown differential between a road and a parking lot. Dense mobile LiDAR can.

The supplied Cyvl LAZ file is a one-street sample for developing and validating the workflow. It contains 53.5 million points with 1 cm stored Z precision and covers approximately 349 by 220 meters in WGS 84 / UTM zone 19N (EPSG:32619). The same processing steps can later run in batches across additional LAZ tiles for neighborhood or citywide coverage. From this sample we can derive:

**Terrain Model (DTM)**
The supplied LAZ is unclassified: all classification and return-number values are zero. Therefore, do not use a simple `classification == 2` ground filter. Clip the point cloud to buffered road corridors, remove vehicles and vertical objects with a ground-classification algorithm such as PDAL SMRF or CSF, and interpolate the resulting road surface. Validate the extracted surface against imagery before using centimeter-scale differences; stored precision is not the same as absolute vertical accuracy.

**Flow Direction**
Apply D8 or D-infinity flow direction algorithms to the DTM. Every cell drains to its steepest downslope neighbor. Streets with even a 0.5% cross-slope toward the gutter have a defined flow path. Parking lots that technically slope toward a drain basin show exactly how much area that basin receives.

**Flow Accumulation**
Accumulate upslope contributing area for each cell. High accumulation values at street intersections identify hydraulic pinch points — places where large drainage catchments converge on a single low point. These are the locations where capacity failures happen first.

**Sink Detection**
Terrain depressions that have no outfall path — either because the surrounding grade is too flat or because the digital surface shows a bowl — are candidate flood pools. In real terrain some of these are legitimate depressions that drain subsurface. Others are genuine stormwater traps.

**Catch Basin Cross-Reference**
Cyvl's computer vision pipeline detects catch basin grates from street-level imagery and logs their coordinates. Overlay detected basin locations onto the flow accumulation raster. Basins that sit at high-accumulation cells are doing the right job. High-accumulation cells with no detected basin are drainage gaps — places where runoff has nowhere to go.

**Pavement Deformation and Change Detection**
Fit a local reference surface to each pavement segment and measure negative elevation residuals, rutting, edge settlement, and localized depressions. With repeat Cyvl scans, align point clouds and calculate surface change over time. Areas that are sinking, roughening, or holding water receive a higher pothole risk score even before a discrete pothole is visible.

---

## Available Local Data

The project can run from files under `data/`; the Cyvl REST API is not required.

| Local dataset | Contents | Direct use |
|---|---|---|
| `global_xyz_rgb_icgu_5122_4000_4988.laz` | 53,524,498 unclassified points, EPSG:32619 | Extract road surface, slope, cross-slope, rutting, and local depressions within the tile |
| `30ft Pavement Scores` | 5,080 scored LineStrings; 0–100 score, condition label, street, area, `client_seg` | Primary pothole-risk unit and fine-grained pavement condition |
| `Segment-to-Segment Pavement Scores` | 894 scored LineStrings | Street-level summaries and joins through `client_seg` |
| `centerline` | 2,167 street LineStrings | Road masks, routing, nearest-street assignment, and aggregation |
| `aboveGroundAssets.geojson` | 8,254 assets, including 381 catch basins and image URLs | Basin locations and asset imagery; it does not contain pipe connectivity or invert data |
| `plainImagery` | 22,830 geotagged image points with bearing, timestamp, and URL | Visual pavement, crack, patch, and ponding review |
| `panoramicImagery` | 38,469 geotagged panorama points with viewer URLs | Intersection and surrounding drainage context |
| `sam.geojson` | 7,116 striping and marking LineStrings | Road-surface context and a possible road-corridor mask |
| `signs` | 3,782 sign points | Not needed for the core model; useful only as visual/location context |

All shapefiles and GeoJSON layers use WGS84 coordinates (EPSG:4326), while the LAZ uses EPSG:32619. Reproject vector layers to EPSG:32619 before buffering, distance calculations, point-cloud clipping, or raster analysis.

The sample LAZ overlaps 153 of the 30-foot pavement sections, 15 street-level pavement segments, 15 centerlines, 213 plain images, and 931 panoramas. It does not overlap a mapped catch basin. That is appropriate for testing pavement-surface extraction, deformation metrics, spatial joins, risk scoring, and imagery review on one street. Drainage-to-basin validation should be tested later on an additional tile that contains one or more catch basins. Production coverage is achieved by running the validated workflow across the broader Cyvl LAZ collection.

Design the implementation as a tile-based pipeline from the start:

1. Read each LAZ header to obtain its CRS and bounds.
2. Select only pavement, centerline, asset, and imagery features intersecting that tile.
3. Extract and rasterize the road surface within buffered street corridors.
4. Calculate pavement and drainage metrics per 30-foot section.
5. Write tile-level outputs with stable pavement and asset identifiers.
6. Merge the outputs into neighborhood or citywide GeoJSON, GeoPackage, and Civil 3D deliverables.

---

## Autodesk Simulation Role

Autodesk is part of the analytical core, not only the final visualization layer. Civil 3D prepares the measured terrain, catchments, and drainage geometry. Autodesk InfoDrainage then runs rainfall-runoff and hydraulic simulations for pipes, manholes, inlets, storage, ponds, and green infrastructure. Results can round-trip to Civil 3D for profiles, design changes, and plan production.

**Terrain Model Import**
Export the Cyvl DTM as a LandXML surface or LAS/LAZ point cloud. Civil 3D imports either format natively. The surface becomes a fully editable Civil 3D Tin Surface with breaklines preserved from the gutter lines and curb returns extracted from LiDAR.

**Catchment Delineation**
Civil 3D's hydrology tools include watershed and catchment analysis built on the same D8 flow direction logic. Using the imported terrain, draw catchment boundaries automatically. Each catchment polygon gets an area, a mean slope, a longest flow path, and an estimated time of concentration — the inputs needed for the Rational Method or SWMM to compute peak flow.

**Catch Basin Simulation**
A street catch basin is modeled in InfoDrainage as an inlet or manhole node connected to a drainage system. Assign the LiDAR-derived catchment, a rainfall event, imperviousness, inlet capacity, node elevation, and downstream connection. The simulation can report:

- Runoff hydrograph entering the basin
- Peak inflow and captured flow
- Water level and surcharge at the node
- Bypass or surface flooding when inlet or pipe capacity is exceeded
- Hydraulic and energy grade lines through the connected network
- Flood volume and duration under each design storm

The local asset GeoJSON supplies basin coordinates, but it does not contain grate capacity, invert elevation, pipe diameter, pipe connectivity, or outfall data. For a prototype, those values must either come from municipal records or be declared as test assumptions. They must not be presented as measured conditions.

**Detention Basin or Pond Simulation**
If “basin” means a detention pond or storage area, model it as a storage structure in InfoDrainage. Derive its footprint and elevations from the Civil 3D surface, define a stage-area or stage-volume relationship, add an outlet such as an orifice, weir, or pipe, and route a design storm through it. Compare peak water level, storage used, discharge rate, time to drain, and overflow volume.

**Scenario Testing**
Run the same storm against alternatives:

1. Existing or assumed configuration
2. Partially blocked inlet
3. Larger grate or added catch basin
4. Upsized downstream pipe
5. Added detention storage, swale, or permeable surface

This makes the Autodesk output a defensible comparison: which intervention most reduces flooding and ponding near pavement sections already susceptible to potholes?

**Drainage Network Model**
Place nodes at catch basin locations and connect them only when subsurface records or explicit prototype assumptions are available. Civil 3D maintains the 3D network geometry; InfoDrainage performs the hydraulic calculations. Survey records or municipal storm-sewer GIS are required for an as-built model.

**Gap Annotation**
Where the flow accumulation raster shows high contributing area but no basin exists, Civil 3D flags the cell as a drainage gap. Output an annotated plan set showing: existing basins, their catchment polygons, the flow paths draining into each, and gap locations with estimated contributing area and design storm runoff volume.

**Deliverable**
A Civil 3D drawing plus an InfoDrainage model containing design storms and alternatives. Deliver simulation tables for peak flow, surcharge, flood volume, pond level, and drainage time, along with profiles, maps, and PDF plan sheets.

---

## Data Pipeline

```
Cyvl LiDAR (.laz)
    │
    ▼
Reproject local vectors to EPSG:32619
    │
    ▼
Road-Corridor Clip + Ground Extraction (PDAL SMRF / CSF)
    │
    ▼
Road-Surface DTM (resolution selected after density/accuracy checks)
    │
    ├──▶ Flow Direction (D8, WhiteboxTools or SAGA GIS)
    │         │
    │         ▼
    │    Flow Accumulation Raster
    │         │
    │         ▼
    │    Sink / Depression Detection
    │
    └──▶ Export: LandXML Surface → Civil 3D
              │
              ├── Catchment Delineation (Civil 3D Hydrology)
              ├── Catch Basin / Pipe Geometry
              └── Exchange with Autodesk InfoDrainage
                            │
                            ├── Design Storms
                            ├── Runoff Hydrographs
                            ├── Pipe and Manhole Hydraulics
                            ├── Storage / Pond Routing
                            └── Flooding and Alternative Comparison

Local aboveGroundAssets.geojson
    │
    ▼
Filter asset_type == "CATCH_BASIN"
    │
    ▼
Node Coordinates → Civil 3D Pipe Network Nodes

External: Somerville 311 Flooding Complaints (CSV)
    │
    ▼
Geocode → Point Layer → Overlay on Flow Accumulation
    └── Validation: do model-predicted flood pools align with complaint clusters?

Local Pavement Shapefiles + Imagery Indexes
    │
    ├── Condition score, cracks, patches, utility cuts
    ├── LiDAR depression / rutting metrics
    ├── Ponding exposure from terrain
    └── Repeat-survey surface change, when available
              │
              ▼
External: Pothole 311 + Weather + Traffic + Repair History
              │
              ▼
Pothole Risk Model
    └── Segment probability for next 3, 6, or 12 months
```

---

## External Data Integration

**Somerville 311 Flooding Complaints**
This is not included in the local bundle and must be downloaded separately from Somerville's open data portal or SeeClickFix. Every flooding, pooling, and catch basin complaint is a labeled observation. Geocode each complaint address to a point. Overlay on the flow accumulation raster. If the model is working, complaint clusters should align with high-accumulation sinks. Mismatches tell you either where infrastructure is working well (drainage exists despite high accumulation) or where the model is missing something (subsurface drainage, off-sheet flow).

**MassGIS Impervious Surface Layer**
Impervious cover determines runoff coefficient — how much of a rainfall event becomes surface runoff vs. infiltration. A block with 90% impervious cover runs off nearly all rainfall; a residential block with mature tree canopy and permeable surfaces runs off 40-60%. Applying runoff coefficients to each catchment polygon scales the raw accumulation area to actual runoff volume estimates under a design storm.

**NOAA Precipitation Frequency Data (Atlas 14)**
Design storms — the 2-year, 10-year, 25-year, 100-year events — are defined by NOAA's Atlas 14 regional precipitation frequency estimates. For Somerville, plug in the 1-hour and 24-hour precipitation depths for each return period. Combined with catchment area and impervious fraction, this gives peak flow estimates in cubic feet per second at each basin node. Pipe capacity (derived from standard grate opening sizes and observed slope) can then be compared directly to design storm loads.

**Local Street Centerline**
The supplied centerline shapefile replaces the need to fetch OpenStreetMap for the pilot. It provides 2,167 connected road LineStrings for road masking, nearest-street assignment, and map routing. It should not be used to infer subsurface pipe connections.

**FEMA National Flood Hazard Layer**
100-year and 500-year floodplain boundaries for Somerville. Any drainage gap inside or adjacent to a FEMA floodplain has a higher consequence weight — infrastructure failure there contributes to a federally-mapped hazard zone, which directly affects MS4 permit compliance and flood insurance rates.

**Pothole Complaints and Work Orders**
These are not included in the local bundle. Once acquired, historical 311 pothole reports provide labels, while public works work orders indicate when a location was patched or reconstructed. Snap reports to pavement segments, remove duplicate reports for the same event, and define a prediction target such as "at least one pothole report in the next 90 days." Complaint data is an imperfect proxy because reporting varies by neighborhood, so a pilot should validate a sample against imagery or field inspection.

**Weather and Freeze-Thaw History**
Daily precipitation, temperature, and snowfall provide cumulative moisture exposure and freeze-thaw counts. Useful features include rainfall over the prior 7, 30, and 90 days; days when temperature crosses 32°F; snowmelt events; and heavy-rain intensity. These variables make the forecast time-aware rather than treating pavement condition as static.

**Traffic and Street Class**
Vehicle loading accelerates failure after water weakens pavement. Use available traffic counts, truck routes, bus routes, or road functional class as loading proxies. Utility cuts, prior patches, pavement age, and resurfacing history should be included when available.

---

## Scoring and Prioritization

Each identified drainage gap or at-risk basin gets a composite risk score:

| Factor | Signal | Weight |
|---|---|---|
| Flow accumulation (contributing area) | Larger = higher stress | High |
| Impervious fraction of catchment | Higher = faster runoff | High |
| 311 complaint density within 100m | Ground-truth failure signal | High |
| FEMA flood zone overlap | Regulatory consequence | Medium |
| Distance to nearest alternative basin | Redundancy assessment | Medium |
| Pavement condition (Cyvl PCI) | Degraded pavement = worse drainage | Low |

Output: ranked list of drainage gaps and at-risk basins, ordered by composite risk score, with contributing area, estimated peak runoff under 10-year storm, nearest complaint history, and FEMA zone flag.

Each pavement segment also gets a separate pothole risk score:

| Factor | Signal | Weight |
|---|---|---|
| Current pavement condition | Lower score and visible cracking = higher risk | High |
| Local ponding / flow accumulation | More water exposure = higher risk | High |
| LiDAR depression or surface change | Growing deformation = higher risk | High |
| Recent pothole and patch history | Repeated failure = higher risk | High |
| Freeze-thaw and precipitation exposure | More recent cycles = higher risk | Medium |
| Traffic, bus, or truck loading | Heavier loading = higher risk | Medium |
| Pavement age and utility cuts | Older or disturbed pavement = higher risk | Medium |

For a first demo, use a transparent weighted score. With enough historical labels, train a calibrated gradient-boosted tree model and evaluate it with time-based validation. Report precision among the top-ranked segments, recall, and calibration rather than accuracy alone, since pothole events are relatively rare.

Output: a map and CSV of pavement segments with 3-, 6-, or 12-month risk, the factors driving each score, and a recommended action such as inspect, crack-seal, clear drainage, or monitor.

---

## Claude Integration

Claude (via Anthropic SDK) wraps the analysis pipeline with a natural-language interface:

**Street-level imagery analysis**: For each flagged drainage gap, retrieve the nearest Cyvl street imagery. Ask Claude to describe what it sees — is there a basin grate visible that the CV model missed? Is there pavement ponding staining? Is the curb cut oriented in a way that would direct flow away from a drain?

The local asset and imagery files already contain `image_url` fields. Select the nearest plain image or panorama with a spatial join and use that URL directly; no Cyvl API lookup is needed.

**Report generation**: Feed the ranked gap list and catchment statistics to Claude to generate a plain-English summary suitable for city staff who are not GIS analysts. "The intersection of Elm and Morrison has a 2.3-acre contributing catchment that is 78% impervious. Under a 10-year storm, estimated peak runoff is 12 cfs. No catch basin was detected within 150 feet. This location has received 7 pooling complaints in the last 3 years, ranking it 3rd of 47 identified gaps."

**311 complaint triage**: When a new flooding complaint comes in (batch-processed from 311 exports), automatically cross-reference with the drainage gap database and return: is this location already flagged, what is its risk rank, and what is the modeled explanation for the flooding.

**Pothole risk explanation**: For each high-risk pavement segment, Claude summarizes the model's structured evidence and nearby imagery without inventing defects. "This segment ranks in the top 5% because it has poor pavement condition, a growing LiDAR depression, repeated winter pothole reports, and runoff concentrated along the curb. Inspect before the next freeze-thaw cycle."

---

## MS4 Permit Context

Every US municipality that discharges stormwater to navigable waters operates under an NPDES Municipal Separate Storm Sewer System (MS4) permit. Somerville's permit requires:

- Mapping of the stormwater system
- Identification of illicit discharges
- Capital improvement planning for failing infrastructure
- Public reporting on complaint response

This tool directly supports permit compliance. The Civil 3D drainage network output is exactly the format EPA auditors expect to see in an MS4 system map. The gap analysis provides defensible, data-driven documentation of identified deficiencies and a priority list for remediation — which is what the permit's capital improvement planning requirement calls for.

FEMA's BRIC (Building Resilient Infrastructure and Communities) program and EPA's Clean Water State Revolving Fund both prioritize projects with this kind of pre-engineering documentation. Cities that can show a quantified gap analysis and a prioritized capital plan move to the front of the funding queue.

---

## What This Is Not

This is not initially a real-time operational flood forecast. It uses Autodesk InfoDrainage to simulate selected historical or design storms before an event, compare infrastructure alternatives, and identify capacity failures. A future version could ingest observed or forecast rainfall, but that is outside the prototype.

It does not promise the exact location or date of a future pothole. Unless repeat surveys and sufficient historical failure labels are available, the pothole output is a screening-level susceptibility score. Existing potholes detected in imagery should be reported separately from forecast risk.

It is not a replacement for a licensed civil engineer's drainage study. The output is a prioritized list and a preliminary network model. A PE still stamps the final design. What this does is compress the initial scoping work that currently costs $50,000 in survey and GIS analysis into a few hours of automated terrain analysis on data Cyvl has already collected.

---

**Prototype success criteria**
- The one-street LAZ is processed without manually editing coordinates or bounds
- At least 90% of intersecting 30-foot pavement sections receive surface metrics
- Ranked sections link to nearby local imagery for visual review
- Outputs retain `inspect_id` and `client_seg` so results can merge across tiles
- Adding another LAZ requires only a new input path, not new analysis logic
- InfoDrainage completes at least one baseline and one intervention simulation
- Every assumed hydraulic input is labeled separately from measured Cyvl data
