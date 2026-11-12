"""Resolves the output directory for generated images and locates the key file.

Precedence: explicit override (the --output-dir flag) > LIMNER_OUTPUT_DIR
environment variable > ./output relative to the current working directory.
Test runs write into <output dir>/test. This is the only module that
computes an output path; it does not create the directories it resolves.

The key file is the .env beside pyproject.toml, found from this file's own
location and never from the current folder, so a run started in any workspace
reads the same keys and ignores that workspace's own .env.
"""
import os
from pathlib import Path

from dotenv import load_dotenv


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


def resolve_env_file() -> Path | None:
    # None outside the source tree (a regular install): the path would be a guess, so none is offered.
    root = Path(__file__).resolve().parents[3]
    if not (root / "pyproject.toml").is_file():
        return None
    return root / ".env"


def load_keys(env_file: Path | None = None) -> Path | None:
    path = env_file if env_file is not None else resolve_env_file()
    if path is not None:
        # A missing file is the key check's to report; override stays off so the environment wins.
        load_dotenv(path, override=False)
    return path
