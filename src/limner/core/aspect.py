import math

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
