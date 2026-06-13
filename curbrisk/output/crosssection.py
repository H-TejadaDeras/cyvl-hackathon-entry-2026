"""Phase 4a: generate a measurable road cross-section per flagged low point.

Two artifacts are produced per low point:

  * a **3-D DXF** of the road sag and the modeled standing water. The
    **longitudinal road profile is LiDAR-measured** — the same low-percentile
    centreline ground profile the topo analysis validated — extruded across the
    carriageway width to a 3-D surface. The cross-street direction is a uniform
    extrusion (labelled), because the raw cloud away from the centreline is full
    of parked cars and kerbside clutter and is not a reliable bare-earth signal.
    ROAD is the bare-earth mesh; WATER is the pond surface at the modeled
    2-inch-storm ponding depth, filling the sag. This is the file Autodesk APS
    translates to SVF2 and renders as a 3-D, measurable model in the APS Viewer
    (no CAD install).
  * a lightweight **2-D SVG** longitudinal section so the deliverable is
    viewable with no APS credentials and as the demo fallback.

Vertical relief on a road is small (centimetres), so Z is exaggerated for
legibility in the 3-D model; the exaggeration factor is annotated and all depth
labels report true inches.

Run:
    python -m curbrisk.output.crosssection
"""
from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

import numpy as np
import geopandas as gpd
import ezdxf
from ezdxf.render import MeshBuilder
from shapely.ops import linemerge, unary_union

from curbrisk import config as C
from curbrisk.ingest.lidar_ground import get_sampler

OUT_DIR = C.PROCESSED_DIR / "crosssections"
OUT_DIR.mkdir(exist_ok=True)
CRACKS_INDEX = C.PROCESSED_DIR / "cracks_index.json"

# Synthetic crack rendering. Real crack openings are millimetres — far too small
# to see next to a road — so width/depth are visually EXAGGERATED in the model
# (the click-through panel reports the true synthetic mm values). Colour = severity.
CRACK_COLOR = 250          # dark charcoal, readable as a fissure on grey pavement
CRACK_WIDTH_VIS = 0.012    # visual metres per mm; true width remains in the API

HALF_WIDTH_M = 4.0     # carriageway half-width (extruded transverse extent)
ALONG_LEN_M = 18.0     # longitudinal extent of the measured profile (centred on sag)
ALONG_STEP_M = 1.5     # along-street station spacing
XSTEP_M = 0.8          # transverse mesh spacing
PROFILE_RADIUS_M = 3.0  # ground-search radius per longitudinal station (matches topo)
VEXAG = 2.0            # vertical exaggeration (labelled); depth labels stay true
M_PER_IN = 1.0 / 12.0 / 3.28084   # inches -> metres


def _street_line(low_row, seg):
    """Merge the low point's street into one centreline; return the component
    nearest the sag (UTM 19N)."""
    pt = low_row.geometry
    sub = seg[seg["street"] == low_row["street"]]
    if sub.empty:
        sub = seg
    merged = linemerge(unary_union(list(sub.geometry)))
    if merged.geom_type == "MultiLineString":
        merged = min(merged.geoms, key=lambda g: g.distance(pt))
    return merged


def _surface_grid(sampler, low_row, seg):
    """Build the road surface around the low point.

    The longitudinal profile (along the centreline) is LiDAR-measured via the
    low-percentile ground sampler; it is extruded across the carriageway width.

    Returns (alongs, offs, Z) where alongs[i] is the signed distance along the
    street from the sag, offs[j] the transverse offset from the centreline, and
    Z[i, j] the bare-earth elevation (m; NaN where the profile has no LiDAR).
    """
    pt = low_row.geometry
    line = _street_line(low_row, seg)
    s0 = line.project(pt)                                  # sag position along the line
    half = ALONG_LEN_M / 2
    stations = np.arange(max(s0 - half, 0.0),
                         min(s0 + half, line.length) + ALONG_STEP_M, ALONG_STEP_M)
    stations = stations[stations <= line.length]
    alongs = stations - s0                                 # centre the sag at 0

    # measured longitudinal profile (smoothed by the percentile sampler's radius)
    prof = np.array([sampler.elevation(*line.interpolate(s).coords[0],
                                       radius_m=PROFILE_RADIUS_M) for s in stations])
    # fill any isolated NaN stations by interpolation so the mesh stays continuous
    if np.isfinite(prof).sum() >= 2:
        idx = np.arange(len(prof))
        ok = np.isfinite(prof)
        prof = np.interp(idx, idx[ok], prof[ok])

    offs = np.arange(-HALF_WIDTH_M, HALF_WIDTH_M + XSTEP_M, XSTEP_M)
    # uniform transverse extrusion of the measured longitudinal profile
    Z = np.repeat(prof[:, None], len(offs), axis=1)
    return alongs, offs, Z


