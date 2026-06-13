"""Phase 4b: push the DXF cross-sections to Autodesk Platform Services (APS).

Pipeline (standard APS Model Derivative flow):
  1. 2-legged OAuth   -> bearer token (data:read/write, bucket, viewables:read)
  2. ensure an OSS bucket exists
  3. upload the .dxf object (signed-S3 upload)
  4. POST a translation job  dxf -> SVF2 (the APS Viewer format)
  5. poll the Model Derivative manifest until the translation succeeds
  6. pull the Autodesk-rendered thumbnail (proof the model translated) and
     record the base64 URN; the front-end loads it in the APS Viewer so an
     underwriter measures the 3-D section in-browser, no CAD install.

Credentials come from env: APS_CLIENT_ID / APS_CLIENT_SECRET (loaded from the
root .env). With no creds we skip translation and the API serves the local SVG
fallback, so the demo still works offline. URNs are cached to
data/processed/aps_urns.json.

Run:
    python -m curbrisk.output.aps_upload          # creds read from .env
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

from curbrisk import config as C

OUT_DIR = C.PROCESSED_DIR / "crosssections"
URN_CACHE = C.PROCESSED_DIR / "aps_urns.json"
BASE = "https://developer.api.autodesk.com"
SCOPE = "data:read data:write data:create bucket:create bucket:read viewables:read"

DEFAULT_BUCKET = "curbrisk-somerville-demo"


def _bucket_key() -> str:
    """APS bucketKey must match [-_.a-z0-9]{3,128}. Env may be empty/unset/dirty
    (note: os.environ.get(k, default) returns '' when k is set-but-empty, NOT the
    default), so coalesce, lowercase, and sanitise."""
    raw = (os.environ.get("APS_BUCKET") or DEFAULT_BUCKET).strip().lower()
    raw = re.sub(r"[^-_.a-z0-9]", "-", raw)
    return raw if 3 <= len(raw) <= 128 else DEFAULT_BUCKET


BUCKET = _bucket_key()


def _raise_with_body(r: requests.Response, what: str) -> None:
    """raise_for_status() but surface the APS JSON error body (it explains why)."""
    if r.ok:
        return
    body = r.text[:600]
    raise RuntimeError(f"APS {what} failed: HTTP {r.status_code} — {body}")


def _token(scope: str = SCOPE) -> str | None:
    cid = os.environ.get("APS_CLIENT_ID")
    sec = os.environ.get("APS_CLIENT_SECRET")
    if not (cid and sec):
        return None
    r = requests.post(
        f"{BASE}/authentication/v2/token",
        data={"grant_type": "client_credentials", "scope": scope},
        auth=(cid, sec), timeout=30,
    )
    _raise_with_body(r, "auth")
    return r.json()["access_token"]


def _ensure_bucket(tok: str) -> None:
    """Create the OSS bucket (idempotent). APS occasionally returns a transient
    400 on the first create; retry a couple of times before surfacing the body."""
    h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
    payload = {"bucketKey": BUCKET, "policyKey": "transient"}
    last = None
    for attempt in range(3):
        r = requests.post(f"{BASE}/oss/v2/buckets", headers=h, json=payload, timeout=30)
        if r.status_code in (200, 409):  # 200 = created, 409 = already exists
            return
        last = r
        print(f"  [aps] bucket create attempt {attempt + 1} -> HTTP {r.status_code}: "
              f"{r.text[:200]}")
        time.sleep(2)
    _raise_with_body(last, "bucket create")


def _upload(tok: str, dxf: Path) -> str:
    """Signed-S3 upload; returns the object URN (base64, unpadded)."""
    h = {"Authorization": f"Bearer {tok}"}
    digest = hashlib.sha256(dxf.read_bytes()).hexdigest()[:12]
    key = f"{dxf.stem}_{digest}{dxf.suffix}"
    r = requests.get(
        f"{BASE}/oss/v2/buckets/{BUCKET}/objects/{key}/signeds3upload",
        headers=h, timeout=30)
    _raise_with_body(r, f"signed-upload init ({key})")
    s = r.json()
    put = requests.put(s["urls"][0], data=dxf.read_bytes(), timeout=120)
    _raise_with_body(put, f"S3 PUT ({key})")
    r = requests.post(
        f"{BASE}/oss/v2/buckets/{BUCKET}/objects/{key}/signeds3upload",
        headers={**h, "Content-Type": "application/json"},
        json={"uploadKey": s["uploadKey"]}, timeout=30)
    _raise_with_body(r, f"signed-upload finalize ({key})")
    object_id = r.json()["objectId"]
    return base64.urlsafe_b64encode(object_id.encode()).decode().rstrip("=")


def _translate(tok: str, urn: str) -> None:
    h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json",
         "x-ads-force": "true"}
    job = {"input": {"urn": urn},
           "output": {"formats": [{"type": "svf2", "views": ["2d", "3d"]}]}}
    r = requests.post(f"{BASE}/modelderivative/v2/designdata/job",
                      headers=h, json=job, timeout=30)
    _raise_with_body(r, "translate job")


def manifest_status(tok: str, urn: str) -> dict:
    """GET the Model Derivative manifest -> {status, progress} for an URN."""
    h = {"Authorization": f"Bearer {tok}"}
    r = requests.get(
        f"{BASE}/modelderivative/v2/designdata/{urn}/manifest", headers=h, timeout=30)
    if r.status_code == 404:
        return {"status": "pending", "progress": "job not registered yet"}
    _raise_with_body(r, "manifest")
    j = r.json()
    return {"status": j.get("status"), "progress": j.get("progress")}


def _poll_manifest(tok: str, urn: str, timeout_s: int = 180) -> str:
    """Block until translation finishes; return 'success' / 'failed' / 'timeout'."""
    h = {"Authorization": f"Bearer {tok}"}
    url = f"{BASE}/modelderivative/v2/designdata/{urn}/manifest"
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        r = requests.get(url, headers=h, timeout=30)
        if r.status_code == 200:
            status = r.json().get("status")
            if status in ("success", "failed", "timeout"):
                return status
        time.sleep(4)
    return "timeout"


def _save_thumbnail(tok: str, urn: str, seg: str) -> str | None:
    """Pull the Autodesk-rendered thumbnail (PNG) for the translated model."""
    h = {"Authorization": f"Bearer {tok}"}
    r = requests.get(f"{BASE}/modelderivative/v2/designdata/{urn}/thumbnail",
                     headers=h, params={"width": 400, "height": 300}, timeout=30)
    if r.status_code == 200 and r.content:
        out = OUT_DIR / f"aps_thumb_{seg}.png"
        out.write_bytes(r.content)
        return out.name
    return None


def upload_all(segment_ids: set[str] | None = None) -> dict:
    tok = _token()
    if URN_CACHE.exists():
        try:
            urns = json.loads(URN_CACHE.read_text())
        except (OSError, json.JSONDecodeError):
            urns = {}
    else:
        urns = {}
    dxfs = sorted(OUT_DIR.glob("*.dxf"))
    if segment_ids:
        dxfs = [d for d in dxfs if d.stem.replace("xsection_", "") in segment_ids]
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
        status = _poll_manifest(tok, urn)
        thumb = _save_thumbnail(tok, urn, seg) if status == "success" else None
        urns[seg] = {
            "urn": urn,
            "status": "ready" if status == "success" else status,
            # served by the API's APS Viewer page; SVG remains the offline fallback
            "viewer": f"/viewer/{seg}" if status == "success" else f"/crosssection/{seg}.svg",
            "thumbnail": f"/crosssection/{thumb}" if thumb else None,
        }
        # Persist each result so a slow remote translation or interrupted run
        # never discards models that already completed successfully.
        URN_CACHE.write_text(json.dumps(urns, indent=2))
        print(f"  {seg}: upload + SVF2 translate -> {status}"
              + (f", thumbnail {thumb}" if thumb else ""))
    URN_CACHE.write_text(json.dumps(urns, indent=2))
    ok = sum(1 for v in urns.values() if v["status"] == "ready")
    print(f"\nAPS: {ok}/{len(urns)} models translated and viewable.")
    return urns


if __name__ == "__main__":
    requested = set(sys.argv[1:]) or None
    out = upload_all(requested)
    print(json.dumps(out, indent=2))

    # Confirm at least one URN is a real, translating APS derivative (not the SVG
    # fallback): poll its Model Derivative manifest.
    real = {s: v for s, v in out.items() if v.get("urn")}
    if not real:
        print("\nNo APS URNs produced (SVG fallback path). APS not exercised.")
    else:
        tok = _token()
        seg, info = next(iter(real.items()))
        urn = info["urn"]
        print(f"\nVerifying APS translation for {seg} (urn={urn[:24]}...):")
        st = {}
        for i in range(10):
            st = manifest_status(tok, urn)
            print(f"  poll {i + 1}: status={st.get('status')} progress={st.get('progress')}")
            if st.get("status") in ("success", "inprogress", "failed"):
                break
            time.sleep(3)
        ok = st.get("status") in ("success", "inprogress")
        print(f"\nAPS URN {'CONFIRMED translating/complete' if ok else 'NOT confirmed'} "
              f"(status={st.get('status')}).")
        print(f"Viewer: {info['viewer']}")
