"""Embeddable SVG trust badge (shields.io-style) for READMEs and websites.

GET /badge/{server_id}.svg -> a self-contained SVG showing the tier + score.
Missing/unknown ids render a gray "unrated" badge (200) so an embed never breaks
into a broken-image icon on someone's README.
"""
from __future__ import annotations

from fastapi import APIRouter, Response

from app.core import store

router = APIRouter()

# EU energy-label ramp (matches the frontend). Text color chosen for contrast.
_TIER = {
    "S": ("#1A9850", "#ffffff"),
    "A": ("#66BD63", "#0A0A0A"),
    "B": ("#A6D96A", "#0A0A0A"),
    "C": ("#FEE08B", "#0A0A0A"),
    "D": ("#FDAE61", "#0A0A0A"),
    "F": ("#D73027", "#ffffff"),
    "U": ("#9AA0A6", "#ffffff"),
}

_LABEL = "MCP Trust"
_LW = 74   # left segment width
_RW = 58   # right segment width


def _svg(tier: str, score) -> str:
    bg, txt = _TIER.get(tier, _TIER["U"])
    right = f"{tier} · {score}" if score not in (None, "") else tier
    w = _LW + _RW
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="20" role="img" aria-label="{_LABEL}: {tier} {score}">
  <title>{_LABEL}: {tier} {score}</title>
  <clipPath id="r"><rect width="{w}" height="20" rx="3" fill="#fff"/></clipPath>
  <g clip-path="url(#r)">
    <rect width="{_LW}" height="20" fill="#0A0A0A"/>
    <rect x="{_LW}" width="{_RW}" height="20" fill="{bg}"/>
  </g>
  <g fill="#fff" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="11" text-rendering="geometricPrecision">
    <text x="{_LW/2:.0f}" y="14" text-anchor="middle">{_LABEL}</text>
    <text x="{_LW + _RW/2:.0f}" y="14" text-anchor="middle" fill="{txt}" font-weight="bold">{right}</text>
  </g>
</svg>'''


def _respond(svg: str) -> Response:
    return Response(
        content=svg,
        media_type="image/svg+xml",
        # short cache so a re-scan shows up, but READMEs don't hammer the API
        headers={"Cache-Control": "public, max-age=300"},
    )


@router.get("/badge/{server_id}.svg")
def badge(server_id: str) -> Response:
    result = store.get(server_id)
    if result is None or result.status != "done":
        return _respond(_svg("U", ""))  # unrated / not found — still renders
    return _respond(_svg(result.tier, result.score))
