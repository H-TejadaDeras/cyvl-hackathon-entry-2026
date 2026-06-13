"""Phase 5: the CurbRisk API — query by address, get a drainage risk report.

Everything is pre-computed (scores.db + cross-sections), so a request is just:
geocode -> nearest segment in SQLite -> assemble JSON. Designed to answer in
well under 10 seconds (typically <1s after the first geocode).

Endpoints:
  GET /risk?address=...   -> full CurbRisk report for the nearest scored segment
  GET /crosssection/{id}.svg -> the rendered cross-section (APS fallback / demo)
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
def risk(address: str = Query(..., description="Street address in/near Somerville, MA")):
    geo = _geocode(address)
    if geo is None:
        raise HTTPException(404, "could not geocode address")
    lat, lon = geo
    seg, dist = _nearest_segment(lat, lon)
    if seg is None:
        raise HTTPException(503, "risk dataset not built — run the pipeline first")

    sid = seg["segment_id"]
    report = {
        "query": {"address": address, "lat": lat, "lon": lon},
        "match": {"segment_id": sid, "street": seg["street"],
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
        "cross_section": _viewer_for(sid),
    }
    return JSONResponse(report)


@app.get("/crosssection/{segment_id}.svg")
def crosssection(segment_id: str):
    p = XS_DIR / f"xsection_{segment_id}.svg"
    if not p.exists():
        raise HTTPException(404, "no cross-section for this segment")
    return FileResponse(p, media_type="image/svg+xml")


@app.get("/", response_class=HTMLResponse)
def home():
    return """<!doctype html><html><head><meta charset=utf-8>
<title>CurbRisk — Somerville drainage risk</title>
<style>body{font:16px system-ui;max-width:760px;margin:40px auto;color:#222}
input{padding:10px;width:70%;font-size:16px}button{padding:10px 16px;font-size:16px;cursor:pointer}
#out{margin-top:24px}.band{display:inline-block;padding:4px 12px;border-radius:6px;color:#fff;font-weight:700}
pre{background:#f4f4f0;padding:14px;border-radius:8px;overflow:auto}img{max-width:100%;border:1px solid #ddd;border-radius:8px}</style>
</head><body>
<h1>CurbRisk</h1><p>Drainage risk by address — Somerville, MA demo (Avon St corridor).</p>
<input id=a placeholder="e.g. 20 Avon Street, Somerville MA" value="Avon Street, Somerville MA">
<button onclick=go()>Get risk</button>
<div id=out></div>
<script>
async function go(){
  const a=document.getElementById('a').value;
  const o=document.getElementById('out'); o.innerHTML='Scoring…';
  const r=await fetch('/risk?address='+encodeURIComponent(a));
  if(!r.ok){o.innerHTML='Error: '+r.status;return;}
  const d=await r.json();
  const col={High:'#d9352a',Moderate:'#e8a33d',Low:'#2e8b57'}[d.risk_band]||'#888';
  let xs=''; if(d.cross_section&&d.cross_section.viewer&&d.cross_section.viewer.endsWith('.svg'))
    xs='<h3>Cross-section</h3><img src="'+d.cross_section.viewer+'">';
  o.innerHTML='<h2>'+d.match.street+' — <span class=band style="background:'+col+'">'
    +d.risk_band+' · CurbRisk '+d.curb_risk_score+'</span></h2>'
    +'<p>Modeled ponding <b>'+d.drainage.modeled_ponding_depth_in+' in</b> @ '
    +d.drainage.rain_event_in+'" storm · PCI '+d.pavement.pci+' · '
    +d.complaints_311_nearby+' nearby 311 flood reports'
    +(d.drainage.lidar_measured?'':' · <i>LiDAR not in tile — imputed</i>')+'</p>'
    +xs+'<pre>'+JSON.stringify(d,null,2)+'</pre>';
}
go();
</script></body></html>"""
