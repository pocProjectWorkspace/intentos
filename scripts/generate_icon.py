#!/usr/bin/env python3
"""Generate IntentOS app icons programmatically using raw pixel manipulation.

Creates PNG icons with a dark blue-to-purple gradient background and a
centered cyan lightning bolt.  Uses only stdlib (struct, zlib) for PNG
encoding — no PIL or external libraries needed.

Output: ui/desktop/src-tauri/icons/ at 32, 128, 256, 512, 1024 px.
"""

from __future__ import annotations

import math
import os
import struct
import zlib
from pathlib import Path

# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------

BG_TOP = (10, 10, 46)       # #0a0a2e — dark blue
BG_BOT = (30, 10, 60)       # purple tint at bottom
CYAN = (6, 182, 212)        # #06b6d4
GLOW = (6, 182, 212, 80)    # translucent glow

# ---------------------------------------------------------------------------
# Minimal PNG encoder (stdlib only)
# ---------------------------------------------------------------------------


def _make_png(pixels: list[list[tuple]], width: int, height: int) -> bytes:
    """Encode RGBA pixel grid to a PNG file (bytes)."""

    def _chunk(chunk_type: bytes, data: bytes) -> bytes:
        c = chunk_type + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    header = b"\x89PNG\r\n\x1a\n"
    ihdr = _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))

    raw_rows = b""
    for row in pixels:
        raw_rows += b"\x00"  # filter byte: None
        for r, g, b, a in row:
            raw_rows += struct.pack("BBBB", r, g, b, a)

    idat = _chunk(b"IDAT", zlib.compress(raw_rows, 9))
    iend = _chunk(b"IEND", b"")

    return header + ihdr + idat + iend


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _blend(bg: tuple, fg: tuple, alpha: float) -> tuple:
    """Blend fg over bg with given alpha [0..1]."""
    return (
        int(_lerp(bg[0], fg[0], alpha)),
        int(_lerp(bg[1], fg[1], alpha)),
        int(_lerp(bg[2], fg[2], alpha)),
        255,
    )


def _distance(x1: float, y1: float, x2: float, y2: float) -> float:
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)


def _point_in_polygon(px: float, py: float, polygon: list[tuple]) -> bool:
    """Ray-casting point-in-polygon test."""
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


# ---------------------------------------------------------------------------
# Icon renderer
# ---------------------------------------------------------------------------


def render_icon(size: int) -> bytes:
    """Render an IntentOS icon at the given square size and return PNG bytes."""
    pixels: list[list[tuple]] = []
    cx, cy = size / 2, size / 2
    r_outer = size * 0.46  # rounded-rect radius
    corner_r = size * 0.15  # corner roundness

    # Lightning bolt polygon (normalised 0..1 coordinates)
    bolt_points_norm = [
        (0.42, 0.15),
        (0.28, 0.50),
        (0.46, 0.50),
        (0.36, 0.85),
        (0.72, 0.42),
        (0.52, 0.42),
        (0.62, 0.15),
    ]

    # Scale to pixel coords with padding
    pad = size * 0.12
    bolt_poly = [
        (pad + px * (size - 2 * pad), pad + py * (size - 2 * pad))
        for px, py in bolt_points_norm
    ]

    glow_radius = size * 0.06

    for y in range(size):
        row = []
        t_y = y / max(size - 1, 1)

        for x in range(size):
            # --- Background gradient ---
            bg_r = int(_lerp(BG_TOP[0], BG_BOT[0], t_y))
            bg_g = int(_lerp(BG_TOP[1], BG_BOT[1], t_y))
            bg_b = int(_lerp(BG_TOP[2], BG_BOT[2], t_y))

            # --- Rounded rect mask ---
            dx = abs(x - cx)
            dy = abs(y - cy)
            half = r_outer
            cr = corner_r

            inside_rect = True
            alpha_rect = 1.0
            if dx > half or dy > half:
                inside_rect = False
                alpha_rect = 0.0
            elif dx > half - cr and dy > half - cr:
                dist = _distance(dx, dy, half - cr, half - cr)
                if dist > cr:
                    inside_rect = False
                    alpha_rect = 0.0
                elif dist > cr - 1.2:
                    alpha_rect = max(0.0, cr - dist) / 1.2  # AA edge

            if not inside_rect:
                row.append((0, 0, 0, 0))
                continue

            colour = (bg_r, bg_g, bg_b, int(255 * alpha_rect))

            # --- Subtle radial highlight in upper-center ---
            dist_center = _distance(x, y, cx, cy * 0.6)
            if dist_center < size * 0.35:
                highlight_t = 1.0 - dist_center / (size * 0.35)
                colour = _blend(colour, (40, 30, 80, 255), highlight_t * 0.25)

            # --- Lightning bolt glow ---
            in_bolt = _point_in_polygon(x, y, bolt_poly)

            if in_bolt:
                colour = (CYAN[0], CYAN[1], CYAN[2], int(255 * alpha_rect))
            else:
                # Check distance to bolt for glow
                min_dist = float("inf")
                for i in range(len(bolt_poly)):
                    x1, y1 = bolt_poly[i]
                    x2, y2 = bolt_poly[(i + 1) % len(bolt_poly)]
                    # Point-to-segment distance
                    seg_len_sq = (x2 - x1) ** 2 + (y2 - y1) ** 2
                    if seg_len_sq == 0:
                        d = _distance(x, y, x1, y1)
                    else:
                        t = max(0, min(1, ((x - x1) * (x2 - x1) + (y - y1) * (y2 - y1)) / seg_len_sq))
                        proj_x = x1 + t * (x2 - x1)
                        proj_y = y1 + t * (y2 - y1)
                        d = _distance(x, y, proj_x, proj_y)
                    min_dist = min(min_dist, d)

                if min_dist < glow_radius:
                    glow_t = 1.0 - min_dist / glow_radius
                    colour = _blend(colour, CYAN, glow_t * 0.5)

            row.append(colour)
        pixels.append(row)

    return _make_png(pixels, size, size)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    project_root = Path(__file__).resolve().parent.parent
    icon_dir = project_root / "ui" / "desktop" / "src-tauri" / "icons"
    icon_dir.mkdir(parents=True, exist_ok=True)

    sizes = [32, 128, 256, 512, 1024]

    for s in sizes:
        print(f"  Generating {s}x{s} icon...")
        data = render_icon(s)
        out = icon_dir / f"{s}x{s}.png"
        out.write_bytes(data)
        print(f"    -> {out}  ({len(data):,} bytes)")

    # Also write 128x128@2x (= 256x256)
    import shutil
    shutil.copy2(icon_dir / "256x256.png", icon_dir / "128x128@2x.png")
    print(f"  Copied 256x256 -> 128x128@2x.png")

    # icon.png = 512x512
    shutil.copy2(icon_dir / "512x512.png", icon_dir / "icon.png")
    print(f"  Copied 512x512 -> icon.png")

    # icon.icns = copy of 256x256 (Tauri accepts PNG renamed for dev)
    shutil.copy2(icon_dir / "256x256.png", icon_dir / "icon.icns")
    print(f"  Copied 256x256 -> icon.icns (dev placeholder)")

    # icon.ico = copy of 256x256 PNG (Tauri dev accepts this)
    shutil.copy2(icon_dir / "256x256.png", icon_dir / "icon.ico")
    print(f"  Copied 256x256 -> icon.ico (dev placeholder)")

    print("\nAll icons generated in:", icon_dir)


if __name__ == "__main__":
    main()
