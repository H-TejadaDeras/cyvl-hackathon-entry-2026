"""Generate CurbRisk hackathon pitch deck (7 slides, 16:9)."""
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

# Palette
NAVY = RGBColor(0x0B, 0x1F, 0x3A)
ACCENT = RGBColor(0x2E, 0x9C, 0xDB)
WATER = RGBColor(0x1E, 0x6B, 0xA8)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
LIGHT = RGBColor(0xF2, 0xF5, 0xF8)
MUTED = RGBColor(0x6B, 0x7A, 0x8C)
RISK = RGBColor(0xE0, 0x4B, 0x4B)

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
SW, SH = prs.slide_width, prs.slide_height
BLANK = prs.slide_layouts[6]


def add_bg(slide, color=WHITE):
    bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, SW, SH)
    bg.line.fill.background()
    bg.fill.solid()
    bg.fill.fore_color.rgb = color
    return bg


def add_text(slide, x, y, w, h, text, size=18, bold=False, color=NAVY,
             align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, font="Calibri"):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Emu(0)
    tf.margin_top = tf.margin_bottom = Emu(0)
    tf.vertical_anchor = anchor
    lines = text.split("\n") if isinstance(text, str) else text
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        r = p.add_run()
        r.text = line
        r.font.name = font
        r.font.size = Pt(size)
        r.font.bold = bold
        r.font.color.rgb = color
    return tb


def add_rect(slide, x, y, w, h, fill=LIGHT, line=None):
    s = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, w, h)
    s.fill.solid()
    s.fill.fore_color.rgb = fill
    if line is None:
        s.line.fill.background()
    else:
        s.line.color.rgb = line
        s.line.width = Pt(0.75)
    s.shadow.inherit = False
    return s


def add_footer(slide, page, total=7):
    add_rect(slide, 0, SH - Inches(0.35), SW, Inches(0.35), fill=NAVY)
    add_text(slide, Inches(0.4), SH - Inches(0.33), Inches(6), Inches(0.3),
             "CurbRisk  ·  Cyvl Hackathon 2026", size=10, color=WHITE,
             anchor=MSO_ANCHOR.MIDDLE)
    add_text(slide, SW - Inches(1.2), SH - Inches(0.33), Inches(0.8), Inches(0.3),
             f"{page} / {total}", size=10, color=WHITE,
             align=PP_ALIGN.RIGHT, anchor=MSO_ANCHOR.MIDDLE)


def title_bar(slide, kicker, title):
    add_rect(slide, 0, 0, Inches(0.2), SH, fill=ACCENT)
    add_text(slide, Inches(0.6), Inches(0.45), Inches(12), Inches(0.4),
             kicker, size=12, bold=True, color=ACCENT)
    add_text(slide, Inches(0.6), Inches(0.85), Inches(12), Inches(0.9),
             title, size=34, bold=True, color=NAVY)


# ---------------------------------------------------------------------------
# Slide 1 — Title
# ---------------------------------------------------------------------------
s = prs.slides.add_slide(BLANK)
add_bg(s, NAVY)
# accent stripe
add_rect(s, 0, Inches(4.2), SW, Inches(0.05), fill=ACCENT)
add_text(s, Inches(0.8), Inches(1.4), Inches(11.7), Inches(1.0),
         "CURBRISK", size=14, bold=True, color=ACCENT)
add_text(s, Inches(0.8), Inches(1.8), Inches(11.7), Inches(2.0),
         "Find the puddle before\nit floods the basement.", size=54, bold=True,
         color=WHITE)
add_text(s, Inches(0.8), Inches(4.45), Inches(11.7), Inches(0.7),
         "Street-level drainage risk scoring from LiDAR + pavement + 311.",
         size=22, color=ACCENT)
add_text(s, Inches(0.8), Inches(6.4), Inches(11.7), Inches(0.4),
         "Cyvl Hackathon 2026  ·  Somerville, MA demo footprint",
         size=14, color=WHITE)
# (no footer on title)

