import math
import urllib.request
from pathlib import Path

import fal_client


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


def generate(prompt: str, images: list[Path], aspect_ratio: str | None = None) -> bytes:
    arguments = {
        "prompt": prompt,
        "output_format": "png",
    }
    if aspect_ratio is not None:
        arguments["image_size"] = IMAGE_SIZES[reduce_ratio(aspect_ratio)]

    image_urls = [fal_client.upload_file(str(path)) for path in images]

    result = fal_client.subscribe(
        "fal-ai/flux-2-pro/edit",
        arguments={**arguments, "image_urls": image_urls},
    )

    output_url = result["images"][0]["url"]
    with urllib.request.urlopen(output_url) as resp:
        return resp.read()
