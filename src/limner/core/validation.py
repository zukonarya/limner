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


class InputError(ValueError):
    pass


def check_provider(provider: str) -> None:
    if provider not in VALID_PROVIDERS:
        raise InputError(f"unknown provider {provider[:40]!r}. Valid: {', '.join(VALID_PROVIDERS)}")


def check_reference_rules(provider: str, names: list[str], where: str) -> None:
    """The provider's reference rules, shared by plain mode and orders; `where` names the caller's input."""
    if not names and provider in NEEDS_REFERENCE:
        raise InputError(f"provider '{provider}' needs at least one reference image ({where}).")
    supported = SUPPORTED_EXTENSIONS[provider]
    for name in names:
        suffix = Path(name).suffix
        if suffix.lower() not in supported:
            raise InputError(
                f"unsupported image type {suffix[:20]!r} for provider '{provider}'.\n"
                f"Supported: {', '.join(sorted(supported))}"
            )


def validate_provider(provider: str) -> None:
    try:
        check_provider(provider)
    except InputError as e:
        print(f"Error: {e}")
        sys.exit(1)


def validate_images(images: list[Path], provider: str) -> None:
    for path in images:
        if not path.exists():
            print(f"Error: image file not found: {path}")
            sys.exit(1)
    try:
        check_reference_rules(provider, [str(p) for p in images], "--image")
    except InputError as e:
        print(f"Error: {e}")
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
