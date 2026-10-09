import hashlib
import json
import re
import secrets
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

from limner.core.writeonce import write_once

SCHEMA_VERSION = "1"
MAX_ERROR_MESSAGE = 300

_URL = re.compile(r"\w+://\S+")
_BEARER = re.compile(r"(?i)\b(bearer|key|basic)\s+\S+")
_ASSIGNED_SECRET = re.compile(
    r"""(["']?)(?<![A-Za-z0-9_-])([A-Za-z0-9_-]+)\1(\s*[=:]\s*)(?:(?:bearer|basic)\s+)?(?:"[^"]*"|'[^']*'|\S+)""",
    re.IGNORECASE,
)
_SECRET_WORDS = {"key", "token", "secret", "password", "authorization"}
_SECRET_COMPOUNDS = ("api_key", "apikey", "api-key")
MAX_REDACT_INPUT = 4096


def _redact_assignment(match: re.Match) -> str:
    name = match.group(2).lower()
    if not (any(c in name for c in _SECRET_COMPOUNDS) or _SECRET_WORDS & set(re.split(r"[_-]", name))):
        return match.group(0)
    return f"{match.group(1)}{match.group(2)}{match.group(1)}{match.group(3)}[redacted]"


_TOKEN_LIKE = re.compile(r"[A-Za-z0-9_\-]{8,}:[A-Za-z0-9_\-]{8,}|[A-Za-z0-9_\-]{20,}")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_job_id(now: datetime | None = None) -> str:
    now = (now or utc_now()).astimezone(timezone.utc)
    return f"{now.strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(2)}"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def redact_error(message: str) -> str:
    """Strip URLs and credential-like strings, then cap the length; the terminal keeps the original."""
    message = _URL.sub("[url]", message[:MAX_REDACT_INPUT])
    message = _ASSIGNED_SECRET.sub(_redact_assignment, message)
    message = _BEARER.sub(r"\1 [redacted]", message)
    message = _TOKEN_LIKE.sub("[redacted]", message)
    if len(message) > MAX_ERROR_MESSAGE:
        message = message[:MAX_ERROR_MESSAGE] + "..."
    return message


def build_receipt(
    *,
    job_id: str,
    status: str,
    provider: str,
    prompt: str,
    started_at: datetime,
    finished_at: datetime,
    duration_s: float,
    error: dict | None = None,
    endpoint: str | None = None,
    model: str | None = None,
    settings_sent: dict | None = None,
    prompt_file: str | None = None,
    references: list[Path] | None = None,
    provider_response: dict | None = None,
    image: str | None = None,
    mode: str = "live",
    project: str | None = None,
    phase: str | None = None,
    version_name: str | None = None,
    caller_copies: list[dict] | None = None,
) -> dict:
    response = {"request_id": None, "seed": None, "model_version": None, "usage": None}
    response.update(provider_response or {})
    return {
        "schema_version": SCHEMA_VERSION,
        "job_id": job_id,
        "mode": mode,
        "status": status,
        "error": error,
        "project": project,
        "phase": phase,
        "version": version_name,
        "provider": provider,
        "endpoint": endpoint,
        "model": model,
        "settings_sent": settings_sent or {},
        "prompt_file": prompt_file,
        "prompt_sha256": sha256_text(prompt),
        "references": [
            {"stored": str(ref), "sha256": sha256_file(ref)} for ref in (references or [])
        ],
        "provider_response": response,
        "started_at": started_at.astimezone(timezone.utc).isoformat(),
        "finished_at": finished_at.astimezone(timezone.utc).isoformat(),
        "duration_s": duration_s,
        "image": image,
        "caller_copies": caller_copies or [],
        "limner_version": version("limner"),
    }


def serialise_receipt(receipt: dict) -> bytes:
    return (json.dumps(receipt, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def write_receipt(path: Path, receipt: dict) -> None:
    write_once(path, serialise_receipt(receipt))
