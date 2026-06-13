"""Phase 4a: generate a measurable road cross-section per flagged low point.

For a low point we sample a transverse ground profile (perpendicular to the
street) and the longitudinal profile from the LiDAR, then emit a DXF showing:

  * ROAD_PROFILE  — the bare-earth cross-section polyline (the road dip);
  * WATER_SURFACE — a horizontal line at the modeled ponding depth, with a
    hatched band beneath it (the standing water at a 2-inch storm);
  * ANNOT         — dimensions + text: ponding depth, PCI, CurbRisk score.

The DXF is the exchange format Autodesk APS ingests; aps_upload.py translates it
to an APS Viewer URN. We also render a lightweight SVG so the deliverable is
viewable even without APS credentials (and as the demo fallback).

Run:
    python -m curbrisk.output.crosssection
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import geopandas as gpd
import ezdxf

from curbrisk import config as C
from curbrisk.ingest.lidar_ground import get_sampler

OUT_DIR = C.PROCESSED_DIR / "crosssections"
OUT_DIR.mkdir(exist_ok=True)
HALF_WIDTH_M = 9.0
VEXAG = 3.0   # vertical exaggeration for legibility


def _bearing_at(line, dist_norm=0.5):
    a = line.interpolate(max(dist_norm - 0.02, 0), normalized=True)
    b = line.interpolate(min(dist_norm + 0.02, 1), normalized=True)
    return math.atan2(b.y - a.y, b.x - a.x)


def _transect_for_lowpoint(sampler, low_row, seg):
    """Sample a transverse ground profile at the low point."""
    pt = low_row.geometry
    # find the owning street segment to get bearing
    sub = seg[seg["street"] == low_row["street"]]
    line = sub.geometry.iloc[int(sub.geometry.distance(pt).values.argmin())]
    bearing = _bearing_at(line, line.project(pt, normalized=True))
    offs, elev = sampler.transect(pt, bearing, half_width_m=HALF_WIDTH_M, step_m=0.2)
    ok = np.isfinite(elev)
    if ok.sum() < 4:
        return None
    return offs[ok], elev[ok]


def build_dxf(low_row, offs, elev, pci, curb_risk) -> Path:
    z0 = float(np.min(elev))
    rel = (elev - z0) * VEXAG           # ground relative to local low, exaggerated
    depth_in = float(low_row["ponding_depth_in"])
    water_rel = (depth_in / 12.0 / 3.28084)  # inches→ft→m
    water_y = water_rel * VEXAG

    doc = ezdxf.new("R2010")
    doc.units = ezdxf.units.M
    msp = doc.modelspace()
    for name, color in [("ROAD_PROFILE", 8), ("WATER_SURFACE", 5),
                        ("WATER_FILL", 4), ("ANNOT", 2), ("PCI", 1)]:
        doc.layers.add(name, color=color)

    # road profile polyline
    pts = list(zip(offs, rel))
    msp.add_lwpolyline(pts, dxfattribs={"layer": "ROAD_PROFILE"})

    # water: horizontal surface clipped to where ground is below water level
    left, right = float(offs.min()), float(offs.max())
    msp.add_line((left, water_y), (right, water_y), dxfattribs={"layer": "WATER_SURFACE"})
    # hatched water body between ground and water surface where submerged
    boundary = [(left, water_y)]
    for o, g in zip(offs, rel):
        boundary.append((o, min(g, water_y)))
    boundary.append((right, water_y))
    hatch = msp.add_hatch(color=4, dxfattribs={"layer": "WATER_FILL"})
    hatch.set_pattern_fill("ANSI31", scale=0.25)
    hatch.paths.add_polyline_path(boundary, is_closed=True)

    # annotations
    msp.add_text(
        f"{low_row['street']}  |  CurbRisk {curb_risk}  |  PCI {pci}",
        dxfattribs={"layer": "ANNOT", "height": 0.4},
    ).set_placement((left, water_y + 1.2))
    msp.add_text(
        f"Ponding depth @ {C.RAIN_EVENT_IN}\" storm: {depth_in:.1f} in",
        dxfattribs={"layer": "ANNOT", "height": 0.35},
    ).set_placement((left, water_y + 0.6))
    msp.add_text(
        f"Catchment: {low_row['catchment_sqft']:.0f} sqft  "
        f"Volume: {low_row['ponding_volume_cf']:.0f} cf",
        dxfattribs={"layer": "ANNOT", "height": 0.3},
    ).set_placement((left, water_y + 0.1))

    path = OUT_DIR / f"xsection_{low_row['segment_id']}.dxf"
    doc.saveas(path)
    _render_svg(path.with_suffix(".svg"), offs, rel, water_y, low_row, pci, curb_risk)
    return path


def _render_svg(path, offs, rel, water_y, low_row, pci, curb_risk):
    """Standalone SVG so the cross-section is viewable without any CAD/APS."""
    W, H, pad = 720, 360, 40
    xmin, xmax = float(offs.min()), float(offs.max())
    ymin, ymax = float(min(rel.min(), 0)), float(max(rel.max(), water_y) + 2.0)

    def sx(x): return pad + (x - xmin) / (xmax - xmin) * (W - 2 * pad)
    def sy(y): return (H - pad) - (y - ymin) / (ymax - ymin) * (H - 2 * pad)

    ground = " ".join(f"{sx(x):.1f},{sy(y):.1f}" for x, y in zip(offs, rel))
    water_poly = [f"{sx(xmin):.1f},{sy(water_y):.1f}"]
    water_poly += [f"{sx(x):.1f},{sy(min(y, water_y)):.1f}" for x, y in zip(offs, rel)]
    water_poly += [f"{sx(xmax):.1f},{sy(water_y):.1f}"]
    band = {"High": "#d9352a", "Moderate": "#e8a33d", "Low": "#2e8b57"}.get(
        low_row.get("risk_band", "Moderate"), "#888")
    svg = f"""<svg xmlns='http://www.w3.org/2000/svg' width='{W}' height='{H}' font-family='system-ui'>
