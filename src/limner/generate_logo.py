#!/usr/bin/env python3
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from limner.core.config import resolve_output_dir, resolve_test_dir
from limner.core.metadata import parse_header
from limner.core.placeholder import render_placeholder
from limner.core.receipt import build_receipt, new_job_id, redact_error, utc_now, write_receipt
from limner.core.writeonce import WriteOnceError, write_once
from limner.providers import resolve_provider
from limner.providers.result import ProviderError
from limner.core.validation import get_api_key, validate_images, validate_provider

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
        "--test",
        action="store_true",
        help="Test run: write a placeholder image and a receipt to <output dir>/test; no provider is called and nothing is charged",
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
        from limner.core.aspect import IMAGE_SIZES, reduce_ratio

        ratio = reduce_ratio(ratio)
        if ratio not in IMAGE_SIZES:
            print(f"Error: fal supports only these aspect ratios: {', '.join(IMAGE_SIZES)}.")
            sys.exit(1)
    elif provider != "gemini":
        print(f"Error: aspect ratio is only supported by the gemini and fal providers, not '{provider}'.")
        sys.exit(1)
    return ratio


def build_output_path(folder: Path, stem: str | None, provider: str, timestamp: str) -> Path:
    prefix = f"{stem}_" if stem else ""
    return folder / f"{prefix}{provider}_{timestamp}.png"


def prepare_test_dir(test_dir: Path) -> None:
    # A link here could steer test files into a client folder, so only a real folder is accepted.
    if test_dir.is_symlink() or (test_dir.exists() and not test_dir.is_dir()):
        print(f"Error: the test folder {test_dir} must be a plain folder, not a link or a file.")
        sys.exit(1)
    test_dir.mkdir(parents=True, exist_ok=True)


def refuse_live_write_into_test_dir(write_dir: Path, test_dir: Path) -> None:
    write_dir, test_dir = write_dir.resolve(), test_dir.resolve()
    if write_dir == test_dir or write_dir.is_relative_to(test_dir):
        print(f"Error: a live run may not write into the test folder {test_dir}.")
        sys.exit(1)


def run_test_mode(output_path: Path, receipt_fields: dict, provider: str, aspect_ratio: str | None) -> None:
    start = time.time()
    image = render_placeholder(provider, aspect_ratio)
    elapsed = time.time() - start
    try:
        write_once(output_path, image)
        write_receipt(output_path.with_suffix(".run.json"), build_receipt(
            **receipt_fields,
            mode="test",
            status="succeeded",
            finished_at=utc_now(),
            duration_s=elapsed,
            image=output_path.name,
        ))
    except WriteOnceError as e:
        print(f"Error: {e}")
        sys.exit(1)
    print("Test run: no provider was called and nothing was charged.")
    print(f"Saved: {output_path}")
    print(f"Receipt: {output_path.with_suffix('.run.json')}")


def main():
    args = parse_args()
    output_dir = resolve_output_dir(args.output_dir)
    provider_name, images, prompt, prompt_file = resolve_config(args)
    validate_provider(provider_name)

    aspect_ratio = resolve_aspect_ratio(args, provider_name)

    validate_images(images, provider_name)

    test_dir = resolve_test_dir(output_dir)
    if args.test:
        prepare_test_dir(test_dir)
        folder = test_dir
    else:
        folder = prompt_file.parent if prompt_file else output_dir
        refuse_live_write_into_test_dir(folder, test_dir)
        get_api_key(provider_name)
        generate_fn = resolve_provider(provider_name)
        folder.mkdir(parents=True, exist_ok=True)

    started_at = utc_now()
    timestamp = started_at.astimezone().strftime("%Y-%m-%d_%H-%M-%S")
    output_path = build_output_path(folder, prompt_file.stem if prompt_file else None, provider_name, timestamp)
    receipt_path = output_path.with_suffix(".run.json")
    for target in (output_path, receipt_path):
        if target.exists():
            print(f"Error: refusing to overwrite existing file: {target}")
            sys.exit(1)

    receipt_fields = dict(
        job_id=new_job_id(started_at),
        provider=provider_name,
        prompt=prompt,
        started_at=started_at,
        prompt_file=prompt_file.name if prompt_file else None,
        references=images,
    )

    if args.test:
        run_test_mode(output_path, receipt_fields, provider_name, aspect_ratio)
        return

    print(f"Generating with {provider_name}...")
    start = time.time()
    extra = {"aspect_ratio": aspect_ratio} if aspect_ratio else {}
    try:
        result = generate_fn(prompt, images, **extra)
    except Exception as e:
        elapsed = time.time() - start
        original = e.__cause__ if isinstance(e, ProviderError) and e.__cause__ else e
        called = (
            dict(endpoint=e.endpoint, model=e.model, settings_sent=e.settings_sent,
                 provider_response=e.provider_response)
            if isinstance(e, ProviderError) else {}
        )
        receipt = build_receipt(
            **receipt_fields,
            **called,
            status="failed",
            error={"type": type(original).__name__, "message": redact_error(str(original))},
            finished_at=utc_now(),
            duration_s=elapsed,
        )
        print(f"Error: {type(original).__name__}: {original}")
        try:
            write_receipt(receipt_path, receipt)
        except WriteOnceError as write_error:
            print(f"Error: {write_error}")
        else:
            print(f"Receipt: {receipt_path}")
        sys.exit(1)
    elapsed = time.time() - start
    print(f"Response received in {elapsed:.1f}s")

    try:
        write_once(output_path, result.image)
    except WriteOnceError as e:
        print(f"Error: {e}")
        sys.exit(1)
    print(f"Saved: {output_path}")

    receipt = build_receipt(
        **receipt_fields,
        status="succeeded",
        finished_at=utc_now(),
        duration_s=elapsed,
        endpoint=result.endpoint,
        model=result.model,
        settings_sent=result.settings_sent,
        provider_response=result.provider_response,
        image=output_path.name,
    )
    try:
        write_receipt(receipt_path, receipt)
    except WriteOnceError as e:
        print(f"Error: image saved, but the receipt could not be written: {e}")
        sys.exit(1)
    print(f"Receipt: {receipt_path}")


if __name__ == "__main__":
    main()
