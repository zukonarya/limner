import urllib.request
from pathlib import Path

import fal_client

from limner.core.aspect import IMAGE_SIZES, reduce_ratio

from .result import ProviderError, ProviderResult, provider_response


ENDPOINT = "fal-ai/flux-2-pro/edit"


def generate(prompt: str, images: list[Path], aspect_ratio: str | None = None) -> ProviderResult:
    arguments = {
        "prompt": prompt,
        "output_format": "png",
    }
    if aspect_ratio is not None:
        arguments["image_size"] = IMAGE_SIZES[reduce_ratio(aspect_ratio)]

    request_ids = []
    settings_sent = {k: v for k, v in arguments.items() if k != "prompt"}
    try:
        image_urls = [fal_client.upload_file(str(path)) for path in images]

        result = fal_client.subscribe(
            ENDPOINT,
            arguments={**arguments, "image_urls": image_urls},
            on_enqueue=request_ids.append,
        )

        output_url = result["images"][0]["url"]
        with urllib.request.urlopen(output_url) as resp:
            image = resp.read()
    except Exception as e:
        raise ProviderError(
            e,
            endpoint=ENDPOINT,
            settings_sent=settings_sent,
            provider_response=provider_response(request_id=request_ids[0] if request_ids else None),
        ) from e
    return ProviderResult(
        image=image,
        endpoint=ENDPOINT,
        settings_sent=settings_sent,
        provider_response=provider_response(
            request_id=request_ids[0] if request_ids else None,
            seed=result.get("seed"),
        ),
    )
