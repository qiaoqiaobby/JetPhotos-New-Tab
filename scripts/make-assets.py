#!/usr/bin/env python3
"""
make-assets.py — generate extension icons + placeholder using ONLY the stdlib.

No Pillow/canvas required (keeps the toolchain dependency-free). Produces:
  extension/icons/icon-16.png, icon-48.png, icon-128.png  (rounded dark square + white jet)
  extension/assets/placeholder.png                        (dark gradient + faint jet)

PNGs are written by hand (zlib + CRC). Icons are anti-aliased via supersampling.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ICONS = ROOT / "extension" / "icons"
ASSETS = ROOT / "extension" / "assets"

# Top-down jet silhouette, normalized [0,1] coords (y down). Union of 3 polygons.
FUSELAGE = [(0.500, 0.07), (0.540, 0.18), (0.556, 0.42), (0.546, 0.66), (0.560, 0.82),
            (0.530, 0.90), (0.500, 0.945), (0.470, 0.90), (0.440, 0.82), (0.454, 0.66),
            (0.444, 0.42), (0.460, 0.18)]
MAINWING = [(0.500, 0.40), (0.085, 0.64), (0.092, 0.705), (0.500, 0.55),
            (0.908, 0.705), (0.915, 0.64)]
TAILWING = [(0.500, 0.775), (0.300, 0.90), (0.305, 0.935), (0.500, 0.85),
            (0.695, 0.935), (0.700, 0.90)]
PLANE = [FUSELAGE, MAINWING, TAILWING]


def _bbox(poly):
    xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
    return min(xs), min(ys), max(xs), max(ys)
_PLANE_BBOX = [(_bbox(p), p) for p in PLANE]


def in_poly(x, y, poly) -> bool:
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]; xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def in_plane(x, y) -> bool:
    for (bx0, by0, bx1, by1), poly in _PLANE_BBOX:
        if bx0 <= x <= bx1 and by0 <= y <= by1 and in_poly(x, y, poly):
            return True
    return False


def write_png_rgba(path: Path, w: int, h: int, pixels: bytearray) -> None:
    """pixels: w*h*4 RGBA bytes, row-major."""
    raw = bytearray()
    stride = w * 4
    for y in range(h):
        raw.append(0)  # filter type 0
        raw += pixels[y * stride:(y + 1) * stride]
    comp = zlib.compress(bytes(raw), 9)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data +
                struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", comp)
    png += chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)


def lerp(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def make_icon(size: int, ss: int = 3) -> bytearray:
    """Rounded dark square + white jet, anti-aliased by ss× supersampling."""
    top = (16, 26, 46)      # navy
    bot = (6, 9, 16)        # near black
    plane_col = (242, 246, 252)
    radius = 0.20           # corner radius as fraction of size

    px = bytearray(size * size * 4)
    S = size * ss
    rad_px = radius * S

    # precompute per-subpixel-row gradient
    for oy in range(size):
        for ox in range(size):
            r_acc = g_acc = b_acc = a_acc = 0
            for sy in range(ss):
                Y = oy * ss + sy
                fy = (Y + 0.5) / S
                for sx in range(ss):
                    X = ox * ss + sx
                    fx = (X + 0.5) / S
                    # rounded-square alpha (inside=1)
                    inside = _rounded_inside(X + 0.5, Y + 0.5, S, rad_px)
                    if not inside:
                        continue
                    if in_plane(fx, fy):
                        r, g, b = plane_col
                    else:
                        r, g, b = lerp(top, bot, fy)
                    r_acc += r; g_acc += g; b_acc += b; a_acc += 255
            n = ss * ss
            i = (oy * size + ox) * 4
            if a_acc == 0:
                px[i:i + 4] = b"\x00\x00\x00\x00"
            else:
                # average colour over covered subpixels; alpha = coverage
                cov = a_acc // 255
                px[i] = r_acc // cov
                px[i + 1] = g_acc // cov
                px[i + 2] = b_acc // cov
                px[i + 3] = a_acc // n
    return px


def _rounded_inside(x, y, S, rad) -> bool:
    if rad <= 0:
        return 0 <= x <= S and 0 <= y <= S
    # distance to nearest corner circle region
    cx = min(max(x, rad), S - rad)
    cy = min(max(y, rad), S - rad)
    dx = x - cx; dy = y - cy
    return dx * dx + dy * dy <= rad * rad


def make_placeholder(w: int = 1280, h: int = 800) -> bytearray:
    """Dark vertical gradient + soft top glow + faint centered jet."""
    top = (14, 23, 38)
    bot = (5, 7, 12)
    glow = (32, 52, 84)
    px = bytearray(w * h * 4)

    # plane placement: centered, ~46% of width, keep aspect square-ish
    pw = 0.46
    px0 = 0.5 - pw / 2
    py0 = 0.5 - pw * (w / h) / 2 * 0.62  # rough vertical centering
    pscale = pw
    pvscale = pw * (w / h)

    # precompute row gradient
    row_colors = [lerp(top, bot, (y + 0.5) / h) for y in range(h)]

    for y in range(h):
        base = row_colors[y]
        ny = (y + 0.5) / h
        for x in range(w):
            nx = (x + 0.5) / w
            r, g, b = base
            # soft radial glow near upper-center (horizon light)
            gx = nx - 0.5; gy = ny - 0.30
            d2 = gx * gx * 1.4 + gy * gy
            if d2 < 0.16:
                t = (0.16 - d2) / 0.16 * 0.5
                r = int(r + (glow[0] - r) * t)
                g = int(g + (glow[1] - g) * t)
                b = int(b + (glow[2] - b) * t)
            # faint plane silhouette (lighten)
            lx = (nx - px0) / pscale
            ly = (ny - py0) / pvscale
            if 0 <= lx <= 1 and 0 <= ly <= 1 and in_plane(lx, ly):
                r = min(255, r + 26); g = min(255, g + 30); b = min(255, b + 36)
            i = (y * w + x) * 4
            px[i] = r; px[i + 1] = g; px[i + 2] = b; px[i + 3] = 255
    return px


def main():
    for size in (16, 48, 128):
        ss = 4 if size <= 48 else 3
        write_png_rgba(ICONS / f"icon-{size}.png", size, size, make_icon(size, ss))
        print(f"  icon-{size}.png")
    write_png_rgba(ASSETS / "placeholder.png", 1280, 800, make_placeholder(1280, 800))
    print("  placeholder.png")
    print("Assets written.")


if __name__ == "__main__":
    main()
