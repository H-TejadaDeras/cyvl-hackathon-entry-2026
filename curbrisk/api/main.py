"""Phase 5: the CurbRisk API — query by address, get a drainage risk report.

Everything is pre-computed (scores.db + cross-sections), so a request is just:
geocode -> nearest segment in SQLite -> assemble JSON. Designed to answer in
well under 10 seconds (typically <1s after the first geocode).

Endpoints:
  GET /risk?address=...   -> full CurbRisk report for the nearest scored segment
  GET /crosssection/{id}.svg -> the rendered cross-section (APS fallback / demo)
  GET /map                -> ranked risk map of the whole demo tile (Phase 5)
  GET /segments.geojson   -> scored segments (risk band per block) for the map
  GET /layers/{name}.geojson -> supporting layers (low points, drains, 311)
  GET /health             -> liveness + dataset summary
  GET /                   -> minimal demo page with an address box

Run:
    uvicorn curbrisk.api.main:app --reload --port 8000
"""
from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path

import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse

from curbrisk import config as C
from curbrisk.scoring import insights as insights_mod

app = FastAPI(title="CurbRisk API", version="0.2.0")

XS_DIR = C.PROCESSED_DIR / "crosssections"
URN_CACHE = C.PROCESSED_DIR / "aps_urns.json"
IMAGERY_INDEX = C.PROCESSED_DIR / "imagery_index.json"
CRACKS_INDEX = C.PROCESSED_DIR / "cracks_index.json"

# In-memory crack-depth overrides (editable in the UI; depth is synthetic until
# real distress data arrives). Keyed by (segment_id, crack_id) -> depth_mm.
_CRACK_DEPTH_OVERRIDES: dict[tuple[str, str], float] = {}


def _db():
    con = sqlite3.connect(C.SCORES_DB)
    con.row_factory = sqlite3.Row
    return con


def _geocode(address: str):
    """Nominatim geocode, biased to the demo bbox."""
    w, s, e, n = C.LIDAR_BOUNDS_WGS84
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": address, "format": "json", "limit": 1,
                    "viewbox": f"{w-0.02},{n+0.02},{e+0.02},{s-0.02}"},
            headers={"User-Agent": "curbrisk-demo/0.1"}, timeout=10)
        j = r.json()
        if j:
            return float(j[0]["lat"]), float(j[0]["lon"])
    except Exception:
        pass
    return None


def _haversine(a_lat, a_lon, b_lat, b_lon):
    R = 6371000
    dlat = math.radians(b_lat - a_lat)
    dlon = math.radians(b_lon - a_lon)
    h = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(a_lat)) * math.cos(math.radians(b_lat)) * math.sin(dlon / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(h))


def _nearest_segment(lat, lon):
    con = _db()
    rows = con.execute("SELECT * FROM segments").fetchall()
    con.close()
    if not rows:
        return None, None
    best, bestd = None, 1e18
    for row in rows:
        d = _haversine(lat, lon, row["lat"], row["lon"])
        if d < bestd:
            best, bestd = row, d
    return best, bestd


def _viewer_for(segment_id: str):
    if URN_CACHE.exists():
        cache = json.loads(URN_CACHE.read_text())
        if segment_id in cache:
            return cache[segment_id]
    svg = XS_DIR / f"xsection_{segment_id}.svg"
    if svg.exists():
        return {"urn": None, "viewer": f"/crosssection/{segment_id}.svg", "status": "svg_fallback"}
    return None