# ---------------------------------------------------------------------------
# Slide 2 — The Problem
# ---------------------------------------------------------------------------
s = prs.slides.add_slide(BLANK)
add_bg(s)
title_bar(s, "THE PROBLEM", "Cities and insurers price flood risk with the wrong map.")

# Two-column problem cards
col_y = Inches(2.0)
col_h = Inches(4.6)
col_w = Inches(5.8)

# Card 1 — Insurers
add_rect(s, Inches(0.6), col_y, col_w, col_h, fill=LIGHT)
add_rect(s, Inches(0.6), col_y, col_w, Inches(0.5), fill=NAVY)
add_text(s, Inches(0.85), col_y + Inches(0.08), col_w, Inches(0.4),
         "FOR INSURERS", size=12, bold=True, color=WHITE)
add_text(s, Inches(0.85), col_y + Inches(0.7), col_w - Inches(0.5), Inches(0.6),
         "FEMA zones stop at the parcel.", size=18, bold=True, color=NAVY)
add_text(s, Inches(0.85), col_y + Inches(1.4), col_w - Inches(0.5), Inches(3.0),
         "Two homes on the same block — one at a low point with a\n"
         "failing catch basin, one on a crest — pay the same premium.\n\n"
         "Underwriters have no measured, coordinate-level signal\n"
         "for which addresses pond. Cat modelers (RMS, Verisk)\n"
         "lack sub-zone drainage granularity.",
         size=13, color=NAVY)

# Card 2 — Cities
x2 = Inches(0.6) + col_w + Inches(0.3)
add_rect(s, x2, col_y, col_w, col_h, fill=LIGHT)
add_rect(s, x2, col_y, col_w, Inches(0.5), fill=NAVY)
add_text(s, x2 + Inches(0.25), col_y + Inches(0.08), col_w, Inches(0.4),
         "FOR CITIES", size=12, bold=True, color=WHITE)
add_text(s, x2 + Inches(0.25), col_y + Inches(0.7), col_w - Inches(0.5), Inches(0.6),
         "Budgets follow complaints, not water.", size=18, bold=True, color=NAVY)
add_text(s, x2 + Inches(0.25), col_y + Inches(1.4), col_w - Inches(0.5), Inches(3.0),
         "Streets get repaved over unresolved drainage and fail\n"
         "again in 18 months. The loudest neighborhood wins\n"
         "the budget; the most hydraulically stressed one doesn't.\n\n"
         "Climate change compresses storms into shorter bursts —\n"
         "1970s-era basins now see 2020s-era loads.",
         size=13, color=NAVY)

add_footer(s, 2)

# ---------------------------------------------------------------------------
# Slide 3 — The Solution
# ---------------------------------------------------------------------------
s = prs.slides.add_slide(BLANK)
add_bg(s)
title_bar(s, "THE SOLUTION", "CurbRisk: a measured, address-level flood score.")

# Pipeline arrow with 4 stages
stages = [
    ("LiDAR", "53.5M points\nroad-surface DEM"),
    ("Hydrology", "low-point detection,\ncatchment + 2-in ponding"),
    ("Score", "topo 40 / PCI 30 /\nbasin 20 / 311 10"),
    ("Deliver", "APS cross-section\n+ address API"),
]
n = len(stages)
total_w = Inches(11.8)
gap = Inches(0.15)
sw_each = (total_w - gap * (n - 1)) / n
sy = Inches(2.2)
sh_each = Inches(1.7)
sx = Inches(0.75)

for i, (label, body) in enumerate(stages):
    x = sx + i * (sw_each + gap)
    add_rect(s, x, sy, sw_each, sh_each, fill=ACCENT)
    add_text(s, x + Inches(0.15), sy + Inches(0.2), sw_each - Inches(0.3),
             Inches(0.5), label, size=20, bold=True, color=WHITE)
    add_text(s, x + Inches(0.15), sy + Inches(0.8), sw_each - Inches(0.3),
             Inches(0.9), body, size=12, color=WHITE)
    # arrow tab
    if i < n - 1:
        ar = s.shapes.add_shape(MSO_SHAPE.RIGHT_TRIANGLE,
                                x + sw_each, sy + sh_each / 2 - Inches(0.1),
                                Inches(0.18), Inches(0.2))
        ar.fill.solid()
        ar.fill.fore_color.rgb = NAVY
        ar.line.fill.background()
        ar.rotation = 90