<rect width='{W}' height='{H}' fill='#f7f7f4'/>
<polygon points='{' '.join(water_poly)}' fill='#4a90d9' fill-opacity='0.55'/>
<polyline points='{ground}' fill='none' stroke='#444' stroke-width='2.5'/>
<line x1='{sx(xmin):.1f}' y1='{sy(water_y):.1f}' x2='{sx(xmax):.1f}' y2='{sy(water_y):.1f}' stroke='#1f6fb2' stroke-dasharray='6 4' stroke-width='2'/>
<text x='{pad}' y='28' font-size='18' font-weight='700'>{low_row['street']} — cross-section at low point</text>
<text x='{pad}' y='{H-14}' font-size='13' fill='#333'>Ponding {low_row['ponding_depth_in']:.1f} in @ {C.RAIN_EVENT_IN}" storm · catchment {low_row['catchment_sqft']:.0f} sqft · PCI {pci}</text>
<rect x='{W-150}' y='14' width='136' height='30' rx='6' fill='{band}'/>
<text x='{W-82}' y='34' font-size='15' fill='#fff' text-anchor='middle' font-weight='700'>CurbRisk {curb_risk}</text>
</svg>"""
    Path(path).write_text(svg)


def main() -> None:
    seg = gpd.read_file(C.PROCESSED_DIR / "segments_elev.geojson").to_crs(C.UTM19N)
    low = gpd.read_file(C.LOWPOINTS_OUT).to_crs(C.UTM19N)
    scores = gpd.read_file(C.SCORES_OUT)
    sampler = get_sampler()
    by_seg = {r["segment_id"]: r for _, r in scores.iterrows()}

    made = 0
    for _, lr in low.iterrows():
        t = _transect_for_lowpoint(sampler, lr, seg)
        if t is None:
            continue
        sc = by_seg.get(lr["segment_id"], {})
        pci = sc.get("pci", "n/a")
        risk = sc.get("curb_risk", "n/a")
        lr = lr.copy()
        lr["risk_band"] = sc.get("risk_band", "Moderate")
        p = build_dxf(lr, *t, pci, risk)
        made += 1
        print(f"  {lr['segment_id']}: {p.name} (+ .svg)")
    print(f"\nGenerated {made} cross-sections in {OUT_DIR}")


if __name__ == "__main__":
    main()