def _ready_models() -> dict:
    """Segments that have a translated, ready APS model."""
    if not URN_CACHE.exists():
        return {}
    try:
        cache = json.loads(URN_CACHE.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return {k: v for k, v in cache.items()
            if v.get("urn") and v.get("status") == "ready"}


def _nearest_model_segment(lat, lon):
    """Nearest low-point segment that has a 3-D studio model (id, distance_m)."""
    ready = _ready_models()
    if not ready or lat is None or lon is None:
        return None
    con = _db()
    qs = ",".join("?" * len(ready))
    rows = con.execute(
        f"SELECT segment_id, lat, lon FROM segments WHERE segment_id IN ({qs})",
        list(ready)).fetchall()
    con.close()
    best, bd = None, 1e18
    for r in rows:
        d = _haversine(lat, lon, r["lat"], r["lon"])
        if d < bd:
            best, bd = r["segment_id"], d
    return (best, round(bd, 1)) if best else None


def _studio_for(seg):
    """Cross-section/studio entry for a segment; if it has no model of its own,
    fall back to the nearest low-point segment that does (so the studio always
    embeds for nearby addresses)."""
    sid = seg["segment_id"]
    xs = _viewer_for(sid)
    if xs and xs.get("status") == "ready":
        return xs
    nm = _nearest_model_segment(seg["lat"], seg["lon"])
    if nm:
        nsid, nd = nm
        nxs = _viewer_for(nsid)
        if nxs and nxs.get("status") == "ready":
            return {**nxs, "for_segment": nsid, "is_nearest_model": True,
                    "model_distance_m": nd}
    return xs


def _summary_for(segment_id: str):
    if not C.SUMMARIES_OUT.exists():
        return None
    try:
        payload = json.loads(C.SUMMARIES_OUT.read_text())
        return payload.get("summaries", {}).get(segment_id)
    except (OSError, json.JSONDecodeError):
        return None


def _imagery_for(segment_id: str):
    if not IMAGERY_INDEX.exists():
        return None
    try:
        idx = json.loads(IMAGERY_INDEX.read_text())
        return idx.get(segment_id)
    except (OSError, json.JSONDecodeError):
        return None


def _inside_demo_tile(lat: float, lon: float) -> bool:
    w, s, e, n = C.LIDAR_BOUNDS_WGS84
    pad_lat = C.TILE_BUFFER_M / 111_320.0
    pad_lon = C.TILE_BUFFER_M / (111_320.0 * math.cos(math.radians(lat)))
    return s - pad_lat <= lat <= n + pad_lat and w - pad_lon <= lon <= e + pad_lon


def _segment_row(segment_id: str):
    con = _db()
    row = con.execute("SELECT * FROM segments WHERE segment_id = ?", (segment_id,)).fetchone()
    con.close()
    return row


def _cracks_for(segment_id: str) -> list:
    """Synthetic cracks for a segment, with any in-memory depth overrides applied."""
    if not CRACKS_INDEX.exists():
        return []
    try:
        idx = json.loads(CRACKS_INDEX.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    cracks = [dict(c) for c in (idx.get(segment_id, {}) or {}).get("cracks", [])]
    for c in cracks:
        ov = _CRACK_DEPTH_OVERRIDES.get((segment_id, c["id"]))
        if ov is not None:
            c["depth_mm"] = ov
            c["depth_edited"] = True
    return cracks


@app.get("/health")
def health():
    try:
        con = _db()
        n = con.execute("SELECT COUNT(*) FROM segments").fetchone()[0]
        hi = con.execute("SELECT COUNT(*) FROM segments WHERE risk_band='High'").fetchone()[0]
        con.close()
        return {"status": "ok", "segments": n, "high_risk": hi,
                "demo_tile": C.LIDAR_BOUNDS_WGS84}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"dataset not built: {exc}")


@app.get("/risk")
def risk(
    address: str | None = Query(None, description="Street address in/near Somerville, MA"),
    lat: float | None = Query(None, ge=-90, le=90),
    lon: float | None = Query(None, ge=-180, le=180),
    segment_id: str | None = Query(None, description="look up a scored segment directly"),
):
    if segment_id:
        seg = _segment_row(segment_id)
        if seg is None:
            raise HTTPException(404, f"unknown segment '{segment_id}'")
        dist = 0.0
    else:
        has_coords = lat is not None or lon is not None
        if has_coords and (lat is None or lon is None):
            raise HTTPException(422, "lat and lon must be provided together")
        if not address and not has_coords:
            raise HTTPException(422, "provide an address, lat/lon, or segment_id")
        geo = (lat, lon) if has_coords else _geocode(address)
        if geo is None:
            raise HTTPException(404, "could not geocode address")
        lat, lon = geo
        if not _inside_demo_tile(lat, lon):
            raise HTTPException(404, "location is outside the CurbRisk demo footprint")
        seg, dist = _nearest_segment(lat, lon)
        if seg is None:
            raise HTTPException(503, "risk dataset not built — run the pipeline first")

    sid = seg["segment_id"]
    cracks = _cracks_for(sid)
    report = {
        "query": {"address": address, "lat": lat, "lon": lon, "segment_id": segment_id},
        "match": {"segment_id": sid, "client_seg": seg["client_seg"], "street": seg["street"],
                  "distance_m": round(dist, 1)},
        "curb_risk_score": seg["curb_risk"],
        "risk_band": seg["risk_band"],
        "components": {
            "topo_pts": seg["topo_pts"], "pavement_pts": seg["pavement_pts"],
            "basin_pts": seg["basin_pts"], "complaint_pts": seg["complaint_pts"],
        },
        "drainage": {
            "modeled_ponding_depth_in": seg["ponding_depth_in"],
            "catchment_sqft": seg["catchment_sqft"],
            "rain_event_in": C.RAIN_EVENT_IN,
            "nearest_drain_m": seg["nearest_drain_m"],
            "lidar_measured": bool(seg["has_lidar"]),
        },
        "pavement": {"pci": seg["pci"]},
        "complaints_311_nearby": seg["complaints_nearby"],
        "recommended_action": seg["recommended_action"],
        # the five actuarial insights replace the old fact grid as the report body
        "insights": insights_mod.compute_insights(seg, cracks=cracks),
        "cracks": cracks,
        "hydraulic_assumptions": json.loads(seg["hydraulic_assumptions"]),
        "narrative": _summary_for(sid),
        "cross_section": _studio_for(seg),
    }
    return JSONResponse(report)


@app.get("/simulate")
def simulate(
    segment_id: str = Query(..., description="scored segment to re-storm"),
    rain_in: float = Query(2.0, ge=0, le=20, description="24-hr rainfall (inches)"),
    snow_in: float = Query(0.0, ge=0, le=60, description="snowfall (inches)"),
):
    """Recompute ponding, CurbRisk and the 5 insights for a chosen rain+snow storm."""
    seg = _segment_row(segment_id)
    if seg is None:
        raise HTTPException(404, f"unknown segment '{segment_id}'")
    out = insights_mod.simulate(seg, rain_in=rain_in, snow_in=snow_in,
                                cracks=_cracks_for(segment_id))
    out["segment_id"] = segment_id
    out["baseline"] = {"curb_risk_score": seg["curb_risk"],
                       "ponding_depth_in": seg["ponding_depth_in"],
                       "design_storm_in": C.RAIN_EVENT_IN}
    return JSONResponse(out)


@app.get("/cracks/{segment_id}")
def cracks_get(segment_id: str):
    """Synthetic cracks for a segment (+ infiltration index)."""
    cracks = _cracks_for(segment_id)
    if not cracks and _segment_row(segment_id) is None:
        raise HTTPException(404, f"unknown segment '{segment_id}'")
    return {"segment_id": segment_id, "cracks": cracks,
            "infiltration": insights_mod.crack_infiltration_index(cracks)}


@app.post("/cracks/{segment_id}/{crack_id}/depth")
def crack_set_depth(
    segment_id: str, crack_id: str,
    depth_mm: float = Query(..., ge=0, le=500, description="override crack depth (mm)"),
):
    """Edit a (synthetic) crack's depth — placeholder until real data; in-memory."""
    cracks = _cracks_for(segment_id)
    if not any(c["id"] == crack_id for c in cracks):
        raise HTTPException(404, f"unknown crack '{crack_id}' for segment '{segment_id}'")
    _CRACK_DEPTH_OVERRIDES[(segment_id, crack_id)] = float(depth_mm)
    updated = _cracks_for(segment_id)
    return {"segment_id": segment_id, "crack_id": crack_id, "depth_mm": depth_mm,
            "infiltration": insights_mod.crack_infiltration_index(updated),
            "cracks": updated}


@app.get("/crosssection/{segment_id}.svg")
def crosssection(segment_id: str):
    p = XS_DIR / f"xsection_{segment_id}.svg"
    if not p.exists():
        raise HTTPException(404, "no cross-section for this segment")
    return FileResponse(p, media_type="image/svg+xml")


@app.get("/crosssection/{name}.png")
def crosssection_png(name: str):
    """Autodesk-rendered thumbnails (and any other PNG) for a cross-section."""
    p = XS_DIR / f"{name}.png"
    if not p.exists():
        raise HTTPException(404, "no image for this segment")
    return FileResponse(p, media_type="image/png")


@app.get("/aps/token")
def aps_token():
    """Short-lived viewer token (2-legged, viewables:read) for the APS Viewer.

    Only the read scope is exposed to the browser; upload/translate scopes stay
    server-side in the pipeline.
    """
    from curbrisk.output import aps_upload
    try:
        tok = aps_upload._token("viewables:read")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"APS auth failed: {exc}")
    if tok is None:
        raise HTTPException(503, "APS credentials not configured")
    return {"access_token": tok, "expires_in": 3600}


