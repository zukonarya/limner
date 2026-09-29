import os
from pathlib import Path

from google import genai
from google.genai import types

MODEL = "gemini-3-pro-image-preview"

_MIME_TYPES: dict[str, str] = {
    ".png":  "image/png",
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".heic": "image/heic",
    ".heif": "image/heif",
}


def generate(prompt: str, images: list[Path]) -> bytes:
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

    response = client.models.generate_content(
        model=MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            response_modalities=["TEXT", "IMAGE"],
            image_config=types.ImageConfig(
                aspect_ratio="1:1",
                image_size="1K",
            ),
        ),
    )

    for part in response.candidates[0].content.parts:
        if part.text:
            print(f"Model note: {part.text.strip()}")
        if part.inline_data is not None:
            return part.inline_data.data

    raise RuntimeError("No image returned in Gemini response.")