# Output banner
add_rect(s, Inches(0.75), Inches(4.4), total_w, Inches(1.5), fill=NAVY)
add_text(s, Inches(1.0), Inches(4.5), total_w, Inches(0.5),
         "WHAT COMES OUT", size=12, bold=True, color=ACCENT)
add_text(s, Inches(1.0), Inches(4.9), total_w, Inches(1.0),
         "A 0–100 CurbRisk score per street segment, a browser-viewable 3D cross-section\n"
         "of every flagged low point, and an API an underwriter queries by address in < 10 s.",
         size=16, color=WHITE)

# Footer stat strip
add_text(s, Inches(0.75), Inches(6.2), Inches(12), Inches(0.4),
         "Demo footprint: 1 Somerville tile · 5,080 pavement sections · 381 catch basins · 145 flooding 311s",
         size=11, color=MUTED)

add_footer(s, 3)

# ---------------------------------------------------------------------------
# Slide 4 — Why It Wins
# ---------------------------------------------------------------------------
s = prs.slides.add_slide(BLANK)
add_bg(s)
title_bar(s, "WHY IT WINS", "Four data layers nobody else has integrated.")

# Four quadrant boxes
qx0 = Inches(0.75)
qy0 = Inches(2.0)
qw = Inches(5.9)
qh = Inches(2.1)
gap = Inches(0.2)

quads = [
    ("Measured terrain, not assumed", ACCENT,
     "Mobile LiDAR captures the 2-inch crown differential that 1-meter DEMs miss. We see where water actually goes."),
    ("Pavement + drainage in one model", WATER,
     "Cyvl PCI scores tell us where the road is already weak; terrain tells us where water lands on it. The intersection is where potholes reappear."),
    ("311 as ground truth", NAVY,
     "144 Somerville flooding reports validate every modeled low point. If complaints cluster on our high-risk segments, the model is right."),
    ("Autodesk-ready, browser-viewable", RISK,
     "Every flagged low point exports as an APS cross-section an underwriter opens in a browser — and a civil engineer opens in Civil 3D."),
]
for i, (head, color, body) in enumerate(quads):
    r = i // 2
    c = i % 2
    x = qx0 + c * (qw + gap)
    y = qy0 + r * (qh + gap)
    add_rect(s, x, y, qw, qh, fill=LIGHT)
    add_rect(s, x, y, Inches(0.12), qh, fill=color)
    add_text(s, x + Inches(0.35), y + Inches(0.18), qw - Inches(0.5), Inches(0.5),
             head, size=16, bold=True, color=NAVY)
    add_text(s, x + Inches(0.35), y + Inches(0.78), qw - Inches(0.5), qh - Inches(0.9),
             body, size=12, color=NAVY)

# Bottom moat line
add_text(s, Inches(0.75), Inches(6.6), Inches(12), Inches(0.4),
         "The moat: nobody else holds measured LiDAR + pavement condition + drainage hydrology + Autodesk delivery in one stack.",
         size=12, bold=True, color=ACCENT)

add_footer(s, 4)

# ---------------------------------------------------------------------------
# Slide 5 — Who Buys It
# ---------------------------------------------------------------------------
s = prs.slides.add_slide(BLANK)
add_bg(s)
title_bar(s, "BUYERS & VALUE", "Two markets, one engine.")

# Two big columns
cy = Inches(1.95)
ch = Inches(4.8)
cw = Inches(5.9)

# Primary — insurers
add_rect(s, Inches(0.75), cy, cw, ch, fill=NAVY)
add_text(s, Inches(1.0), cy + Inches(0.2), cw, Inches(0.4),
         "PRIMARY  ·  INSURANCE & RISK", size=12, bold=True, color=ACCENT)
add_text(s, Inches(1.0), cy + Inches(0.6), cw - Inches(0.5), Inches(0.6),
         "Address-level flood pricing", size=22, bold=True, color=WHITE)
