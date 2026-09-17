from datetime import datetime
from pathlib import Path


def parse_header(content: str) -> tuple[dict, str]:
    lines = content.split("\n")
    if not lines or not lines[0].startswith("#"):
        return {}, content.strip()

    header = {}
    prompt_start = len(lines)

    for i, line in enumerate(lines):
        if line == "---":
            prompt_start = i + 1
            break
        if line.startswith("#"):
            rest = line[1:].strip()
            if ":" in rest:
                key, _, value = rest.partition(":")
                header[key.strip()] = value.strip()

    prompt = "\n".join(lines[prompt_start:]).strip()
    return header, prompt


def write_output_metadata(file_path: Path, output_path: Path, timestamp: datetime) -> None:
    content = file_path.read_text()
    if "---\n" not in content:
        return
    ts_str = timestamp.strftime("%Y-%m-%dT%H:%M:%S")
    new_lines = f"# output: {output_path.name}\n# timestamp: {ts_str}\n"
    content = content.replace("---\n", f"{new_lines}---\n", 1)
    file_path.write_text(content)
