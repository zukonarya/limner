import os
import sys
from pathlib import Path

from limner.core.config import resolve_env_file
from limner.providers import VALID_PROVIDERS

SUPPORTED_EXTENSIONS: dict[str, set[str]] = {
    "gemini": {".png", ".jpg", ".jpeg", ".webp", ".heic", ".heif"},
    "fal":    {".png", ".jpg", ".jpeg"},
    "openai": {".png", ".jpg", ".jpeg", ".webp"},
    "composite": {".png", ".jpg", ".jpeg", ".webp"},
}

# composite only composites reference images, so it is refused before anything is
# sent when none is given. fal and openai run text-only on their own endpoints.
NEEDS_REFERENCE = {"composite"}

# Paid routes that run text-only without being asked to: the caller is told once,
# because a forgotten --image used to be refused for free. Fixed text on purpose:
# the agent reads labelled output lines, so nothing variable may appear here.
TEXT_ONLY_NOTICE = "No reference images; running the text-only route."
TEXT_ONLY_NOTICE_PROVIDERS = {"fal", "openai"}


def text_only_notice(provider: str, images) -> str | None:
    if provider in TEXT_ONLY_NOTICE_PROVIDERS and not images:
        return TEXT_ONLY_NOTICE
    return None


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


def missing_key_message(var: str) -> str:
    # The fixed prefix is what a calling agent matches on; only the tail varies.
    env_file = resolve_env_file()
    if env_file is None:
        return (f"Error: {var} is not set, and this Limner install has no key file "
                f"(it is not the editable install from the source folder). Set {var} in the environment.")
    if not env_file.is_file():
        return (f"Error: {var} is not set, and the key file {env_file} does not exist. "
                f"Create it with a line {var}=<your key>.")
    return f"Error: {var} is not set. Add it to {env_file}."


def get_api_key(provider: str) -> str:
    if provider not in API_KEY_VARS:
        return ""
    var = API_KEY_VARS[provider]
    key = os.environ.get(var)
    if not key:
        print(missing_key_message(var))
        sys.exit(1)
    return key