add_text(s, Inches(1.0), cy + Inches(1.45), cw - Inches(0.5), Inches(3.0),
         "·  Underwriters: per-query API at point of sale\n"
         "·  Actuaries: portfolio loss exposure below the FEMA zone\n"
         "·  Cat modelers (RMS, Verisk): bulk dataset license\n\n"
         "Differentiates premiums between the crest house and\n"
         "the low-point house on the same block.",
         size=14, color=WHITE)

# Secondary — cities
x2 = Inches(0.75) + cw + Inches(0.3)
add_rect(s, x2, cy, cw, ch, fill=LIGHT)
add_rect(s, x2, cy, cw, Inches(0.4), fill=ACCENT)
add_text(s, x2 + Inches(0.25), cy + Inches(0.05), cw, Inches(0.4),
         "SECONDARY  ·  MUNICIPAL DPW", size=12, bold=True, color=WHITE)
add_text(s, x2 + Inches(0.25), cy + Inches(0.6), cw - Inches(0.5), Inches(0.6),
         "Defensible capital prioritization", size=22, bold=True, color=NAVY)
add_text(s, x2 + Inches(0.25), cy + Inches(1.45), cw - Inches(0.5), Inches(3.0),
         "·  Stop repaving over unresolved drainage\n"
         "·  Auto-generate MS4 / NPDES gap analysis\n"
         "·  Hand civil engineers a Civil 3D starting model\n"
         "·  Move to the front of FEMA BRIC / EPA CWSRF queues\n\n"
         "Replaces complaint-driven politics with a ranked, auditable list.",
         size=14, color=NAVY)

add_footer(s, 5)

# ---------------------------------------------------------------------------
# Slide 6 — Live Demo
# ---------------------------------------------------------------------------
s = prs.slides.add_slide(BLANK)
add_bg(s)
title_bar(s, "LIVE DEMO", "Address in. Drainage risk out. Under 10 seconds.")

# Flow: address -> API -> output panel
# Input box
ix, iy = Inches(0.75), Inches(2.3)
iw, ih = Inches(3.6), Inches(1.0)
add_rect(s, ix, iy, iw, ih, fill=LIGHT, line=ACCENT)
add_text(s, ix + Inches(0.2), iy + Inches(0.1), iw, Inches(0.3),
         "JUDGE ENTERS", size=10, bold=True, color=ACCENT)
add_text(s, ix + Inches(0.2), iy + Inches(0.4), iw - Inches(0.3), Inches(0.6),
         "93 Highland Ave\nSomerville, MA", size=15, bold=True, color=NAVY)

# Arrow 1
ar = s.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, ix + iw + Inches(0.15),
                        iy + Inches(0.3), Inches(0.6), Inches(0.4))
ar.fill.solid(); ar.fill.fore_color.rgb = ACCENT; ar.line.fill.background()

# API box
ax = ix + iw + Inches(0.95)
add_rect(s, ax, iy, iw, ih, fill=NAVY)
add_text(s, ax + Inches(0.2), iy + Inches(0.1), iw, Inches(0.3),
         "CURBRISK API", size=10, bold=True, color=ACCENT)
add_text(s, ax + Inches(0.2), iy + Inches(0.4), iw - Inches(0.3), Inches(0.6),
         "Geocode → segment lookup\nSQLite score cache hit", size=14, color=WHITE)

# Arrow 2
ar2 = s.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, ax + iw + Inches(0.15),
                         iy + Inches(0.3), Inches(0.6), Inches(0.4))
ar2.fill.solid(); ar2.fill.fore_color.rgb = ACCENT; ar2.line.fill.background()

# Output box (risk score)
ox = ax + iw + Inches(0.95)
ow = Inches(3.0)
add_rect(s, ox, iy, ow, ih, fill=RISK)
add_text(s, ox + Inches(0.2), iy + Inches(0.1), ow, Inches(0.3),
         "CURBRISK SCORE", size=10, bold=True, color=WHITE)
