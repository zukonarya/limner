import os
import sys
from pathlib import Path

from limner.providers import VALID_PROVIDERS

SUPPORTED_EXTENSIONS: dict[str, set[str]] = {
    "gemini": {".png", ".jpg", ".jpeg", ".webp", ".heic", ".heif"},
    "fal":    {".png", ".jpg", ".jpeg"},
    "openai": {".png", ".jpg", ".jpeg", ".webp"},
    "composite": {".png", ".jpg", ".jpeg", ".webp"},
}

# These routes edit a reference image; without one they fail only after the
# call (fal: at the remote API), so the check runs before anything is sent.
NEEDS_REFERENCE = {"fal", "openai", "composite"}

API_KEY_VARS: dict[str, str] = {
    "gemini": "GEMINI_API_KEY",
    "fal":    "FAL_KEY",
    "openai": "OPENAI_API_KEY",
}


def validate_provider(provider: str) -> None:
    if provider not in VALID_PROVIDERS:
        print(f"Error: unknown provider '{provider}'. Valid: {', '.join(VALID_PROVIDERS)}")
        sys.exit(1)


def validate_images(images: list[Path], provider: str) -> None:
    if not images and provider in NEEDS_REFERENCE:
        print(f"Error: provider '{provider}' needs at least one reference image (--image).")
        sys.exit(1)
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