_STUDIO_HTML = """<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>CurbRisk · 3D Drainage Studio · __SID__</title>
<link rel=stylesheet href="https://developer.api.autodesk.com/modelderivative/v2/viewers/7.*/style.min.css">
<script src="https://developer.api.autodesk.com/modelderivative/v2/viewers/7.*/viewer3D.min.js"></script>
<style>
:root{--bg:#0e1116;--panel:#161b22;--line:#2a313c;--ink:#e6edf3;--mut:#8b97a7;--accent:#4aa3ff}
*{box-sizing:border-box}
html,body{margin:0;height:100%;font:14px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--ink)}
#bar{height:48px;background:#0a0e13;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:12px;padding:0 16px}
#bar b{font-size:15px}#bar .seg{color:var(--mut);font-size:13px}
#bar .chip{font-size:11px;background:#3a2a12;color:#ffcf86;border:1px solid #5a4220;border-radius:20px;padding:2px 9px}
#bar a{margin-left:auto;color:var(--mut);text-decoration:none;font-size:13px}#bar a:hover{color:#fff}
#main{position:absolute;top:48px;bottom:0;left:0;right:0;display:flex}
#viewerwrap{flex:1;position:relative;min-width:0;background:#1b1b1b}
#fv{position:absolute;inset:0}
#rain{position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:3}
#tint{position:absolute;inset:0;pointer-events:none;z-index:2;background:linear-gradient(180deg,rgba(20,60,120,0) 40%,rgba(20,70,140,0.0));transition:background .4s}
#pond{position:absolute;left:14px;bottom:14px;width:54px;z-index:4;background:rgba(10,14,19,.72);border:1px solid var(--line);border-radius:10px;padding:8px 6px;text-align:center}
#pond .g{height:90px;width:18px;margin:4px auto;background:#10202f;border-radius:4px;position:relative;overflow:hidden}
#pond .g i{position:absolute;left:0;right:0;bottom:0;background:linear-gradient(180deg,#4aa3ff,#1763d6);transition:height .4s}
#pond .v{font-size:13px;font-weight:700}#pond .k{font-size:9px;color:var(--mut);text-transform:uppercase;letter-spacing:.4px}
#panel{width:372px;background:var(--panel);border-left:1px solid var(--line);overflow-y:auto;padding:16px}
.card{background:#0e131a;border:1px solid var(--line);border-radius:12px;padding:14px;margin-bottom:14px}
.scorerow{display:flex;align-items:center;justify-content:space-between;gap:10px}
.scorerow .num{font-size:46px;font-weight:800;line-height:1}
.band{display:inline-block;padding:3px 11px;border-radius:999px;color:#fff;font-weight:700;font-size:12px}
h3{font-size:12px;text-transform:uppercase;letter-spacing:.5px;color:var(--mut);margin:0 0 10px}
.sl{margin:12px 0}
.sl label{display:flex;justify-content:space-between;font-size:13px;margin-bottom:5px}
.sl label b{color:var(--accent)}
input[type=range]{width:100%;accent-color:var(--accent)}
.simmeta{font-size:12px;color:var(--mut);margin-top:6px}
.btn{background:#1763d6;color:#fff;border:0;border-radius:8px;padding:7px 12px;font-size:12px;font-weight:600;cursor:pointer}
.btn.ghost{background:#1c2530;color:var(--ink)}
.ins{display:grid;gap:9px}
.ins .i{background:#11161d;border:1px solid var(--line);border-radius:10px;padding:10px 12px}
.ins .i .k{font-size:11px;color:var(--mut);text-transform:uppercase;letter-spacing:.4px}
.ins .i .v{font-size:18px;font-weight:700;margin-top:2px}
.ins .i .v small{font-size:11px;color:var(--mut);font-weight:500}
.ins .i .sub{font-size:11px;color:var(--mut);margin-top:2px}
.crk{display:flex;align-items:center;gap:8px;padding:7px 8px;border-radius:8px;cursor:pointer;border:1px solid transparent}
.crk:hover{background:#11161d}.crk.sel{background:#13233a;border-color:#27466e}
.crk .dot{width:10px;height:10px;border-radius:50%;flex:none}
.crk .id{font-weight:700;font-size:13px;width:34px}
.crk .dim{font-size:11px;color:var(--mut);flex:1}
.crk input[type=checkbox]{accent-color:var(--accent)}
#crackdet{font-size:12px;color:var(--mut);margin-top:8px;display:none}
#crackdet.show{display:block}
#crackdet input{width:70px;background:#11161d;border:1px solid var(--line);color:var(--ink);border-radius:6px;padding:3px 6px}
.muted{color:var(--mut)}.warn{color:#ffcf86}
</style></head><body>
<div id=bar><b>CurbRisk · 3D Drainage Studio</b><span class=seg id=segname>__SID__</span>
<span class=chip>synthetic cracks · demo</span><a href="/">← report</a></div>
<div id=main>
  <div id=viewerwrap>
    <div id=fv></div><div id=tint></div><canvas id=rain></canvas>
    <div id=pond><div class=k>Ponding</div><div class=g><i id=pondfill style="height:0%"></i></div><div class=v id=pondv>0"</div></div>
  </div>
  <div id=panel>
    <div class=card><div class=scorerow>
      <div><div class=k style="font-size:11px;color:var(--mut);text-transform:uppercase;letter-spacing:.4px">CurbRisk</div>
      <div class=num id=score>—</div></div>
      <span class=band id=band style="background:#888">—</span></div>
      <div class=simmeta id=scoremeta></div>
    </div>
    <div class=card><h3>Storm simulator</h3>
      <div class=sl><label>Rainfall <b><span id=rainv>2.0</span> in / 24 h</b></label>
        <input type=range id=rainsl min=0 max=8 step=0.25 value=2></div>
      <div class=sl><label>Snowfall <b><span id=snowv>0</span> in</b></label>
        <input type=range id=snowsl min=0 max=24 step=1 value=0></div>
      <div style="display:flex;gap:8px;align-items:center">
        <button class="btn ghost" id=reset>Design storm (2")</button>
        <span class=simmeta id=rpmeta></span></div>
    </div>
    <div class=card><h3>Actionable insights</h3><div class=ins id=insights></div></div>
    <div class=card><h3 id=crackhdr>Cracks</h3>
      <label style="font-size:12px;display:flex;gap:7px;align-items:center;margin-bottom:6px">
        <input type=checkbox id=crackall checked> show all cracks in model</label>
      <div id=cracklist></div>
      <div id=crackdet></div>
      <div class=simmeta style="margin-top:8px">Crack width/depth are <span class=warn>synthetic</span> (PCI-derived); depth is editable until real distress data lands.</div>
    </div>
  </div>
</div>
<script>
const SID='__SID__', URN='__URN__';
let viewer=null, objTree=null, crackDbIds={}, baseData=null, selCrack=null, pondDepth=0;
const $=id=>document.getElementById(id);
const COL={High:'#d9352a',Moderate:'#e8a33d',Low:'#2e8b57'};
const SEVC={High:'#d9352a',Medium:'#e8a33d',Low:'#f2d15b'};
const fmt=v=>(v===null||v===undefined)?'—':v;

/* ---------- APS viewer ---------- */
function showSvgFallback(msg){
  // Never leave the viewer pane an empty dark void (with rain falling on nothing):
  // drop in the always-available 2-D measured cross-section so there is a road.
  $('fv').innerHTML='<div style="position:absolute;inset:0;display:flex;flex-direction:column;'
    +'align-items:center;justify-content:center;gap:12px;padding:20px;text-align:center;background:#11161d">'
    +'<img src="/crosssection/'+SID+'.svg" onerror="this.remove()" '
    +'style="max-width:94%;max-height:74%;border:1px solid #2a313c;border-radius:10px;background:#f7f7f4">'
    +'<div style="color:#9fb1c9;font:13px/1.55 system-ui;max-width:520px">'
    +(msg||'')+' Showing the 2-D measured cross-section instead.</div></div>';
}
function frameModel(){
  // Fit AFTER geometry has streamed in; a second fit on the next frame settles
  // the camera once the bounding box is final.
  try{ viewer.fitToView(); requestAnimationFrame(()=>{ try{ viewer.fitToView(); }catch(e){} }); }catch(e){}
}
Autodesk.Viewing.Initializer({env:'AutodeskProduction',api:'streamingV2',
  getAccessToken:cb=>fetch('/aps/token').then(r=>{if(!r.ok)throw new Error('token HTTP '+r.status);return r.json();})
    .then(t=>cb(t.access_token,t.expires_in))
    .catch(e=>showSvgFallback('Autodesk viewer token unavailable ('+e.message+').'))},
  ()=>{
    viewer=new Autodesk.Viewing.GuiViewer3D($('fv'));
    viewer.start();
    viewer.setBackgroundColor(20,26,34,12,16,22);
    Autodesk.Viewing.Document.load('urn:'+URN, doc=>{
      const root=doc.getRoot();
      // A DXF translates to several viewables: a 3-D View (the extruded road +
      // water + crack meshes — what we want), a 2-D View, and an empty paperspace
      // "Layout1". getDefaultGeometry() can resolve to that empty layout and show
      // nothing, so pick the 3-D geometry explicitly, then fall back gracefully.
      const g3d=root.search({type:'geometry',role:'3d'});
      const g2d=root.search({type:'geometry',role:'2d'});
      const geom=(g3d&&g3d[0])||(g2d&&g2d[0])||root.getDefaultGeometry();
      if(!geom){ showSvgFallback('No renderable 3-D viewable in this model.'); return; }
      // Frame the model and wire up cracks only once GEOMETRY_LOADED fires —
      // calling fitToView() right after loadDocumentNode resolves points the
      // camera at empty space, so the road appears "missing" though it loaded.
      viewer.addEventListener(Autodesk.Viewing.GEOMETRY_LOADED_EVENT,
        ()=>{ frameModel(); mapCracks(); scheduleRainRebuild(); }, {once:true});
      viewer.addEventListener(Autodesk.Viewing.SELECTION_CHANGED_EVENT, onViewerSelect);
      viewer.addEventListener(Autodesk.Viewing.CAMERA_CHANGE_EVENT, scheduleRainRebuild);
      viewer.loadDocumentNode(doc, geom).then(()=>{
        // Some Viewer builds resolve after GEOMETRY_LOADED_EVENT has fired.
        mapCracks();
        scheduleRainRebuild();
      })
        .catch(err=>showSvgFallback('Could not load the geometry: '+(err&&err.message?err.message:err)));
    }, (code,msg)=>{ showSvgFallback('Document load error '+code+': '+msg); });
  });

function mapCracks(){
  try{
    viewer.getObjectTree(tree=>{
      objTree=tree; crackDbIds={};
      tree.enumNodeChildren(tree.getRootId(), id=>{
        const nm=(tree.getNodeName(id)||'').toUpperCase();
        const m=nm.match(/C\\d\\d/);
        if(nm.indexOf('CRACK')>=0 && m){ crackDbIds[m[0]]=id; }
      }, true);
      // DXF translation may expose the layer only through APS search rather
      // than in the object-tree node name.
      const cks=(baseData&&baseData.cracks)||[];
      cks.forEach(c=>viewer.search('CRACK_'+c.id, ids=>{
        if(ids&&ids.length){ crackDbIds[c.id]=ids[0]; renderCracks(); }
      }));
      renderCracks();
    });
  }catch(e){}
}

function onViewerSelect(e){
  const ids=e.dbIdArray||[]; if(!ids.length||!objTree) return;
  const nm=(objTree.getNodeName(ids[0])||'').toUpperCase();
  const m=nm.match(/C\\d\\d/);
  if(nm.indexOf('CRACK')>=0 && m) selectCrack(m[0], false);
}

/* ---------- data + render ---------- */
async function loadBase(){
  baseData=await fetch('/risk?segment_id='+SID).then(r=>r.json());
  $('segname').textContent=baseData.match.street+' · '+SID;
  setScore(baseData.curb_risk_score, baseData.risk_band, baseData.drainage.modeled_ponding_depth_in);
  renderInsights(baseData.insights);
  $('rpmeta').textContent='design storm '+baseData.drainage.rain_event_in+'"';
  renderCracks();
}

function setScore(score, band, ponding){
  pondDepth=Math.max(0,ponding||0);
  $('score').textContent=fmt(score);
  $('score').style.color=COL[band]||'#fff';
  const b=$('band'); b.textContent=(band||'—')+' RISK'; b.style.background=COL[band]||'#888';
  const maxd=12; const pct=Math.max(0,Math.min(100,(ponding/maxd)*100));
  $('pondfill').style.height=pct+'%'; $('pondv').textContent=(ponding??0).toFixed(1)+'"';
  const t=Math.min(.55,(ponding||0)/maxd*.6);
  $('tint').style.background='linear-gradient(180deg,rgba(20,60,120,0) 30%,rgba(30,90,170,'+t+'))';
}

function insCard(k,v,sub){return '<div class=i><div class=k>'+k+'</div><div class=v>'+v+'</div>'+(sub?'<div class=sub>'+sub+'</div>':'')+'</div>';}
function renderInsights(ins){
  if(!ins) return;
  const pv=ins.ponding_volume, rp=ins.storm_return_period, fv=ins.foundation_flow_vector,
        ci=ins.crack_infiltration_index, dr=ins.drainage_relief_score;
  $('insights').innerHTML=
    insCard('Ponding volume', fmt(pv.cubic_feet)+' <small>cf</small>', 'catchment × depth × 0.9 runoff')
   +insCard('Storm return period', fmt(rp.label), rp.annual_exceedance_prob!=null?('annual exceedance '+(rp.annual_exceedance_prob*100).toFixed(0)+'% · NOAA Atlas 14'):'NOAA Atlas 14 (Somerville)')
   +insCard('Foundation flow vector', (fv.grade_pct==null?'—':fv.grade_pct+'%'), fv.direction)
   +insCard('Crack infiltration', fmt(ci.index)+' <small>('+ci.score+')</small>', ci.n_cracks+' synthetic cracks weighted by proximity')
   +insCard('Drainage relief', fmt(dr.score)+' <small>/100</small>', dr.interpretation);
}

function renderCracks(){
  const cks=(baseData&&baseData.cracks)||[];
  $('crackhdr').textContent='Cracks ('+cks.length+')';
  $('cracklist').innerHTML=cks.map(c=>{
    const linked=crackDbIds[c.id]!=null;
    return '<div class=crk data-id="'+c.id+'">'
      +'<input type=checkbox class=ctog data-id="'+c.id+'" '+(linked?'':'disabled')+' checked>'
      +'<span class=dot style="background:'+(SEVC[c.severity]||'#888')+'"></span>'
      +'<span class=id>'+c.id+'</span>'
      +'<span class=dim>'+c.width_mm+' mm × '+c.length_m+' m · '+c.severity+(c.depth_edited?' · edited':'')+'</span></div>';
  }).join('') || '<div class=muted>no cracks</div>';
  $('cracklist').querySelectorAll('.crk').forEach(el=>{
    el.addEventListener('click',ev=>{ if(ev.target.classList.contains('ctog'))return; selectCrack(el.dataset.id,true); });
  });
  $('cracklist').querySelectorAll('.ctog').forEach(cb=>{
    cb.addEventListener('change',()=>toggleCrack(cb.dataset.id, cb.checked));
  });
}

function toggleCrack(id, show){
  const db=crackDbIds[id]; if(db==null||!viewer)return;
  show?viewer.show(db):viewer.hide(db);
}
$('crackall').addEventListener('change',e=>{
  document.querySelectorAll('.ctog').forEach(cb=>{ if(!cb.disabled){cb.checked=e.target.checked; toggleCrack(cb.dataset.id,e.target.checked);} });
});

function selectCrack(id, fromPanel){
  selCrack=id;
  document.querySelectorAll('.crk').forEach(el=>el.classList.toggle('sel',el.dataset.id===id));
  const c=((baseData&&baseData.cracks)||[]).find(x=>x.id===id); if(!c)return;
  const det=$('crackdet'); det.classList.add('show');
  det.innerHTML='<b style="color:var(--ink)">Crack '+id+'</b> — '+c.orientation+', '+c.severity+' severity<br>'
    +'width <b style="color:var(--ink)">'+c.width_mm+' mm</b> · length <b style="color:var(--ink)">'+c.length_m+' m</b> · '
    +(c.dist_to_low_m)+' m from low point<br>'
    +'depth <input type=number id=depthin value="'+c.depth_mm+'" min=0 max=500 step=1> mm '
    +'<button class=btn id=depthsave>save</button> <span class=warn>synthetic</span>';
  $('depthsave').addEventListener('click',()=>saveDepth(id));
  const db=crackDbIds[id];
  if(db!=null&&viewer){ try{ viewer.select([db]); viewer.fitToView([db]); }catch(e){} }
}

async function saveDepth(id){
  const v=parseFloat($('depthin').value); if(isNaN(v))return;
  const r=await fetch('/cracks/'+SID+'/'+id+'/depth?depth_mm='+v,{method:'POST'}).then(r=>r.json());
  baseData.cracks=r.cracks;                        // refresh dims (incl. edited flag)
  renderInsights(Object.assign({}, baseData.insights, {crack_infiltration_index:r.infiltration}));
  baseData.insights.crack_infiltration_index=r.infiltration;
  renderCracks(); selectCrack(id,true);
}

/* ---------- simulator ---------- */
let simT=null;
function onSim(){
  const rain=parseFloat($('rainsl').value), snow=parseFloat($('snowsl').value);
  $('rainv').textContent=rain.toFixed(2); $('snowv').textContent=snow.toFixed(0);
  setRain(rain, snow);
  clearTimeout(simT);
  simT=setTimeout(async()=>{
    const d=await fetch('/simulate?segment_id='+SID+'&rain_in='+rain+'&snow_in='+snow).then(r=>r.json());
    setScore(d.curb_risk_score, d.risk_band, d.modeled_ponding_depth_in);
    renderInsights(d.insights);
    const rp=d.insights.storm_return_period;
    $('scoremeta').textContent='ponding '+d.modeled_ponding_depth_in+'" · baseline '+d.baseline.curb_risk_score
      +' @ '+d.baseline.design_storm_in+'"';
    $('rpmeta').textContent=rp.label+' · effective '+d.applied_storm.effective_rain_in+'" (incl. snowmelt)';
  }, 160);
}
$('rainsl').addEventListener('input',onSim);
$('snowsl').addEventListener('input',onSim);
$('reset').addEventListener('click',()=>{ $('rainsl').value=2; $('snowsl').value=0; onSim(); });

/* ---------- rain/snow rendered over the Autodesk view ---------- */
const cv=$('rain'), ctx=cv.getContext('2d');
let parts=[], rainI=0.25, snowI=0, cw=1, ch=1, rainRebuildT=null;
function resize(){
  const r=cv.getBoundingClientRect(), dpr=Math.min(window.devicePixelRatio||1,2);
  cw=Math.max(1,r.width||cv.parentElement.clientWidth||window.innerWidth);
  ch=Math.max(1,r.height||cv.parentElement.clientHeight||window.innerHeight);
  cv.width=Math.round(cw*dpr); cv.height=Math.round(ch*dpr);
  ctx.setTransform(dpr,0,0,dpr,0,0);
  rebuild();
}
window.addEventListener('resize',resize);
if(window.ResizeObserver){ try{ new ResizeObserver(resize).observe($('viewerwrap')); }catch(e){} }
function scheduleRainRebuild(){
  clearTimeout(rainRebuildT);
  rainRebuildT=setTimeout(rebuild,80);
}
function setRain(rain, snow){ rainI=rain/8; snowI=snow/24; rebuild(); }
function roadTarget(){
  if(viewer&&viewer.model){
    try{
      const b=viewer.model.getBoundingBox();
      // The CAD also contains long annotation text, so the full model bounds
      // are wider than the pavement. Target the generated 18 m x 8 m road slab.
      const p=new THREE.Vector3(
        -8.7+Math.random()*17.4,
        -3.8+Math.random()*7.6,
        b.min.z+0.03
      );
      const q=viewer.worldToClient(p);
      if(Number.isFinite(q.x)&&Number.isFinite(q.y)){
        return {x:Math.max(0,Math.min(cw,q.x)),y:Math.max(ch*.2,Math.min(ch,q.y))};
      }
    }catch(e){}
  }
  return {x:Math.random()*cw,y:ch*(.62+Math.random()*.28)};
}
function resetParticle(p, initial=false){
  const t=roadTarget(); p.tx=t.x; p.ty=t.y;
  p.y=initial?Math.random()*p.ty:-Math.random()*ch*.35;
  p.x=p.tx+(p.ty-p.y)*.09;
}
function drawPond(){
  if(!pondDepth||!viewer||!viewer.model)return;
  try{
    // The modeled sag is the CAD origin. Project a small local road frame so
    // the puddle stays attached to the pavement while the user orbits the view.
    const z=viewer.model.getBoundingBox().min.z+0.035;
    const c=viewer.worldToClient(new THREE.Vector3(0,0,z));
    const ax=viewer.worldToClient(new THREE.Vector3(4,0,z));
    const ay=viewer.worldToClient(new THREE.Vector3(0,3,z));
    if(![c.x,c.y,ax.x,ax.y,ay.x,ay.y].every(Number.isFinite))return;
    const growth=Math.min(1,Math.sqrt(pondDepth/8));
    const rx=Math.max(14,Math.hypot(ax.x-c.x,ax.y-c.y)*(.28+.62*growth));
    const ry=Math.max(8,Math.hypot(ay.x-c.x,ay.y-c.y)*(.24+.58*growth));
    const angle=Math.atan2(ax.y-c.y,ax.x-c.x);
    ctx.save();
    ctx.translate(c.x,c.y); ctx.rotate(angle);
    const g=ctx.createRadialGradient(0,0,ry*.08,0,0,rx);
    g.addColorStop(0,'rgba(55,145,225,'+(.24+.22*growth)+')');
    g.addColorStop(.72,'rgba(35,115,205,'+(.18+.20*growth)+')');
    g.addColorStop(1,'rgba(30,95,180,0)');
    ctx.fillStyle=g; ctx.beginPath(); ctx.ellipse(0,0,rx,ry,0,0,Math.PI*2); ctx.fill();
    ctx.strokeStyle='rgba(135,205,255,'+(.18+.25*growth)+')';
    ctx.lineWidth=1.2; ctx.beginPath(); ctx.ellipse(0,0,rx*.72,ry*.55,0,0,Math.PI*2); ctx.stroke();
    ctx.restore();
  }catch(e){}
}
function rebuild(){
  const nRain=Math.round(rainI*420), nSnow=Math.round(snowI*220);
  parts=[];
  for(let i=0;i<nRain;i++){
    const p={t:'r',l:6+Math.random()*14,s:7+Math.random()*8};
    resetParticle(p,true); parts.push(p);
  }
  for(let i=0;i<nSnow;i++){
    const p={t:'s',r:1.2+Math.random()*2.4,s:1+Math.random()*1.8,d:Math.random()*6.28};
    resetParticle(p,true); parts.push(p);
  }
}
function tick(){
  ctx.clearRect(0,0,cw,ch);
  drawPond();
  for(const p of parts){
    if(p.t==='r'){ ctx.strokeStyle='rgba(150,190,255,.55)'; ctx.lineWidth=1.1;
      ctx.beginPath(); ctx.moveTo(p.x,p.y); ctx.lineTo(p.x-1.5,p.y+p.l); ctx.stroke();
      p.y+=p.s; p.x-=p.s*.09; if(p.y>p.ty)resetParticle(p); }
    else{ ctx.fillStyle='rgba(255,255,255,.85)'; ctx.beginPath();
      ctx.arc(p.x,p.y,p.r,0,6.28); ctx.fill();
      p.y+=p.s; p.x-=p.s*.09; p.x+=Math.sin((p.d+=0.02))*.6;
      if(p.y>p.ty)resetParticle(p); }
  }
  requestAnimationFrame(tick);
}
// defer first spawn to after layout/paint so the canvas has a real width
requestAnimationFrame(()=>{ resize(); rebuild(); tick(); });

loadBase();
</script></body></html>"""


