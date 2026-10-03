import base64
from pathlib import Path

from openai import OpenAI


def generate(prompt: str, images: list[Path]) -> bytes:
    if not images:
        raise ValueError("OpenAI images.edit requires at least one image.")

    client = OpenAI()  # reads OPENAI_API_KEY from env

    handles = [open(path, "rb") for path in images]
    try:
        result = client.images.edit(
            model="gpt-image-2",
            image=handles if len(handles) > 1 else handles[0],
            prompt=prompt,
            output_format="png",
        )
    finally:
        for h in handles:
            h.close()

    return base64.b64decode(result.data[0].b64_json)
