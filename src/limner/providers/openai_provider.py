import base64
import re
from pathlib import Path

from openai import OpenAI

from .result import ProviderError, ProviderResult, provider_response

MODEL = "gpt-image-2"
SETTINGS = {"output_format": "png"}

# The response says which quality and size the model chose. Only a short lowercase
# token is kept, so provider-supplied text cannot enter the receipt unbounded.
_TOKEN = re.compile(r"[a-z0-9x]{1,20}")


def _token(value):
    return value if isinstance(value, str) and _TOKEN.fullmatch(value) else None


def generate(prompt: str, images: list[Path]) -> ProviderResult:
    client = OpenAI()  # reads OPENAI_API_KEY from env

    endpoint = "images.edit" if images else "images.generate"
    handles = [open(path, "rb") for path in images]
    try:
        if images:
            result = client.images.edit(
                model=MODEL,
                image=handles if len(handles) > 1 else handles[0],
                prompt=prompt,
                **SETTINGS,
            )
        else:
            result = client.images.generate(model=MODEL, prompt=prompt, **SETTINGS)
    except Exception as e:
        raise ProviderError(
            e, endpoint=endpoint, model=MODEL, settings_sent=dict(SETTINGS)
        ) from e
    finally:
        for h in handles:
            h.close()

    return ProviderResult(
        image=base64.b64decode(result.data[0].b64_json),
        endpoint=endpoint,
        model=MODEL,
        settings_sent=dict(SETTINGS),
        provider_response={
            **provider_response(request_id=getattr(result, "_request_id", None), usage=result.usage),
            "quality": _token(getattr(result, "quality", None)),
            "size": _token(getattr(result, "size", None)),
        },
    )