@app.get("/viewer/{segment_id}", response_class=HTMLResponse)
def viewer(segment_id: str):
    """Interactive 3-D Drainage Studio: Autodesk APS Viewer (LiDAR road + water +
    toggleable cracks) with a live rain/snow simulator and the 5 insights."""
    entry = None
    if URN_CACHE.exists():
        entry = json.loads(URN_CACHE.read_text()).get(segment_id)
    if not entry or not entry.get("urn") or entry.get("status") != "ready":
        raise HTTPException(404, "no translated APS model for this segment")
    return _STUDIO_HTML.replace("__URN__", entry["urn"]).replace("__SID__", segment_id)


@app.get("/segments.geojson")
def segments_geojson():
    """Scored segments (one LineString per 30-ft block) for the ranked map."""
    if not C.SCORES_OUT.exists():
        raise HTTPException(503, "risk dataset not built — run the pipeline first")
    return JSONResponse(json.loads(C.SCORES_OUT.read_text()))


_LAYERS = {
    "low_points": C.LOWPOINTS_OUT,
    "storm_drains": C.PROCESSED_DIR / "storm_drains.geojson",
    "flood_complaints": C.PROCESSED_DIR / "flood_complaints.geojson",
    "catch_basins": C.BASINS_OUT,
}


@app.get("/layers/{name}.geojson")
def layer_geojson(name: str):
    """Supporting overlays for the map: low points, drains, 311 complaints."""
    path = _LAYERS.get(name)
    if path is None:
        raise HTTPException(404, f"unknown layer '{name}'")
    if not path.exists():
        # an empty-but-valid collection keeps the map happy when a layer is sparse
        return JSONResponse({"type": "FeatureCollection", "features": []})
    return JSONResponse(json.loads(path.read_text()))


