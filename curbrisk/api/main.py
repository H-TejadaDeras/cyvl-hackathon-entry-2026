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

app = FastAPI(title="CurbRisk API", version="0.1.0")

XS_DIR = C.PROCESSED_DIR / "crosssections"
URN_CACHE = C.PROCESSED_DIR / "aps_urns.json"
IMAGERY_INDEX = C.PROCESSED_DIR / "imagery_index.json"


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
):
    has_coords = lat is not None or lon is not None
    if has_coords and (lat is None or lon is None):
        raise HTTPException(422, "lat and lon must be provided together")
    if not address and not has_coords:
        raise HTTPException(422, "provide an address or lat/lon")
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
    report = {
        "query": {"address": address, "lat": lat, "lon": lon},
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
        "hydraulic_assumptions": json.loads(seg["hydraulic_assumptions"]),
        "narrative": _summary_for(sid),
        "cross_section": _viewer_for(sid),
        "imagery": _imagery_for(sid),
    }
    return JSONResponse(report)


@app.get("/crosssection/{segment_id}.svg")
def crosssection(segment_id: str):
    p = XS_DIR / f"xsection_{segment_id}.svg"
    if not p.exists():
        raise HTTPException(404, "no cross-section for this segment")
    return FileResponse(p, media_type="image/svg+xml")


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
<p class=hint>Enter any address inside the demo footprint. Returns a CurbRisk score, modeled
ponding cross-section, nearby 311 flood history, and street-level imagery.</p>
<div id=out></div>
</div>
<script>
const COL={High:'#d9352a',Moderate:'#e8a33d',Low:'#2e8b57'};
const fmt=v=>(v===null||v===undefined)?'—':v;
function bar(label,pts,max,color){
  const pct=Math.max(0,Math.min(100,(pts/max)*100));
  return `<div class=bar><span>${label}</span>`
    +`<span class=track><span class=fill style="width:${pct}%;background:${color}"></span></span>`
    +`<span>${pts}<small class=muted>/${max}</small></span></div>`;
}
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
  const c=d.components||{};
  // score + bands
  let html='<div class=card><div class=scorehead>'
    +'<div><h2>'+fmt(d.match.street)+'</h2>'
    +'<div class=sub>Segment '+fmt(d.match.segment_id)+' · nearest scored block '
    +fmt(d.match.distance_m)+' m from address'
    +(d.drainage.lidar_measured?' · LiDAR-measured':' · <i>topography-imputed</i>')+'</div></div>'
    +'<div class=gauge><div class=num style="color:'+col+'">'+fmt(d.curb_risk_score)+'</div>'
    +'<span class=band style="background:'+col+'">'+fmt(d.risk_band)+' RISK</span></div></div>'
    +'<div class=bars>'
    +bar('Topography',c.topo_pts,40,'#1763d6')
    +bar('Pavement',c.pavement_pts,30,'#7b54c4')
    +bar('Drainage gap',c.basin_pts,20,'#2c9c8f')
    +bar('311 reports',c.complaint_pts,10,'#d4a72c')
    +'</div>'
    +'<div class=facts>'
    +'<div class=fact><div class=k>Modeled ponding</div><div class=v>'
      +fmt(d.drainage.modeled_ponding_depth_in)+' <small>in @ '+fmt(d.drainage.rain_event_in)+'" storm</small></div></div>'
    +'<div class=fact><div class=k>Catchment</div><div class=v>'+fmt(d.drainage.catchment_sqft)+' <small>sqft</small></div></div>'
    +'<div class=fact><div class=k>Nearest drain</div><div class=v>'+fmt(d.drainage.nearest_drain_m)+' <small>m</small></div></div>'
    +'<div class=fact><div class=k>Pavement PCI</div><div class=v>'+fmt(d.pavement.pci)+'</div></div>'
    +'<div class=fact><div class=k>311 flood reports</div><div class=v>'+fmt(d.complaints_311_nearby)+' <small>within 100 m</small></div></div>'
    +'<div class=fact><div class=k>Recommended action</div><div class=v style="font-size:16px;text-transform:capitalize">'+fmt(d.recommended_action)+'</div></div>'
    +'</div>';
  if(d.hydraulic_assumptions)
    html+='<div class=assume><b>Assumptions:</b> '+d.hydraulic_assumptions.model
      +' Runoff coeff '+d.hydraulic_assumptions.runoff_coefficient+'. '+d.hydraulic_assumptions.vertical_accuracy+'</div>';
  html+='</div>';

  // narrative + vision
  if(d.narrative){
    const src=d.narrative.source||'';
    html+='<div class=card><h3>Underwriter summary'
      +(src.startsWith('claude')?'<span class=tag>Claude'+(src.includes('vision')?' + vision':'')+'</span>':'<span class=tag>auto</span>')
      +'</h3><p>'+fmt(d.narrative.summary)+'</p>';
    if(d.narrative.vision)
      html+='<div class=vision><b>Field image read:</b> '+d.narrative.vision+'</div>';
    html+='</div>';
  }

  // cross-section
  const xs=d.cross_section;
  if(xs&&xs.viewer){
    html+='<div class=card><h3>Modeled cross-section at low point'
      +(xs.status==='svg_fallback'?'':' <span class=tag>APS Viewer</span>')+'</h3>';
    if(xs.viewer.endsWith('.svg')) html+='<img class=xs src="'+xs.viewer+'">';
    else html+='<p><a href="'+xs.viewer+'" target=_blank>Open in Autodesk APS Viewer ↗</a></p>';
    html+='</div>';
  }

  // imagery
  const im=d.imagery;
  if(im&&im.plain_images&&im.plain_images.length){
    html+='<div class=card><h3>Cyvl street-level imagery</h3><div class=thumbs>';
    im.plain_images.forEach(p=>{
      html+='<a href="'+p.url+'" target=_blank><img loading=lazy src="'+p.url+'" title="'+p.dist_m+' m"></a>';
    });
    html+='</div>';
    if(im.panoramic&&im.panoramic.viewer_url)
      html+='<p style="margin-top:12px"><a href="'+im.panoramic.viewer_url+'" target=_blank>Open 360° panorama ↗</a></p>';
    html+='</div>';
  }

  html+='<details><summary>Raw API response</summary><pre>'+JSON.stringify(d,null,2)+'</pre></details>';
  o.innerHTML=html;
}
go();
</script></body></html>"""
