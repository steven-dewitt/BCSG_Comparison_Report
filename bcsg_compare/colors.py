"""Colours shared by the Excel and HTML reports."""

from __future__ import annotations

import colorsys

# Distinguishable categorical colours; beyond these, hues are generated.
_BASE = [
    "#2F6DB5", "#E3832B", "#3A9A5B", "#C8423B", "#8064A8", "#8C5A45", "#D16BA5", "#6F7378",
    "#B5A82A", "#2BA6B5", "#9FC0E8", "#F2B97F", "#93D1A3", "#EE9A93", "#C1AEDB", "#C9A291",
]

# Heatmap scales: low -> mid -> high (good = green).
BAD, MID, GOOD = "#F8696B", "#FFEB84", "#63BE7B"
NEG, ZERO, POS = "#F8696B", "#FFFFFF", "#63BE7B"


def palette(n: int) -> list[str]:
    colors = list(_BASE[:n])
    golden = 0.618033988749895
    hue = 0.11
    while len(colors) < n:
        hue = (hue + golden) % 1.0
        r, g, b = colorsys.hls_to_rgb(hue, 0.45 + 0.15 * (len(colors) % 2), 0.6)
        colors.append("#{:02X}{:02X}{:02X}".format(int(r * 255), int(g * 255), int(b * 255)))
    return colors


def _rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def blend(c1: str, c2: str, t: float) -> str:
    a, b = _rgb(c1), _rgb(c2)
    t = min(max(t, 0.0), 1.0)
    return "#{:02X}{:02X}{:02X}".format(*(round(x + (y - x) * t) for x, y in zip(a, b)))


def three_color(t: float, low: str, mid: str, high: str) -> str:
    """Colour at position ``t`` in [0, 1] on a low-mid-high scale."""
    return blend(low, mid, t * 2) if t < 0.5 else blend(mid, high, (t - 0.5) * 2)
