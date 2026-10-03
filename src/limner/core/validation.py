import os
import sys
from pathlib import Path

SUPPORTED_EXTENSIONS: dict[str, set[str]] = {
    "gemini": {".png", ".jpg", ".jpeg", ".webp", ".heic", ".heif"},
    "fal":    {".png", ".jpg", ".jpeg"},
    "openai": {".png", ".jpg", ".jpeg", ".webp"},
    "composite": {".png", ".jpg", ".jpeg", ".webp"},
}

API_KEY_VARS: dict[str, str] = {
    "gemini": "GEMINI_API_KEY",
    "fal":    "FAL_KEY",
    "openai": "OPENAI_API_KEY",
}


def validate_images(images: list[Path], provider: str) -> None:
    supported = SUPPORTED_EXTENSIONS[provider]
    for path in images:
        if not path.exists():
            print(f"Error: image file not found: {path}")
            sys.exit(1)
        if path.suffix.lower() not in supported:
            print(
                f"Error: unsupported image type '{path.suffix}' for provider '{provider}'.\n"
                f"Supported: {', '.join(sorted(supported))}"
            )
            sys.exit(1)


def get_api_key(provider: str) -> str:
    if provider not in API_KEY_VARS:
        return ""
    var = API_KEY_VARS[provider]
    key = os.environ.get(var)
    if not key:
        print(f"Error: {var} is not set. Add it to code/.env.")
        sys.exit(1)
    return key
