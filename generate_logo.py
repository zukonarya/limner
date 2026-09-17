#!/usr/bin/env python3
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from config import resolve_output_dir
from metadata import parse_header, write_output_metadata
from providers import resolve_provider
from validation import get_api_key, validate_images

load_dotenv()


def parse_args():
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate images using Gemini, fal.ai, or OpenAI.",
    )
    parser.add_argument(
        "--provider",
        choices=["gemini", "fal", "openai", "composite"],
        help="Image generation provider (default: gemini, or from prompt file header)",
    )
    parser.add_argument(
        "--file",
        type=Path,
        metavar="FILE",
        help="Path to a prompt text file",
    )
    parser.add_argument(
        "--image",
        type=Path,
        action="append",
        default=[],
        dest="images",
        metavar="PATH",
        help="Reference image path (repeatable)",
    )
    parser.add_argument(
        "prompt",
        nargs="?",
        help="Inline prompt text (mutually exclusive with --file)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        metavar="DIR",
        help=(
            "Directory to write generated images to when no prompt file is "
            "given (default: LOGO_OUTPUT_DIR env var, or ./output relative "
            "to the current working directory)"
        ),
    )

    args = parser.parse_args()

    if args.file and args.prompt:
        parser.error("--file and inline prompt are mutually exclusive.")
    if not args.file and not args.prompt:
        parser.error("Provide a prompt string or --file PATH.")

    return args


def resolve_config(args):
    header = {}
    prompt_text = args.prompt or ""
    prompt_file = None

    if args.file:
        if not args.file.exists():
            print(f"Error: prompt file not found: {args.file}")
            sys.exit(1)
        content = args.file.read_text()
        header, prompt_text = parse_header(content)
        prompt_file = args.file

    provider = args.provider or header.get("provider", "gemini")

    if args.images:
        images = args.images
    elif "images" in header:
        base = args.file.parent if args.file else Path(".")
        images = [base / p.strip() for p in header["images"].split(",")]
    else:
        images = []

    return provider, images, prompt_text, prompt_file


def build_output_path(
    prompt_file: Path | None, provider: str, timestamp: str, output_dir: Path
) -> Path:
    if prompt_file is not None:
        return prompt_file.parent / f"{prompt_file.stem}_{provider}_{timestamp}.png"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / f"{provider}_{timestamp}.png"


def main():
    args = parse_args()
    output_dir = resolve_output_dir(args.output_dir)
    provider_name, images, prompt, prompt_file = resolve_config(args)

    validate_images(images, provider_name)
    get_api_key(provider_name)

    generate_fn = resolve_provider(provider_name)

    print(f"Generating with {provider_name}...")
    start = time.time()
    image_bytes = generate_fn(prompt, images)
    elapsed = time.time() - start
    print(f"Response received in {elapsed:.1f}s")

    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
    output_path = build_output_path(prompt_file, provider_name, timestamp, output_dir)
    output_path.write_bytes(image_bytes)

    if prompt_file:
        write_output_metadata(prompt_file, output_path, now)

    print(f"Saved: {output_path}")


if __name__ == "__main__":
    main()
