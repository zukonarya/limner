import os
from pathlib import Path

from google import genai
from google.genai import types

from .result import ProviderError, ProviderResult, provider_response

MODEL = "gemini-3-pro-image"

_MIME_TYPES: dict[str, str] = {
    ".png":  "image/png",
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".heic": "image/heic",
    ".heif": "image/heif",
}


def generate(prompt: str, images: list[Path], aspect_ratio: str = "1:1") -> ProviderResult:
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    if images:
        contents = [
            types.Part.from_bytes(
                data=path.read_bytes(),
                mime_type=_MIME_TYPES[path.suffix.lower()],
            )
            for path in images
        ] + [prompt]
    else:
        contents = prompt

    config = types.GenerateContentConfig(
        response_modalities=["TEXT", "IMAGE"],
        image_config=types.ImageConfig(
            aspect_ratio=aspect_ratio,
            image_size="1K",
        ),
    )
    called = dict(
        endpoint="models.generate_content",
        model=MODEL,
        settings_sent=config.model_dump(mode="json", exclude_none=True),
    )
    try:
        response = client.models.generate_content(model=MODEL, contents=contents, config=config)
    except Exception as e:
        raise ProviderError(e, **called) from e

    metadata = provider_response(
        request_id=response.response_id,
        model_version=response.model_version,
        usage=response.usage_metadata,
    )
    candidate = (response.candidates or [None])[0]
    for part in (candidate.content.parts if candidate and candidate.content else None) or []:
        if part.text:
            print(f"Model note: {part.text.strip()}")
        if part.inline_data is not None:
            return ProviderResult(image=part.inline_data.data, provider_response=metadata, **called)

    error = RuntimeError("No image returned in Gemini response.")
    raise ProviderError(error, provider_response=metadata, **called) from error
