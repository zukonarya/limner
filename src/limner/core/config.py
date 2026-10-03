"""Resolves the output directory for generated images.

Precedence: explicit override (the --output-dir flag) > LIMNER_OUTPUT_DIR
environment variable > ./output relative to the current working directory.
This is the only module that computes an output path; it does not create
the directory it resolves.
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
