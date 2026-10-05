#!/usr/bin/env python3
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from limner.core.config import resolve_output_dir
from limner.core.metadata import parse_header
from limner.providers import resolve_provider
from limner.core.validation import get_api_key, validate_images

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
        "-a",
        "--aspect-ratio",
        metavar="W:H",
        help=(
            "Output aspect ratio, e.g. 16:9 (gemini: any ratio, default 1:1; fal: 1:1, 4:3, 3:4, "
            "16:9, 9:16; or aspect_ratio from prompt file header)"
        ),
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
            "given (default: LIMNER_OUTPUT_DIR env var, or ./output relative "
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


def resolve_aspect_ratio(args, provider):
    ratio = args.aspect_ratio
    if ratio is None and args.file:
        header, _ = parse_header(args.file.read_text())
        ratio = header.get("aspect_ratio")
    if ratio is None:
        return None
    ratio = ratio.strip()
    match = re.fullmatch(r"([0-9]+):([0-9]+)", ratio)
    if not match or not all(int(n) > 0 for n in match.groups()):
        print(f"Error: aspect ratio '{ratio}' must be two positive integers separated by a colon, e.g. 16:9.")
        sys.exit(1)
    if provider == "fal":
        from limner.providers.fal import IMAGE_SIZES, reduce_ratio

        ratio = reduce_ratio(ratio)
        if ratio not in IMAGE_SIZES:
            print(f"Error: fal supports only these aspect ratios: {', '.join(IMAGE_SIZES)}.")
            sys.exit(1)
    elif provider != "gemini":
        print(f"Error: aspect ratio is only supported by the gemini and fal providers, not '{provider}'.")
        sys.exit(1)
    return ratio


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

    aspect_ratio = resolve_aspect_ratio(args, provider_name)

    validate_images(images, provider_name)
    get_api_key(provider_name)

    generate_fn = resolve_provider(provider_name)

    print(f"Generating with {provider_name}...")
    start = time.time()
    extra = {"aspect_ratio": aspect_ratio} if aspect_ratio else {}
    image_bytes = generate_fn(prompt, images, **extra).image
    elapsed = time.time() - start
    print(f"Response received in {elapsed:.1f}s")

    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
    output_path = build_output_path(prompt_file, provider_name, timestamp, output_dir)
    output_path.write_bytes(image_bytes)

    print(f"Saved: {output_path}")


if __name__ == "__main__":
    main()
