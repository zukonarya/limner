# logo-generator

A focused Python module that generates logo images via the Google Gemini image generation API.

This is the execution layer of a two-part system. It accepts a prompt file as input and
produces a timestamped PNG as output. It has no knowledge of brand, project, or design
intent — those live in a separate private configuration layer.

## What this does

- Reads a prompt from a file path or CLI argument
- Calls `gemini-3-pro-image-preview` via the `google-genai` SDK
- Saves output as `output/YYYY-MM-DD_HH-MM-SS.png`

## Requirements

- Python 3.11+
- A [Gemini API key](https://aistudio.google.com/apikey)

## Setup

```bash
pip install -e ".[dev]"
cp .env.example .env
# Add your GEMINI_API_KEY to .env
```

The editable install is required, not optional — it registers the two console scripts,
`logo-generate` and `logo-export`, in the virtualenv's `bin/`, and they are invocable by
name from any working directory from then on. `pip` is the reference installer for this
project. `uv` works ad hoc (`uv pip install -e ".[dev]"`) since it reads
`pyproject.toml` directly with no lockfile, but `pip` is what these docs assume.

## Output destination

With `LOGO_OUTPUT_DIR` unset, output from an inline prompt (no `--file`) lands in
`./output` relative to the current working directory the command is run from — not
relative to where the source lives. `code/.env`, as shipped, sets `LOGO_OUTPUT_DIR` to
an absolute `code/output/`, so the workspace commands documented below land in
`code/output/` regardless of the working directory they're run from. On a fresh clone
with no `.env`, that variable is unset and the default applies.

Precedence, exactly: `--output-dir` flag → `LOGO_OUTPUT_DIR` environment variable →
`./output` relative to the current working directory. When `--file` is given, output is
written alongside the prompt file instead, unaffected by any of this.

## Usage

```
logo-generate [--provider PROVIDER] "your prompt here"
logo-generate [--provider PROVIDER] --file /path/to/prompt.txt [--image PATH ...]
```

Providers: gemini (default), fal, openai

Examples:
  # Text-only (existing workflow — unchanged)
  logo-generate --file brain/projects/my-project/active.txt

  # Gemini with one reference image
  logo-generate --provider gemini --file prompt.txt --image screenshot.png

  # fal.ai with two reference images
  logo-generate --provider fal --file prompt.txt --image ui.png --image brand.png

  # OpenAI
  logo-generate --provider openai --file prompt.txt --image ui.png

  # Re-run a version using its header defaults (provider + images recorded automatically)
  logo-generate --file sessions/01-exploration/v01.txt

## Secrets

Copy .env.example to .env and fill in the key(s) for the provider(s) you use.
Only the key for the selected provider needs to be set.

Output is saved alongside the prompt file (or the resolved output directory for inline
prompts — see [Output destination](#output-destination) above). Previous outputs are
never overwritten.

## Design

The module is intentionally stateless. It does not store prompts, track iterations, or
know anything about the logo project it is serving. That separation keeps the public
interface clean and the private design process private.

```
prompt file (private)  →  generate_logo.py  →  output PNG (local)
```

## Exporting production assets

Once you have a 1024×1024 master PNG, use `logo-export` to generate the full deployment
asset set from it:

```bash
# Dark variant (favicons + PWA icons + transparent logo mark)
logo-export --master /path/to/master-dark.png --variant dark --output /path/to/exports/

# Light variant (light-bg PNG)
logo-export --master /path/to/master-light.png --variant light --output /path/to/exports/
```

**dark variant produces:**
- `favicon.ico` — 16×16 + 32×32 embedded, transparent background
- `apple-touch-icon.png` — 180×180, solid background (iOS home screen)
- `icon-192.png` — 192×192, solid background (Android PWA manifest)
- `icon-512.png` — 512×512, solid background (Android PWA splash)
- `logo-mark-512.png` — 512×512, transparent background

**light variant produces:**
- `logo-mark-light.png` — 512×512, transparent background

Background removal uses luminance-based alpha blending. Solid black or white
backgrounds are cleanly removed; anti-aliased stroke edges are preserved.

## Notes

- Model: `gemini-3-pro-image-preview`
- Output: 1024×1024px PNG (1:1 aspect ratio)
- The `output/` directory is gitignored — generated images stay local
