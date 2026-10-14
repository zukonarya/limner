"""Resolves the output directory for generated images.

Precedence: explicit override (the --output-dir flag) > LIMNER_OUTPUT_DIR
environment variable > ./output relative to the current working directory.
Test runs write into <output dir>/test. This is the only module that
computes an output path; it does not create the directories it resolves.
"""
import os
from pathlib import Path


def resolve_output_dir(override: Path | None = None) -> Path:
    if override is not None:
        return Path(override).expanduser().resolve()

    env_value = os.environ.get("LIMNER_OUTPUT_DIR", "").strip()
    if env_value:
        return Path(env_value).expanduser().resolve()

    return (Path.cwd() / "output").resolve()


def resolve_test_dir(output_dir: Path) -> Path:
    # Left unresolved so the caller can refuse a link here before writing.
    return Path(output_dir) / "test"


def resolve_store_root() -> Path | None:
    # Whether the root is usable is the store factory's decision, not this module's.
    value = os.environ.get("LIMNER_STORE_DIR", "").strip()
    return Path(value).expanduser().resolve() if value else None