def _bowl_bounds(prof, sag_i, sag_z, spill_m):
    """Stations spanned by the pond: walk out from the sag until the profile
    rises past the overflow crest (sag + spill) or turns back down (a divide)."""
    n = len(prof)
    lo = sag_i
    while lo > 0 and prof[lo - 1] <= sag_z + spill_m and prof[lo - 1] >= prof[lo]:
        lo -= 1
    hi = sag_i
    while hi < n - 1 and prof[hi + 1] <= sag_z + spill_m and prof[hi + 1] >= prof[hi]:
        hi += 1
    return lo, hi


def _surface_z(alongs, offs, Z, z_ref, a, o):
    """Exaggerated surface height (model units) at along=a, offset=o (nearest cell)."""
    i = int(np.argmin(np.abs(alongs - a)))
    j = int(np.argmin(np.abs(offs - o)))
    z = Z[i, j]
    if not np.isfinite(z):
        col = Z[i, :]
        z = float(np.nanmin(col)) if np.isfinite(col).any() else z_ref
    return (float(z) - z_ref) * VEXAG


def _add_cracks(msp, doc, alongs, offs, Z, z_ref, cracks) -> None:
    """Draw each synthetic crack as its own named layer object (CRACK_<id>) so it
    is individually selectable + toggleable in the APS Viewer.

    Each crack is a dark, irregular ribbon draped just above the road. This reads
    as an actual pavement fissure in APS; the previous rectangular severity bars
    looked like CAD markers and could disappear against the shaded road."""
    amin, amax = float(alongs.min()), float(alongs.max())
    omin, omax = float(offs.min()), float(offs.max())
    for ck in cracks:
        a0 = min(max(float(ck["along_m"]), amin), amax)
        o0 = min(max(float(ck["offset_m"]), omin), omax)
        length = max(0.45, float(ck["length_m"]))
        width = max(0.10, float(ck["width_mm"]) * CRACK_WIDTH_VIS)
        transverse = ck.get("orientation") == "transverse"
        rng = random.Random(f"{ck['id']}:{a0}:{o0}")
        n = max(7, int(length / 0.18))
        centers = []
        for i in range(n):
            t = i / (n - 1) - 0.5
            jitter = 0.0 if i in (0, n - 1) else rng.uniform(-width * 0.9, width * 0.9)
            a = a0 + (jitter if transverse else t * length)
            o = o0 + (t * length if transverse else jitter)
            a = min(max(a, amin), amax)
            o = min(max(o, omin), omax)
            centers.append((a, o, _surface_z(alongs, offs, Z, z_ref, a, o) + 0.025))

        layer = f"CRACK_{ck['id']}"
        if layer not in doc.layers:
            doc.layers.add(layer, color=CRACK_COLOR)
        m = MeshBuilder()
        for i in range(len(centers) - 1):
            a1, o1, z1 = centers[i]
            a2, o2, z2 = centers[i + 1]
            da, do = a2 - a1, o2 - o1
            mag = math.hypot(da, do) or 1.0
            pa, po = -do / mag * width / 2, da / mag * width / 2
            m.add_face([
                (a1 + pa, o1 + po, z1), (a2 + pa, o2 + po, z2),
                (a2 - pa, o2 - po, z2), (a1 - pa, o1 - po, z1),
            ])
        m.render_mesh(msp, dxfattribs={"layer": layer})


def build_dxf(low_row, alongs, offs, Z, pci, curb_risk, cracks=None) -> Path:
    """Write a 3-D DXF: bare-earth road mesh + modeled pond surface.

    The pond is anchored to the *detected* sag (the topo low point at the centre
    of the window), not the lowest cell in the window — the street can keep
    descending past a drainage divide, and water collected at the sag does not
    fill that downslope. Its extent is clipped to the local bowl using the
    overflow (spill) depth topo measured.
    """
    prof = Z[:, Z.shape[1] // 2]                 # measured centreline profile
    depth_in = float(low_row["ponding_depth_in"])
    spill_m = float(low_row.get("spill_depth_m", depth_in * M_PER_IN) or depth_in * M_PER_IN)

    # detected sag = local minimum near the window centre (along == 0)
    centre = int(np.argmin(np.abs(alongs)))
    win = range(max(centre - 2, 0), min(centre + 3, len(prof)))
    sag_i = min(win, key=lambda i: prof[i])
    z_ref = float(prof[sag_i])                   # sag floor elevation
    lo, hi = _bowl_bounds(prof, sag_i, z_ref, spill_m)
    water_local = depth_in * M_PER_IN * VEXAG    # pond surface above the sag floor

    doc = ezdxf.new("R2010")
    doc.units = ezdxf.units.M
    msp = doc.modelspace()
    doc.layers.add("ROAD", color=8)        # bare-earth surface (grey)
    doc.layers.add("WATER", color=5)       # modeled standing water (blue)
    doc.layers.add("ANNOT", color=2)       # labels (yellow)

    def zr(i, j):
        return (Z[i, j] - z_ref) * VEXAG

    road = MeshBuilder()
    water = MeshBuilder()
    na, no = len(alongs), len(offs)
    for i in range(na - 1):
        for j in range(no - 1):
            quad = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)]
            if not all(np.isfinite(Z[a, b]) for a, b in quad):
                continue
            road.add_face([(float(alongs[a]), float(offs[b]), zr(a, b)) for a, b in quad])
            # pond covers the cell when it is inside the bowl and below the water line
            if lo <= i < hi and max(zr(a, b) for a, b in quad) < water_local:
                water.add_face([(float(alongs[a]), float(offs[b]), water_local)
                                for a, b in quad])

    road.render_mesh(msp, dxfattribs={"layer": "ROAD"})
    if len(water.faces):
        water.render_mesh(msp, dxfattribs={"layer": "WATER"})

    # synthetic cracks, each on its own selectable/toggleable layer
    _add_cracks(msp, doc, alongs, offs, Z, z_ref, cracks or [])

    # annotations placed just above/beside the model
    top = water_local + 0.6
    left = float(offs.min())
    front = float(alongs.min())
    _label(msp, (front, left, top),
           f"{low_row['street']} | CurbRisk {curb_risk} | PCI {pci}", 0.45)
    _label(msp, (front, left, top - 0.7),
           f"Ponding {depth_in:.1f} in @ {C.RAIN_EVENT_IN}\" storm "
           f"(true depth; Z exaggerated {VEXAG:g}x)", 0.35)
    _label(msp, (front, left, top - 1.3),
           f"Catchment {low_row['catchment_sqft']:.0f} sqft | "
           f"Volume {low_row['ponding_volume_cf']:.0f} cf", 0.30)
    _label(msp, (front, left, top - 1.9),
           "Longitudinal profile: LiDAR-measured | cross-street: extruded", 0.26)

    path = OUT_DIR / f"xsection_{low_row['segment_id']}.dxf"
    doc.saveas(path)
    return path


