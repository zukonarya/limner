import base64
from pathlib import Path

from openai import OpenAI

from .result import ProviderError, ProviderResult, provider_response

MODEL = "gpt-image-2"
SETTINGS = {"output_format": "png"}


def generate(prompt: str, images: list[Path]) -> ProviderResult:
    if not images:
        raise ValueError("OpenAI images.edit requires at least one image.")

    client = OpenAI()  # reads OPENAI_API_KEY from env

    handles = [open(path, "rb") for path in images]
    try:
        result = client.images.edit(
            model=MODEL,
            image=handles if len(handles) > 1 else handles[0],
            prompt=prompt,
            **SETTINGS,
        )
    except Exception as e:
        raise ProviderError(
            e, endpoint="images.edit", model=MODEL, settings_sent=dict(SETTINGS)
        ) from e
    finally:
        for h in handles:
            h.close()

    return ProviderResult(
        image=base64.b64decode(result.data[0].b64_json),
        endpoint="images.edit",
        model=MODEL,
        settings_sent=dict(SETTINGS),
        provider_response=provider_response(
            request_id=getattr(result, "_request_id", None), usage=result.usage
        ),
    )