add_text(s, ox + Inches(0.2), iy + Inches(0.4), ow - Inches(0.3), Inches(0.6),
         "78 / 100  ·  HIGH", size=20, bold=True, color=WHITE)

# Bottom panel — what's in the response
py = Inches(4.0)
ph = Inches(2.5)
add_rect(s, Inches(0.75), py, Inches(11.8), ph, fill=LIGHT)
add_text(s, Inches(1.0), py + Inches(0.15), Inches(11), Inches(0.4),
         "RESPONSE PAYLOAD", size=11, bold=True, color=ACCENT)

bullets = [
    ("Score breakdown", "topo 32 · pavement 21 · basin 18 · complaints 7"),
    ("LiDAR geometry", "low-point depth, 2-in ponding volume, catchment polygon"),
    ("311 history", "3 flooding reports within 100 m since 2023"),
    ("APS cross-section", "browser-viewable 3D profile — no CAD software needed"),
    ("Recommended action", "clear upstream basin; do not resurface until drainage resolved"),
]
for i, (k, v) in enumerate(bullets):
    yy = py + Inches(0.55) + Inches(0.38) * i
    add_text(s, Inches(1.1), yy, Inches(3.2), Inches(0.35),
             f"·  {k}", size=13, bold=True, color=NAVY)
    add_text(s, Inches(4.4), yy, Inches(8.0), Inches(0.35),
             v, size=13, color=NAVY)

add_footer(s, 6)

# ---------------------------------------------------------------------------
# Slide 7 — Ask / Next
# ---------------------------------------------------------------------------
s = prs.slides.add_slide(BLANK)
add_bg(s, NAVY)
add_rect(s, 0, Inches(2.0), SW, Inches(0.05), fill=ACCENT)

add_text(s, Inches(0.8), Inches(0.7), Inches(11.7), Inches(0.5),
         "WHAT'S NEXT", size=14, bold=True, color=ACCENT)
add_text(s, Inches(0.8), Inches(1.1), Inches(11.7), Inches(0.9),
         "From one Somerville tile to a city-wide risk layer.",
         size=30, bold=True, color=WHITE)

# Three roadmap cards
ry = Inches(2.6)
rh = Inches(2.7)
rw = Inches(3.9)
gx = Inches(0.2)
cards = [
    ("NOW", "Hackathon MVP",
     "One Somerville tile end-to-end. Address → score + APS cross-section in < 10 s."),
    ("NEXT", "Paid pilot",
     "$20–50K fixed-scope study with a Somerville-style city. One paving package, one Autodesk model, one reference customer."),
    ("THEN", "Insurer dataset",
     "Bulk drainage-risk layer for one metro area, licensed to a cat modeler. Recurring revenue, no per-city sales cycle."),
]
for i, (kicker, head, body) in enumerate(cards):
    x = Inches(0.8) + i * (rw + gx)
    add_rect(s, x, ry, rw, rh, fill=WHITE)
    add_rect(s, x, ry, rw, Inches(0.4), fill=ACCENT)
    add_text(s, x + Inches(0.2), ry + Inches(0.05), rw, Inches(0.35),
             kicker, size=11, bold=True, color=WHITE)
    add_text(s, x + Inches(0.2), ry + Inches(0.55), rw - Inches(0.4), Inches(0.5),
             head, size=18, bold=True, color=NAVY)
    add_text(s, x + Inches(0.2), ry + Inches(1.15), rw - Inches(0.4), Inches(1.5),
             body, size=13, color=NAVY)

# Closing line
add_text(s, Inches(0.8), Inches(5.8), Inches(11.7), Inches(0.6),
         "Stop pricing flood risk with a map that ends at the parcel.",
         size=20, bold=True, color=ACCENT)
add_text(s, Inches(0.8), Inches(6.35), Inches(11.7), Inches(0.5),
         "Start pricing it with the one that ends at the curb.",
         size=20, bold=True, color=WHITE)

add_footer(s, 7)

# ---------------------------------------------------------------------------
out = "/home/htejadaderas/Git/cyvl-hackathon-entry-2026/presentation/CurbRisk_Pitch.pptx"
prs.save(out)
print(f"Wrote {out}")
