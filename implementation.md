Ingest Cyvl's LiDAR point cloud to automatically identify topographic low points on every street segment, compute their catchment area and modeled ponding volume, and cross-reference with Cyvl's CV-detected pavement condition scores and existing catch basin locations to produce a per-block drainage risk score. 

Layer Boston and Somerville open data — specifically 311 flooding complaints and storm sewer maps — on top of the Cyvl geometry to validate and weight each risk score against real historical flood events at those exact coordinates. 

Feed the scored geometry into Autodesk APS via ezdxf to generate a 3D cross-section rendering of each flagged low point, showing road profile, modeled water depth at a 2-inch rain event, and pavement condition — rendered in the APS Viewer as a measurable, browser-based deliverable an insurance underwriter or actuary can open without any CAD software. 

Package each street segment's risk score, LiDAR geometry, 311 complaint history, and Autodesk cross-section into a structured API response that an insurer queries by address to receive a CurbRisk score at policy-underwriting time — priced per query, per city license, or as a bulk dataset sale to catastrophe risk modelers like Moody's RMS or Verisk. 

The MVP demonstrates the full pipeline on one Somerville neighborhood: Cyvl data in, risk score and Autodesk 3D cross-section out, with a live demo showing a judge entering an address and receiving a drainage risk report in under 10 seconds.
