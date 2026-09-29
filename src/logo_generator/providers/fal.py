import urllib.request
from pathlib import Path

import fal_client


def generate(prompt: str, images: list[Path]) -> bytes:
    image_urls = [fal_client.upload_file(str(path)) for path in images]

    result = fal_client.subscribe(
        "fal-ai/flux-2-pro/edit",
        arguments={
            "prompt": prompt,
            "image_urls": image_urls,
            "output_format": "png",
        },
    )

    output_url = result["images"][0]["url"]
    with urllib.request.urlopen(output_url) as resp:
        return resp.read()