@app.get("/map", response_class=HTMLResponse)
def risk_map():
    w, s, e, n = C.LIDAR_BOUNDS_WGS84
    cx, cy = (w + e) / 2, (s + n) / 2
    return """<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>CurbRisk — ranked drainage risk map</title>
<link rel=stylesheet href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
:root{--ink:#1a1f24;--mut:#5c6772;--line:#e3e6ea}
*{box-sizing:border-box}
html,body{margin:0;height:100%;font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:var(--ink)}
header{background:#0f1b2d;color:#fff;padding:14px 20px;display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
header h1{margin:0;font-size:18px;letter-spacing:-.3px}
header a{color:#9fb1c9;font-size:14px;text-decoration:none}
header a:hover{color:#fff}
#map{position:absolute;top:54px;bottom:0;left:0;right:0}
.legend{background:#fff;border:1px solid var(--line);border-radius:10px;padding:10px 12px;line-height:1.7;font-size:13px;box-shadow:0 1px 4px rgba(0,0,0,.12)}
.legend b{display:block;margin-bottom:4px;font-size:12px;text-transform:uppercase;letter-spacing:.4px;color:var(--mut)}
.legend i{width:22px;height:5px;display:inline-block;border-radius:3px;margin-right:8px;vertical-align:middle}
.legend .dot{width:12px;height:12px;border-radius:50%;display:inline-block;margin-right:6px;vertical-align:middle;border:1px solid #fff;box-shadow:0 0 0 1px #999}
.leaflet-popup-content{font:14px/1.45 system-ui,sans-serif}
.pp h3{margin:0 0 4px;font-size:15px}
.pp .sc{font-size:26px;font-weight:800;line-height:1}
.pp .band{display:inline-block;padding:2px 9px;border-radius:999px;color:#fff;font-weight:700;font-size:12px;margin-left:6px;vertical-align:middle}
.pp .row{color:var(--mut);font-size:13px;margin-top:5px}
.pp a{display:inline-block;margin-top:8px;color:#1763d6;font-weight:600;text-decoration:none}
</style></head><body>
<header><h1>CurbRisk — ranked drainage risk · Somerville demo tile</h1>
<a href="/">← address lookup</a></header>
<div id=map></div>
<script>
const COL={High:'#d9352a',Moderate:'#e8a33d',Low:'#2e8b57'};
const map=L.map('map').setView([__CY__,__CX__],17);
L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
  {attribution:'© OpenStreetMap © CARTO',maxZoom:20}).addTo(map);

function popupHtml(p){
  const col=COL[p.risk_band]||'#888';
  return '<div class=pp><h3>'+(p.street||'segment')+'</h3>'
    +'<span class=sc style="color:'+col+'">'+(p.curb_risk??'—')+'</span>'
    +'<span class=band style="background:'+col+'">'+(p.risk_band||'')+'</span>'
    +'<div class=row>topo '+(p.topo_pts??'—')+' · pavement '+(p.pavement_pts??'—')
    +' · drainage '+(p.basin_pts??'—')+' · 311 '+(p.complaint_pts??'—')+'</div>'
    +'<div class=row>PCI '+(p.pci??'—')+' · '+(p.has_lidar?'LiDAR-measured':'topo-imputed')
    +' · action: '+(p.recommended_action||'—')+'</div>'
    +'<a href="/risk?lat='+p._lat+'&lon='+p._lon+'" target=_blank>full report (JSON) ↗</a></div>';
}

fetch('/segments.geojson').then(r=>r.json()).then(gj=>{
  const layer=L.geoJSON(gj,{
    style:f=>({color:COL[f.properties.risk_band]||'#888',
      weight:f.properties.risk_band==='High'?8:5,opacity:.9}),
    onEachFeature:(f,lyr)=>{
      // a representative coordinate for the address-query deep link
      const c=f.geometry.coordinates, m=c[Math.floor(c.length/2)];
      f.properties._lon=m[0]; f.properties._lat=m[1];
      lyr.bindPopup(popupHtml(f.properties));
      lyr.on('mouseover',()=>lyr.setStyle({weight:9}));
      lyr.on('mouseout',()=>layer.resetStyle(lyr));
    }
  }).addTo(map);
  try{ map.fitBounds(layer.getBounds().pad(0.05)); }catch(e){}
});

// supporting overlays
fetch('/layers/low_points.geojson').then(r=>r.json()).then(gj=>{
  L.geoJSON(gj,{pointToLayer:(f,ll)=>L.circleMarker(ll,
    {radius:7,color:'#1763d6',weight:2,fillColor:'#5aa0ff',fillOpacity:.9})
    .bindPopup('<b>Modeled low point</b><br>'+(f.properties.street||'')
      +'<br>ponding '+(f.properties.ponding_depth_in??'—')+' in @ 2&quot; storm'
      +'<br>catchment '+(f.properties.catchment_sqft??'—')+' sqft')}).addTo(map);
});
fetch('/layers/storm_drains.geojson').then(r=>r.json()).then(gj=>{
  L.geoJSON(gj,{pointToLayer:(f,ll)=>L.circleMarker(ll,
    {radius:5,color:'#2c9c8f',weight:2,fillColor:'#7fd6c9',fillOpacity:.9})
    .bindPopup('Storm drain')}).addTo(map);
});
fetch('/layers/flood_complaints.geojson').then(r=>r.json()).then(gj=>{
  L.geoJSON(gj,{pointToLayer:(f,ll)=>L.circleMarker(ll,
    {radius:6,color:'#b03060',weight:2,fillColor:'#e87da6',fillOpacity:.9})
    .bindPopup('<b>311 flood report</b><br>'+(f.properties.case_title||'')
      +'<br>'+(f.properties.date||''))}).addTo(map);
});

const legend=L.control({position:'bottomright'});
legend.onAdd=function(){
  const d=L.DomUtil.create('div','legend');
  d.innerHTML='<b>CurbRisk band</b>'
    +'<div><i style="background:#d9352a"></i>High</div>'
    +'<div><i style="background:#e8a33d"></i>Moderate</div>'
    +'<div><i style="background:#2e8b57"></i>Low</div>'
    +'<b style="margin-top:8px">Overlays</b>'
    +'<div><span class=dot style="background:#5aa0ff"></span>Modeled low point</div>'
    +'<div><span class=dot style="background:#7fd6c9"></span>Storm drain</div>'
    +'<div><span class=dot style="background:#e87da6"></span>311 flood report</div>';
  return d;
};
legend.addTo(map);
</script></body></html>""".replace("__CY__", str(cy)).replace("__CX__", str(cx))


