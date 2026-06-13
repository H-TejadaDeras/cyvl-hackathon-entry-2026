"""Generate plain-English summaries (and a Claude vision read) for the
highest-risk CurbRisk segments.

Two Claude calls per top segment, both optional:
  1. vision  — the nearest Cyvl street-level image is passed to Claude, which
     reports only what is visible: catch-basin grate presence, ponding/staining,
     curb orientation, and pavement distress. It must not invent defects.
  2. summary — a two-sentence underwriter-facing summary built from the
     structured risk facts plus the vision observations.

Claude is optional. When credentials are missing, invalid, or the API is
unreachable, the pipeline writes a deterministic summary from the same
structured evidence so the demo remains fully usable offline.
"""
from __future__ import annotations

import json
import os

import geopandas as gpd

from curbrisk import config as C

DEFAULT_MODEL = "claude-sonnet-4-6"
TOP_N = 10
IMAGERY_INDEX = C.PROCESSED_DIR / "imagery_index.json"


def _facts(row) -> dict:
    return {
        "segment_id": row["segment_id"],
        "client_seg": row.get("client_seg"),
        "street": row["street"],
        "curb_risk": float(row["curb_risk"]),
        "risk_band": row["risk_band"],
        "ponding_depth_in": float(row["ponding_depth_in"]),
        "catchment_sqft": float(row["catchment_sqft"]),
        "pci": None if row.get("pci") is None else float(row["pci"]),
        "nearest_drain_m": row.get("nearest_drain_m"),
        "complaints_nearby": int(row["complaints_nearby"]),
        "lidar_measured": bool(row["has_lidar"]),
        "recommended_action": row["recommended_action"],
    }


def _load_imagery() -> dict:
    if IMAGERY_INDEX.exists():
        try:
            return json.loads(IMAGERY_INDEX.read_text())
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


def _fallback_summary(facts: dict) -> str:
    measurement = "LiDAR-measured" if facts["lidar_measured"] else "topography-imputed"
    return (
        f"{facts['street']} segment {facts['segment_id']} has a CurbRisk score of "
        f"{facts['curb_risk']:.1f} ({facts['risk_band']}). The {measurement} model "
        f"estimates {facts['ponding_depth_in']:.1f} inches of ponding from a "
        f"{facts['catchment_sqft']:.0f} square-foot contributing area, with "
        f"{facts['complaints_nearby']} nearby flood-related 311 reports. "
        f"Recommended action: {facts['recommended_action']}."
    )


def _vision_read(client, image_url: str, model: str) -> str:
    """Ask Claude to describe only what is visible in the Cyvl street image."""
    prompt = (
        "This is a street-level image from a road survey. Report ONLY what is "
        "visibly present, in 1-2 sentences. Specifically note: (a) any catch-basin "
        "grate or storm drain inlet at the curb and whether it looks clear or "
        "obstructed; (b) standing water, water staining, or sediment lines; "
        "(c) curb/gutter orientation relative to the road; (d) visible pavement "
        "distress (cracking, potholes, patching). Do NOT speculate about defects "
        "you cannot see; if something is not visible, say so."
    )
    message = client.messages.create(
        model=model,
        max_tokens=220,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "url", "url": image_url}},
                {"type": "text", "text": prompt},
            ],
        }],
    )
    return "".join(b.text for b in message.content if b.type == "text").strip()


def _claude_summary(client, facts: dict, vision: str | None, model: str) -> str:
    vision_clause = (
        f" Field image observations (use only if consistent, never invent): {vision}"
        if vision else ""
    )
    prompt = (
        "Write a two-sentence drainage-risk summary for an insurance underwriter. "
        "Use only the supplied JSON facts and image observations. Clearly distinguish "
        "LiDAR-measured from imputed values and do not invent defects, causes, or "
        "observations. End with the exact recommended action. "
        f"Facts: {json.dumps(facts, sort_keys=True)}.{vision_clause}"
    )
    message = client.messages.create(
        model=model,
        max_tokens=260,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(block.text for block in message.content if block.type == "text").strip()


def generate(top_n: int = TOP_N, use_claude: bool = True) -> dict:
    scores = gpd.read_file(C.SCORES_OUT).sort_values("curb_risk", ascending=False).head(top_n)
    imagery = _load_imagery()
    model = os.environ.get("CLAUDE_MODEL", DEFAULT_MODEL)
    client = None
    error = None
    if use_claude and os.environ.get("ANTHROPIC_API_KEY"):
        try:
            from anthropic import Anthropic
            client = Anthropic(timeout=30.0)
        except Exception as exc:  # noqa: BLE001
            error = f"{type(exc).__name__}: {exc}"

    summaries = {}
    for _, row in scores.iterrows():
        facts = _facts(row)
        sid = facts["segment_id"]
        seg_imgs = imagery.get(sid, {})
        plain = seg_imgs.get("plain_images") or []
        nearest_url = plain[0]["url"] if plain else None

        text = _fallback_summary(facts)
        vision = None
        source = "structured_fallback"
        if client is not None:
            # 1. vision read of the nearest street image
            if nearest_url:
                try:
                    vision = _vision_read(client, nearest_url, model)
                except Exception as exc:  # noqa: BLE001
                    error = f"vision: {type(exc).__name__}: {exc}"
            # 2. underwriter summary (folds in the vision read when available)
            try:
                text = _claude_summary(client, facts, vision, model)
                source = "claude+vision" if vision else "claude"
            except Exception as exc:  # noqa: BLE001
                error = f"summary: {type(exc).__name__}: {exc}"
                client = None
        summaries[sid] = {
            "summary": text,
            "vision": vision,
            "image_url": nearest_url,
            "panoramic_url": (seg_imgs.get("panoramic") or {}).get("viewer_url"),
            "source": source,
            "model": model if source.startswith("claude") else None,
        }

    payload = {"summaries": summaries, "claude_error": error}
    C.SUMMARIES_OUT.write_text(json.dumps(payload, indent=2))
    print(f"Wrote {len(summaries)} segment summaries to {C.SUMMARIES_OUT}")
    if error:
        print(f"Claude issue encountered; used best-available fallback ({error})")
    return payload


if __name__ == "__main__":
    generate()
