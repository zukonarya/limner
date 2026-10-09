import io

from PIL import Image, ImageDraw

from limner.core.aspect import reduce_ratio

LONG_SIDE = 1024


def _size(aspect_ratio: str | None) -> tuple[int, int]:
    if aspect_ratio is None:
        return LONG_SIDE, LONG_SIDE
    w, h = (int(n) for n in reduce_ratio(aspect_ratio).split(":"))
    short = max(1, round(LONG_SIDE * min(w, h) / max(w, h)))
    return (LONG_SIDE, short) if w >= h else (short, LONG_SIDE)


def render_placeholder(provider: str, aspect_ratio: str | None = None) -> bytes:
    """A marked stand-in image for test runs; it never contains prompt text."""
    image = Image.new("RGB", _size(aspect_ratio), (200, 200, 200))
    ImageDraw.Draw(image).text((8, 8), f"TEST {provider}", fill=(60, 60, 60))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
