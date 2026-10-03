import io
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

# ── Canvas ────────────────────────────────────────────────────────────────────
CANVAS_W = 1440
CANVAS_H = 900
BG_COLOR = (12, 13, 16)  # #0C0D10

# ── Input scaling (before bezel) ─────────────────────────────────────────────
SCREENSHOT_MAX_W = int(CANVAS_W * 0.70)
SCREENSHOT_MAX_H = int(CANVAS_H * 0.65)

# ── Bezel ─────────────────────────────────────────────────────────────────────
BEZEL_TOP    = 10
BEZEL_SIDE   = 14
BEZEL_BOTTOM = 20
BEZEL_COLOR  = (18, 20, 24)
BEZEL_RADIUS = 8

# ── Perspective corners (fraction of canvas W × H, clockwise from TL) ────────
# Tune these to adjust tilt angle and monitor position.
MONITOR_TL = (0.12, 0.04)
MONITOR_TR = (0.80, 0.09)
MONITOR_BR = (0.88, 0.75)
MONITOR_BL = (0.07, 0.82)

# ── Glow ──────────────────────────────────────────────────────────────────────
GLOW_BLUR    = 28
GLOW_OPACITY = 0.35

# ── Reflection ────────────────────────────────────────────────────────────────
REFLECTION_OPACITY = 0.55


def _rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([(0, 0), (size[0] - 1, size[1] - 1)], radius=radius, fill=255)
    return mask


def _add_bezel(screenshot: Image.Image) -> Image.Image:
    w = screenshot.width + 2 * BEZEL_SIDE
    h = screenshot.height + BEZEL_TOP + BEZEL_BOTTOM
    frame = Image.new("RGBA", (w, h), BEZEL_COLOR + (255,))
    frame.paste(screenshot, (BEZEL_SIDE, BEZEL_TOP))
    result = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    result.paste(frame, mask=_rounded_mask((w, h), BEZEL_RADIUS))
    return result


def _find_coeffs(src_pts: list, dst_pts: list) -> list:
    """PIL PERSPECTIVE coefficients mapping output canvas coords → input image coords."""
    matrix = []
    rhs = []
    for (xs, ys), (xd, yd) in zip(src_pts, dst_pts):
        matrix.append([xd, yd, 1, 0, 0, 0, -xs * xd, -xs * yd])
        rhs.append(xs)
        matrix.append([0, 0, 0, xd, yd, 1, -ys * xd, -ys * yd])
        rhs.append(ys)
    return np.linalg.solve(np.array(matrix, dtype=np.float64),
                           np.array(rhs, dtype=np.float64)).tolist()


def _apply_tilt(framed: Image.Image) -> Image.Image:
    w, h = framed.size
    src = [(0, 0), (w, 0), (w, h), (0, h)]
    dst = [
        (MONITOR_TL[0] * CANVAS_W, MONITOR_TL[1] * CANVAS_H),
        (MONITOR_TR[0] * CANVAS_W, MONITOR_TR[1] * CANVAS_H),
        (MONITOR_BR[0] * CANVAS_W, MONITOR_BR[1] * CANVAS_H),
        (MONITOR_BL[0] * CANVAS_W, MONITOR_BL[1] * CANVAS_H),
    ]
    coeffs = _find_coeffs(src, dst)
    return framed.transform((CANVAS_W, CANVAS_H), Image.PERSPECTIVE, coeffs, Image.BICUBIC)


def _make_glow(monitor_layer: Image.Image) -> Image.Image:
    glow = monitor_layer.filter(ImageFilter.GaussianBlur(GLOW_BLUR))
    r, g, b, a = glow.split()
    a_arr = np.array(a, dtype=np.float32) * GLOW_OPACITY
    glow.putalpha(Image.fromarray(a_arr.clip(0, 255).astype(np.uint8)))
    return glow


def _make_reflection(monitor_layer: Image.Image) -> Image.Image:
    bottom_y = int(max(MONITOR_BL[1], MONITOR_BR[1]) * CANVAS_H)
    y_offset = 2 * bottom_y - CANVAS_H

    flipped = monitor_layer.transpose(Image.FLIP_TOP_BOTTOM)
    refl = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    refl.paste(flipped, (0, y_offset), flipped)

    r, g, b, a = refl.split()
    a_arr = np.array(a, dtype=np.float32)

    zone = CANVAS_H - bottom_y
    if zone > 0:
        fade = np.linspace(1.0, 0.0, zone, dtype=np.float32) * REFLECTION_OPACITY
        a_arr[:bottom_y, :] = 0
        a_arr[bottom_y:, :] *= fade[:, np.newaxis]

    refl.putalpha(Image.fromarray(a_arr.clip(0, 255).astype(np.uint8)))
    return refl


def generate(prompt: str, images: list[Path]) -> bytes:
    if not images:
        raise ValueError("composite provider requires at least one --image")

    screenshot = Image.open(images[0]).convert("RGBA")
    screenshot.thumbnail((SCREENSHOT_MAX_W, SCREENSHOT_MAX_H), Image.LANCZOS)

    framed = _add_bezel(screenshot)
    monitor_layer = _apply_tilt(framed)

    canvas = Image.new("RGBA", (CANVAS_W, CANVAS_H), BG_COLOR + (255,))
    canvas.alpha_composite(_make_glow(monitor_layer))
    canvas.alpha_composite(_make_reflection(monitor_layer))
    canvas.alpha_composite(monitor_layer)

    buf = io.BytesIO()
    canvas.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()