def _label(msp, xyz, text, height):
    t = msp.add_text(text, dxfattribs={"layer": "ANNOT", "height": height})
    # lay the text flat-ish in the model so it reads in the 3-D viewer
    t.set_placement(xyz)


def _render_svg(path, offs, elev, low_row, pci, curb_risk):
    """Standalone 2-D longitudinal section — viewable without any CAD/APS.

    `offs` here is signed distance along the street (m) and `elev` the measured
    centreline ground profile, so the SVG shows the road dipping into the sag.
    """
    ok = np.isfinite(elev)
    offs, elev = offs[ok], elev[ok]
    if offs.size < 2:
        return
    z0 = float(elev.min())
    rel = (elev - z0) * VEXAG
    water_y = float(low_row["ponding_depth_in"]) * M_PER_IN * VEXAG

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
<text x='{pad}' y='28' font-size='18' font-weight='700'>{low_row['street']} — longitudinal profile at low point</text>
<text x='{pad}' y='{H-14}' font-size='13' fill='#333'>Ponding {low_row['ponding_depth_in']:.1f} in @ {C.RAIN_EVENT_IN}" storm · catchment {low_row['catchment_sqft']:.0f} sqft · PCI {pci}</text>
<rect x='{W-150}' y='14' width='136' height='30' rx='6' fill='{band}'/>
<text x='{W-82}' y='34' font-size='15' fill='#fff' text-anchor='middle' font-weight='700'>CurbRisk {curb_risk}</text>
</svg>"""
    Path(path).write_text(svg)


def main(segment_ids: set[str] | None = None) -> None:
    seg = gpd.read_file(C.PROCESSED_DIR / "segments_elev.geojson").to_crs(C.UTM19N)
    low = gpd.read_file(C.LOWPOINTS_OUT).to_crs(C.UTM19N)
    scores = gpd.read_file(C.SCORES_OUT)
    sampler = get_sampler()
    by_seg = {r["segment_id"]: r for _, r in scores.iterrows()}
    crack_index = json.loads(CRACKS_INDEX.read_text()) if CRACKS_INDEX.exists() else {}

    made = 0
    for _, lr in low.iterrows():
        if segment_ids and str(lr["segment_id"]) not in segment_ids:
            continue
        alongs, offs, Z = _surface_grid(sampler, lr, seg)
        if not np.isfinite(Z).any():
            continue
        sc = by_seg.get(lr["segment_id"], {})
        pci = sc.get("pci", "n/a")
        risk = sc.get("curb_risk", "n/a")
        lr = lr.copy()
        lr["risk_band"] = sc.get("risk_band", "Moderate")
        cracks = (crack_index.get(str(lr["segment_id"]), {}) or {}).get("cracks", [])
        p = build_dxf(lr, alongs, offs, Z, pci, risk, cracks=cracks)
        # the measured longitudinal profile (centre column) feeds the 2-D SVG
        _render_svg(p.with_suffix(".svg"), alongs, Z[:, Z.shape[1] // 2], lr, pci, risk)
        made += 1
        print(f"  {lr['segment_id']}: {p.name} (3-D mesh + .svg)")
    print(f"\nGenerated {made} cross-sections in {OUT_DIR}")


if __name__ == "__main__":
    main(set(sys.argv[1:]) or None)
