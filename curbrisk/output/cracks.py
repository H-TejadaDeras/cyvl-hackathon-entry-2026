"""Phase 6: synthetic pavement cracks for the 3-D model + infiltration insight.

REALITY CHECK: the Cyvl deliverable has no per-crack geometry — only one PCI
`score` per ~30-ft segment. So cracks here are SYNTHETIC: generated
deterministically (seeded by segment id, so they are stable/reproducible and
editable) with counts and widths scaled inversely to PCI, clustered toward the
modeled low point where water sits. Depth is an explicit placeholder, meant to be
overwritten once real distress vectors / point-cloud width-depth arrive.

Cracks are parameterised in the SAME local model frame the cross-section uses:
  along_m  : signed distance along the street from the sag (sag = 0)
  offset_m : transverse offset from the centreline

Writes data/processed/cracks_index.json keyed by segment_id.

Run:
    python -m curbrisk.output.cracks
"""
from __future__ import annotations

import json
import hashlib
import random

import geopandas as gpd

from curbrisk import config as C

CRACKS_OUT = C.PROCESSED_DIR / "cracks_index.json"

ALONG_HALF_M = 9.0      # matches crosssection ALONG_LEN_M / 2
OFFSET_HALF_M = 4.0     # matches crosssection HALF_WIDTH_M


def _seed(segment_id: str) -> int:
    return int(hashlib.md5(segment_id.encode()).hexdigest()[:8], 16)


def _severity(width_mm: float) -> str:
    return "High" if width_mm >= 12 else "Medium" if width_mm >= 5 else "Low"


def generate_for_segment(segment_id: str, pci: float | None) -> list[dict]:
    """Deterministic synthetic cracks for one segment, scaled by PCI."""
    pci = 85.0 if pci is None else float(pci)
    rng = random.Random(_seed(segment_id))
    n = int(max(3, min(15, round((100.0 - pci) / 5.0) + 3)))
    cracks = []
    for i in range(n):
        # cluster toward the sag (along ~ 0): triangular distribution peaked at 0
        along = rng.triangular(-ALONG_HALF_M, ALONG_HALF_M, 0.0)
        offset = rng.uniform(-OFFSET_HALF_M, OFFSET_HALF_M)
        # width widens as PCI drops; depth is a (labelled) placeholder
        width_mm = round(rng.uniform(2.0, 6.0 + (100.0 - pci) / 2.0), 1)
        depth_mm = round(rng.uniform(5.0, max(8.0, width_mm * 2.5)), 1)
        length_m = round(rng.uniform(0.3, 2.0), 2)
        transverse = rng.random() < 0.4   # 40% run across the lane, else longitudinal
        cracks.append({
            "id": f"C{i + 1:02d}",
            "along_m": round(along, 2),
            "offset_m": round(offset, 2),
            "length_m": length_m,
            "width_mm": width_mm,
            "depth_mm": depth_mm,               # placeholder; editable in the UI
            "depth_is_synthetic": True,
            "orientation": "transverse" if transverse else "longitudinal",
            "severity": _severity(width_mm),
            "dist_to_low_m": round(abs(along), 2),
        })
    # strongest/most relevant first
    cracks.sort(key=lambda c: (c["dist_to_low_m"], -c["width_mm"]))
    return cracks


def build_index() -> dict:
    """Generate cracks for every segment that has a modeled low point (= a 3-D
    cross-section). PCI comes from the scored segments."""
    low = gpd.read_file(C.LOWPOINTS_OUT)
    scores = gpd.read_file(C.SCORES_OUT)
    pci_by_seg = {r["segment_id"]: r.get("pci") for _, r in scores.iterrows()}

    index = {}
    seg_ids = sorted(set(str(s) for s in low["segment_id"]))
    for sid in seg_ids:
        index[sid] = {
            "segment_id": sid,
            "pci": pci_by_seg.get(sid),
            "cracks": generate_for_segment(sid, pci_by_seg.get(sid)),
        }
    CRACKS_OUT.write_text(json.dumps(index, indent=2))
    total = sum(len(v["cracks"]) for v in index.values())
    print(f"Wrote {CRACKS_OUT}")
    print(json.dumps({
        "segments": len(index),
        "total_cracks": total,
        "by_segment": {k: len(v["cracks"]) for k, v in index.items()},
    }, indent=2))
    return index


if __name__ == "__main__":
    build_index()
