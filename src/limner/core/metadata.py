import re
from datetime import datetime
from pathlib import Path


def parse_header(content: str) -> tuple[dict, str]:
    lines = re.split(r"\r\n|\r|\n", content)
    try:
        separator = lines.index("---")
    except ValueError:
        return {}, content.strip()

    before = [line for line in lines[:separator] if line.strip()]
    if not before or not all(line.startswith("#") for line in before):
        return {}, content.strip()

    header = {}
    for line in before:
        rest = line[1:].strip()
        if ":" in rest:
            key, _, value = rest.partition(":")
            header[key.strip()] = value.strip()

    prompt = "\n".join(lines[separator + 1 :]).strip()
    return header, prompt
