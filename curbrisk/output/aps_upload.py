"""Phase 4b: push the DXF cross-sections to Autodesk Platform Services (APS).

Pipeline (standard APS Model Derivative flow):
  1. 2-legged OAuth   -> bearer token (data:read data:write bucket:create)
  2. ensure an OSS bucket exists
  3. upload the .dxf object (signed-S3 upload)
  4. POST a translation job  dxf -> SVF2 (the APS Viewer format)
  5. record the base64 URN; the front-end loads it in the APS Viewer so an
     underwriter measures the section in-browser, no CAD install.

Credentials come from env: APS_CLIENT_ID / APS_CLIENT_SECRET. With no creds we
skip translation and the API serves the local SVG fallback, so the demo still
works offline. URNs are cached to data/processed/aps_urns.json.

Run:
    APS_CLIENT_ID=... APS_CLIENT_SECRET=... python -m curbrisk.output.aps_upload
"""
from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path

import requests

from curbrisk import config as C

OUT_DIR = C.PROCESSED_DIR / "crosssections"
URN_CACHE = C.PROCESSED_DIR / "aps_urns.json"
BUCKET = os.environ.get("APS_BUCKET", "curbrisk-somerville-demo")
BASE = "https://developer.api.autodesk.com"


def _token() -> str | None:
    cid = os.environ.get("APS_CLIENT_ID")
    sec = os.environ.get("APS_CLIENT_SECRET")
    if not (cid and sec):
        return None
    r = requests.post(
        f"{BASE}/authentication/v2/token",
        data={"grant_type": "client_credentials",
              "scope": "data:read data:write data:create bucket:create bucket:read"},
        auth=(cid, sec), timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def _ensure_bucket(tok: str) -> None:
    h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
    r = requests.post(f"{BASE}/oss/v2/buckets", headers=h,
                      json={"bucketKey": BUCKET, "policyKey": "transient"}, timeout=30)
    if r.status_code not in (200, 409):  # 409 = already exists
        r.raise_for_status()


def _upload(tok: str, dxf: Path) -> str:
    """Signed-S3 upload; returns the object URN (base64, unpadded)."""
    h = {"Authorization": f"Bearer {tok}"}
    key = dxf.name
    s = requests.get(
        f"{BASE}/oss/v2/buckets/{BUCKET}/objects/{key}/signeds3upload",
        headers=h, timeout=30).json()
    requests.put(s["urls"][0], data=dxf.read_bytes(), timeout=120).raise_for_status()
    fin = requests.post(
        f"{BASE}/oss/v2/buckets/{BUCKET}/objects/{key}/signeds3upload",
        headers={**h, "Content-Type": "application/json"},
        json={"uploadKey": s["uploadKey"]}, timeout=30).json()
    object_id = fin["objectId"]
    return base64.urlsafe_b64encode(object_id.encode()).decode().rstrip("=")


def _translate(tok: str, urn: str) -> None:
    h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
    job = {"input": {"urn": urn},
           "output": {"formats": [{"type": "svf2", "views": ["2d", "3d"]}]}}
    requests.post(f"{BASE}/modelderivative/v2/designdata/job",
                  headers=h, json=job, timeout=30).raise_for_status()


def upload_all() -> dict:
    tok = _token()
    urns = {}
    dxfs = sorted(OUT_DIR.glob("*.dxf"))
    if tok is None:
        print("No APS_CLIENT_ID/SECRET set — skipping APS translation.")
        print("Serving local SVG fallbacks; set creds to enable the APS Viewer.")
        for d in dxfs:
            seg = d.stem.replace("xsection_", "")
            urns[seg] = {"urn": None, "viewer": f"/crosssection/{seg}.svg",
                         "status": "svg_fallback"}
        URN_CACHE.write_text(json.dumps(urns, indent=2))
        return urns

    _ensure_bucket(tok)
    for d in dxfs:
        seg = d.stem.replace("xsection_", "")
        urn = _upload(tok, d)
        _translate(tok, urn)
        urns[seg] = {
            "urn": urn, "status": "translating",
            "viewer": f"https://developer.api.autodesk.com/derivativeservice/v2/viewer?urn={urn}",
        }
        print(f"  {seg}: uploaded + translation queued")
        time.sleep(0.3)
    URN_CACHE.write_text(json.dumps(urns, indent=2))
    return urns


if __name__ == "__main__":
    out = upload_all()
    print(json.dumps(out, indent=2))
