#!/usr/bin/env python3
"""
export.py — Export production assets from a 1024x1024 logo master PNG.

Usage:
    python export.py --master PATH --variant dark|light --output DIR

dark variant produces:
    favicon.ico           (16x16 + 32x32, transparent)
    apple-touch-icon.png  (180x180, solid dark bg)
    icon-192.png          (192x192, solid dark bg)
    icon-512.png          (512x512, solid dark bg)
    logo-mark-512.png     (512x512, transparent)

light variant produces:
    logo-mark-light.png   (512x512, transparent)
"""

import argparse
import sys
from pathlib import Path

from PIL import Image


def remove_background(img: Image.Image, variant: str) -> Image.Image:
    img = img.convert("RGBA")
    pixels = list(img.get_flattened_data())
    result = []
    for r, g, b, a in pixels:
        lum = (r * 299 + g * 587 + b * 114) // 1000
        if variant == "dark":
            raw = min(255, lum * 4)
        else:
            raw = min(255, (255 - lum) * 4)
        # Snap near-transparent pixels to 0 to eliminate AI generation noise
        if raw <= 25:
            new_alpha = 0
        elif raw >= 230:
            new_alpha = 255
        else:
            new_alpha = raw
        result.append((r, g, b, min(a, new_alpha)))
    img.putdata(result)
    return img


def resize(img: Image.Image, size: int) -> Image.Image:
    return img.resize((size, size), Image.LANCZOS)


def export_dark(master: Image.Image, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)

    for size, name in [(180, "apple-touch-icon.png"), (192, "icon-192.png"), (512, "icon-512.png")]:
        resized = resize(master, size)
        resized.save(out / name)
        print(f"  {name} ({size}x{size}, solid bg)")

    transparent = remove_background(master, "dark")

    transparent.save(out / "favicon.ico", format="ICO", sizes=[(16, 16), (32, 32)])
    print("  favicon.ico (16+32 embedded, transparent)")

    resize(transparent, 512).save(out / "logo-mark-512.png")
    print("  logo-mark-512.png (512x512, transparent)")


def export_light(master: Image.Image, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    transparent = remove_background(master, "light")
    resize(transparent, 512).save(out / "logo-mark-light.png")
    print("  logo-mark-light.png (512x512, transparent)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export production assets from a logo master PNG."
    )
    parser.add_argument("--master", required=True, help="Path to 1024x1024 master PNG")
    parser.add_argument("--variant", required=True, choices=["dark", "light"])
    parser.add_argument("--output", required=True, help="Output directory")
    args = parser.parse_args()

    master_path = Path(args.master)
    if not master_path.exists():
        sys.exit(f"Error: master file not found: {master_path}")

    master = Image.open(master_path).convert("RGB")
    if master.size != (1024, 1024):
        sys.exit(f"Error: expected 1024x1024, got {master.size}")

    out = Path(args.output)
    print(f"Exporting {args.variant} variant → {out}/")

    if args.variant == "dark":
        export_dark(master, out)
    else:
        export_light(master, out)

    print("Done.")


if __name__ == "__main__":
    main()
