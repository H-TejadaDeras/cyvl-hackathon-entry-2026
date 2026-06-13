# Autodesk

Optional Autodesk: Best Capture-to-Design. Pair Cyvl capture data with an Autodesk APS output. Cyvl tells you what a street physically IS; Autodesk is where you DESIGN what comes next. 

AI can do a lot of the heavy lifting here. An AI coding assistant can write the APS auth/upload/translate calls, the geometry code, and debug viewer quirks. The flagship below was built in one afternoon this way. Describe the step, let AI draft it, verify in the viewer.

## What APS is

APS (Autodesk Platform Services, formerly Forge) is Autodesk's cloud API platform: REST endpoints to translate CAD files, render 3D in the browser, store files, and run Autodesk engines headless. No AutoCAD install required.

Sign up free: https://aps.autodesk.com/ (create an app to get a Client ID + Secret).

## Pick the right API

- **Viewer** (effort: Low) - renders 3D/2D models in the browser, free JS SDK. Use it for showing your result. Highest demo payoff.
- **Model Derivative** (effort: Low-Med) - translates CAD files (DWG, DXF, IFC, OBJ, RVT) to web format (SVF2) and extracts geometry/metadata. The bridge from Cyvl data to Autodesk; feeds the Viewer.
- **Data Management / OSS** (effort: Low) - cloud storage buckets for your files. Upload the file before translating it.
- **Design Automation** (effort: High) - runs AutoCAD / Civil 3D HEADLESS in the cloud. Use it to generate a real Civil 3D alignment or surface. Ambitious.

Skip the desktop Civil 3D .NET API (Windows + license + heavy install; you will lose hours). For Civil 3D output, use Design Automation in the cloud instead.

**ALSO, JUST EXPLORE IT YOURSELF!!!** There are lots of cool things you can do with it.

## The flagship workflow (a team of 4 can finish this)

**Street scan to CAD drawing to 3D web viewer.** Turn live Cyvl street data into an auto-generated CAD deliverable you can open and measure in a browser.

1. Pull Cyvl features for one block via the Cyvl API or MCP: road centerlines, curb lines, sign locations, pavement segments. You get coordinates + attributes.
2. Write a DXF from those features with ezdxf (free Python library). Centerlines and curbs become lines, signs become point blocks, one layer per feature type. This is the only real code you write for the Autodesk side. Field note: for full 3D scenes, write OBJ + MTL instead. Named OBJ groups (o name, no spaces) become individually selectable objects in the Viewer, and MTL carries material colors through Model Derivative. Zip OBJ + MTL together and submit with compressedUrn: true + rootFilename.
3. Authenticate: POST to the APS auth endpoint (2-legged OAuth2) with your Client ID + Secret. Scopes: data:read data:write bucket:create. You get a bearer token.
4. Upload: create an OSS bucket, upload your .dxf.
5. Translate: POST a Model Derivative job to SVF2. Poll the manifest until it reports complete. You now have a URN.
6. View: load the URN in the APS Viewer in your web app. You have an interactive, measurable CAD view of a real street, generated automatically from Cyvl data.
7. (Stretch) Overlay attributes: use the Viewer API to color segments by Cyvl pavement score, or drop markers at weight-limit signs. Now the CAD view is also a data view.

## Project ideas

Each idea pairs a Cyvl input with an Autodesk path. Pick by interest, then scope down to one street or one block. The browser path (DXF or OBJ to Model Derivative to APS Viewer) is the backbone for all of these.

### Starting Ideas!

- **1. Street Scan to CAD Export (EASY)** - flagship. Auto-generate a CAD drawing of a real street from Cyvl data. Cyvl: centerlines, curb lines, sign locations for a block. Autodesk: write features to DXF (ezdxf) to Model Derivative to APS Viewer. Hook: 'We turned a live street scan into a CAD deliverable in a day.' BUILT (June 2026), extended to full 3D: ground surfaces, buildings with point-measured roof shapes, cars/trees/poles/hydrants as individually movable objects, raw point cloud overlay toggle. Live demo: https://cyvl-scan-to-cad.vercel.app
- **2. Bike Lane / Restripe Proposal (MED).** Propose a restripe and show it in 3D before/after. Cyvl: road width, parking presence, signs. Autodesk: generate a restripe DXF to Viewer; toggle existing vs proposed. Hook: a planning artifact a city could actually react to.

## Links

- APS home + sign up: https://aps.autodesk.com/
- AEC documentation: https://aps.autodesk.com/developer/documentation?industry_tags=aec
- Model Derivative API: https://aps.autodesk.com/developer/overview/model-derivative-api
- ezdxf (DXF writer): https://ezdxf.readthedocs.io/