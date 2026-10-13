import math
import re

IMAGE_SIZES = {
    "1:1": "square_hd",
    "4:3": "landscape_4_3",
    "3:4": "portrait_4_3",
    "16:9": "landscape_16_9",
    "9:16": "portrait_16_9",
}


def reduce_ratio(ratio: str) -> str:
    w, h = (int(n) for n in ratio.split(":"))
    d = math.gcd(w, h)
    return f"{w // d}:{h // d}"


class AspectError(ValueError):
    pass


def check_aspect_ratio(ratio: str, provider: str) -> str:
    """The aspect-ratio rule for any source of the value; returns the ratio as it will be sent."""
    if not isinstance(ratio, str):
        raise AspectError("aspect ratio must be text such as 16:9.")
    ratio = ratio.strip()
    # Bounded digits keep int() below Python's conversion limit.
    match = re.fullmatch(r"([0-9]{1,6}):([0-9]{1,6})", ratio)
    if not match or not all(int(n) > 0 for n in match.groups()):
        raise AspectError(f"aspect ratio {ratio[:40]!r} must be two positive integers separated by a colon, e.g. 16:9.")
    if provider == "fal":
        ratio = reduce_ratio(ratio)
        if ratio not in IMAGE_SIZES:
            raise AspectError(f"fal supports only these aspect ratios: {', '.join(IMAGE_SIZES)}.")
    elif provider != "gemini":
        raise AspectError(f"aspect ratio is only supported by the gemini and fal providers, not '{provider}'.")
    return ratio