@app.get("/", response_class=HTMLResponse)
def home():
    return """<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>CurbRisk — Street-level drainage risk</title>
<style>
:root{--ink:#1a1f24;--mut:#5c6772;--line:#e3e6ea;--bg:#f6f7f9;--card:#fff}
*{box-sizing:border-box}
body{font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;color:var(--ink);background:var(--bg)}
header{background:#0f1b2d;color:#fff;padding:22px 0}
.wrap{max-width:920px;margin:0 auto;padding:0 20px}
header h1{margin:0;font-size:22px;letter-spacing:-.3px}
header p{margin:4px 0 0;color:#9fb1c9;font-size:14px}
.search{display:flex;gap:10px;margin:24px 0}
.search input{flex:1;padding:13px 14px;font-size:16px;border:1px solid var(--line);border-radius:10px;background:var(--card)}
.search button{padding:13px 22px;font-size:16px;font-weight:600;cursor:pointer;border:0;border-radius:10px;background:#1763d6;color:#fff}
.search button:disabled{opacity:.5;cursor:wait}
.hint{font-size:13px;color:var(--mut);margin:-12px 0 20px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:22px;margin-bottom:18px}
.scorehead{display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap}
.scorehead h2{margin:0;font-size:20px}
.scorehead .sub{color:var(--mut);font-size:14px;margin-top:2px}
.gauge{text-align:center;min-width:120px}
.gauge .num{font-size:42px;font-weight:800;line-height:1}
.band{display:inline-block;padding:4px 12px;border-radius:999px;color:#fff;font-weight:700;font-size:13px;margin-top:4px}
.bars{margin:18px 0 4px}
.bar{display:grid;grid-template-columns:130px 1fr 52px;align-items:center;gap:10px;margin:7px 0;font-size:14px}
.track{background:#eef1f4;border-radius:6px;height:12px;overflow:hidden}
.fill{height:100%;border-radius:6px}
.facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin-top:6px}
.fact{background:var(--bg);border-radius:10px;padding:12px 14px}
.fact .k{font-size:12px;color:var(--mut);text-transform:uppercase;letter-spacing:.4px}
.fact .v{font-size:19px;font-weight:700;margin-top:3px}
.fact .v small{font-size:12px;color:var(--mut);font-weight:500}
h3{font-size:15px;text-transform:uppercase;letter-spacing:.5px;color:var(--mut);margin:0 0 12px}
img.xs{width:100%;border:1px solid var(--line);border-radius:10px}
.studioframe{width:100%;height:560px;border:1px solid var(--line);border-radius:12px;background:#0e1116;display:block}
a.studio{display:inline-block;background:#1763d6;color:#fff;font-weight:600;text-decoration:none;border-radius:8px;padding:8px 14px;font-size:14px}
.insgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px}
.ic{background:var(--bg);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.ic .k{font-size:11px;color:var(--mut);text-transform:uppercase;letter-spacing:.4px}
.ic .v{font-size:20px;font-weight:700;margin-top:3px}
.ic .v small{font-size:12px;color:var(--mut);font-weight:500}
.ic .sub{font-size:11px;color:var(--mut);margin-top:3px}
.thumbs{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px}
.thumbs a{display:block}
.thumbs img{width:100%;height:130px;object-fit:cover;border-radius:10px;border:1px solid var(--line)}
.tag{display:inline-block;font-size:12px;background:#eef3fb;color:#1763d6;border-radius:6px;padding:2px 8px;margin-left:6px;font-weight:600}
.vision{background:#fbfaf4;border-left:3px solid #d4a72c;padding:12px 16px;border-radius:0 10px 10px 0;font-size:14px}
.assume{font-size:12px;color:var(--mut);margin-top:10px}
details{margin-top:12px}summary{cursor:pointer;color:var(--mut);font-size:14px}
pre{background:#0f1b2d;color:#cfe0f5;padding:14px;border-radius:10px;overflow:auto;font-size:12px}
.err{color:#c0392b;font-weight:600}
.muted{color:var(--mut)}
</style></head><body>
<header><div class=wrap style="display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap">
<div><h1>CurbRisk</h1>
<p>Street-level drainage risk for underwriting · Somerville, MA demo tile</p></div>
<a href="/map" style="color:#9fb1c9;font-size:14px;text-decoration:none">Ranked risk map →</a>
</div></header>
<div class=wrap>
<div class=search>
<input id=a placeholder="e.g. 20 Avon Street, Somerville MA" value="Avon Street, Somerville MA"
  onkeydown="if(event.key==='Enter')go()">
<button id=btn onclick=go()>Get risk</button>
</div>
<p class=hint>Enter any address inside the demo footprint. Returns a CurbRisk score, five
actuarial insights, and an interactive Autodesk 3D drainage studio (LiDAR model,
toggleable cracks, live rain/snow simulator).</p>
<div id=out></div>
</div>
<script>
const COL={High:'#d9352a',Moderate:'#e8a33d',Low:'#2e8b57'};
const fmt=v=>(v===null||v===undefined)?'—':v;
function ic(k,v,sub){return '<div class=ic><div class=k>'+k+'</div><div class=v>'+v+'</div>'
  +(sub?'<div class=sub>'+sub+'</div>':'')+'</div>';}
async function go(){
  const a=document.getElementById('a').value;
  const o=document.getElementById('out'); const btn=document.getElementById('btn');
  o.innerHTML='<div class=card>Scoring…</div>'; btn.disabled=true;
  let r,d;
  try{ r=await fetch('/risk?address='+encodeURIComponent(a)); }
  catch(e){ o.innerHTML='<div class="card err">Network error</div>'; btn.disabled=false; return; }
  btn.disabled=false;
  if(!r.ok){
    let m='Error '+r.status;
    try{ m=(await r.json()).detail||m; }catch(e){}
    o.innerHTML='<div class="card err">'+m+'</div>'; return;
  }
  d=await r.json();
  const col=COL[d.risk_band]||'#888';
  const ins=d.insights||{};
  const pv=ins.ponding_volume||{}, rp=ins.storm_return_period||{}, fv=ins.foundation_flow_vector||{},
        ci=ins.crack_infiltration_index||{}, dr=ins.drainage_relief_score||{};
  // score header + the five actionable insights
  let html='<div class=card><div class=scorehead>'
    +'<div><h2>'+fmt(d.match.street)+'</h2>'
    +'<div class=sub>Segment '+fmt(d.match.segment_id)+' · nearest scored block '
    +fmt(d.match.distance_m)+' m from address'
    +(d.drainage.lidar_measured?' · LiDAR-measured':' · <i>topography-imputed</i>')+'</div></div>'
    +'<div class=gauge><div class=num style="color:'+col+'">'+fmt(d.curb_risk_score)+'</div>'
    +'<span class=band style="background:'+col+'">'+fmt(d.risk_band)+' RISK</span></div></div>'
    +'<h3 style="margin-top:18px">Actionable insights</h3><div class=insgrid>'
    +ic('Ponding volume', fmt(pv.cubic_feet)+' <small>cf</small>', 'catchment × depth × 0.9 runoff')
    +ic('Storm return period', fmt(rp.label),
        rp.annual_exceedance_prob!=null?('annual exceedance '+(rp.annual_exceedance_prob*100).toFixed(0)+'% · NOAA Atlas 14'):'NOAA Atlas 14 (Somerville)')
    +ic('Foundation flow vector', (fv.grade_pct==null?'—':fv.grade_pct+'%'), fv.direction||'')
    +ic('Crack infiltration', fmt(ci.index)+' <small>('+fmt(ci.score)+')</small>', (ci.n_cracks||0)+' synthetic cracks')
    +ic('Drainage relief', fmt(dr.score)+' <small>/100</small>', dr.interpretation||'')
    +ic('Recommended action', '<span style="text-transform:capitalize">'+fmt(d.recommended_action)+'</span>', '')
    +'</div>'
    +'<div class=assume>Ponding volume = catchment × ponding depth × 0.9 runoff coeff · return period via NOAA Atlas 14 (Somerville) · foundation grade ESTIMATED from LiDAR (no building footprints yet) · cracks &amp; depths synthetic (PCI-derived).</div>'
    +'</div>';

  // narrative
  if(d.narrative){
    const src=d.narrative.source||'';
    html+='<div class=card><h3>Underwriter summary'
      +(src.startsWith('claude')?'<span class=tag>Claude</span>':'<span class=tag>auto</span>')
      +'</h3><p>'+fmt(d.narrative.summary)+'</p></div>';
  }

  // 3D Drainage Studio (Autodesk APS) — embedded LiDAR model + cracks + simulator
  const xs=d.cross_section;
  if(xs&&xs.status==='ready'){
    const nm=xs.is_nearest_model?(' <span class=muted>· nearest modeled low point '+fmt(xs.for_segment)+' ('+fmt(xs.model_distance_m)+' m)</span>'):'';
    html+='<div class=card><h3>3D Drainage Studio · Autodesk APS</h3>'
      +'<p style="margin-top:-4px;font-size:14px;color:var(--mut)">LiDAR road surface + modeled ponding with '
      +'<b>toggleable, clickable cracks</b> and a live <b>rain / snow simulator</b>.'+nm+' '
      +'<a class=studio href="'+xs.viewer+'" target=_blank>Open full studio ↗</a></p>'
      +'<iframe class=studioframe src="'+xs.viewer+'" loading=lazy></iframe></div>';
  } else if(xs&&xs.viewer&&String(xs.viewer).endsWith('.svg')){
    html+='<div class=card><h3>Modeled cross-section</h3><img class=xs src="'+xs.viewer+'"></div>';
  } else {
    html+='<div class=card><h3>3D model</h3><p class=muted>No modeled low-point cross-section for this '
      +'segment — the 3D studio is generated for sag / low-point segments. Try an Avon Street address.</p></div>';
  }

  html+='<details><summary>Raw API response</summary><pre>'+JSON.stringify(d,null,2)+'</pre></details>';
  o.innerHTML=html;
}
go();
</script></body></html>"""
