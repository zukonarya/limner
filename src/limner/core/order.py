"""Validation of an order form (ADR-0004 section 3). Nothing here writes; every refusal raises OrderError."""
import json
import math
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

from limner.core import catalog
from limner.core.aspect import AspectError, check_aspect_ratio
from limner.core.catalog import CatalogError
from limner.core.store import StoreError
from limner.core.validation import NEEDS_REFERENCE, SUPPORTED_EXTENSIONS
from limner.providers import VALID_PROVIDERS

MAX_ORDER_BYTES = 1_000_000
MAX_REFERENCE_BYTES = 20 * 1024 * 1024

_SLUG = r"[a-z0-9]+(-[a-z0-9]+)*"
_PATTERNS = {
    "project": re.compile(_SLUG),
    "phase": re.compile(r"[0-9]{2}-" + _SLUG),
    "caller_name": re.compile(_SLUG),
}
_REFERENCE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")

_REQUIRED = {
    "schema_version": str, "action": str, "project": str, "phase": str, "prompt": str, "adjustments": list,
    "references": list, "provider": str, "routing_rule": str, "settings": dict, "cost_estimate": dict,
    "approval": str, "return_dir": str,
}
_OPTIONAL = {
    "version": int, "parent_version": int, "user_words": str, "feedback_on_parent": dict, "caller_name": str,
}
_CLI_FILLED = {"job_id", "caller_workspace", "received_at"}


class OrderError(ValueError):
    pass


@dataclass(frozen=True)
class Reference:
    name: str
    label: str
    source: Path
    data: bytes


@dataclass(frozen=True)
class Order:
    fields: dict
    project: str
    phase: str
    version: int | None
    parent_version: int | None
    prompt: str
    provider: str
    aspect_ratio: str | None
    references: tuple[Reference, ...]
    return_dir: Path
    caller_name: str | None


def _show(value) -> str:
    return repr(str(value)[:40])


def _no_duplicates(pairs):
    keys = [key for key, _ in pairs]
    if len(keys) != len(set(keys)):
        raise OrderError("The order repeats a field name.")
    return dict(pairs)


def _no_constants(name):
    raise OrderError(f"The order contains {name}, which is not a number.")


def _load(raw: bytes) -> dict:
    if len(raw) > MAX_ORDER_BYTES:
        raise OrderError("The order is larger than 1 MB.")
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_no_duplicates, parse_constant=_no_constants)
    except (ValueError, RecursionError):
        # ValueError covers bad UTF-8, bad JSON and integers past Python's digit limit.
        raise OrderError("The order is not UTF-8 JSON.") from None
    if not isinstance(data, dict):
        raise OrderError("The order must be a JSON object.")
    try:
        _check_encodable(data)
    except RecursionError:
        raise OrderError("The order is nested too deeply.") from None
    return data


def _check_encodable(value) -> None:
    # JSON escapes can carry lone surrogates, which can't be written as UTF-8 later.
    if isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            raise OrderError("The order contains text that is not valid UTF-8.") from None
    elif isinstance(value, dict):
        for key, item in value.items():
            _check_encodable(key)
            _check_encodable(item)
    elif isinstance(value, list):
        for item in value:
            _check_encodable(item)


def _is(value, kind) -> bool:
    # JSON true is a Python int; it must never count as a number.
    return isinstance(value, kind) and not (kind is int and isinstance(value, bool))


def _check_shape(name: str, value, fields: set[str]) -> None:
    if not isinstance(value, dict) or set(value) != fields or not all(isinstance(v, str) for v in value.values()):
        raise OrderError(f"{name} must be an object with exactly the text fields {', '.join(sorted(fields))}.")


def _check_fields(order: dict) -> None:
    for key in order:
        if key in _CLI_FILLED:
            raise OrderError(f"{key} is filled in by the CLI and may not be sent.")
        if key not in _REQUIRED and key not in _OPTIONAL:
            raise OrderError(f"Unknown field {_show(key)}.")
    for key, kind in _REQUIRED.items():
        if key not in order:
            raise OrderError(f"Missing field {key}.")
    for key, kind in {**_REQUIRED, **_OPTIONAL}.items():
        if key in order and not _is(order[key], kind):
            raise OrderError(f"{key} has the wrong type.")
    if order["schema_version"] != "1":
        raise OrderError("schema_version must be \"1\".")
    if order["action"] != "send":
        raise OrderError("action must be \"send\".")
    for key in ("prompt", "approval"):
        if not order[key]:
            raise OrderError(f"{key} may not be empty.")
    for key in ("version", "parent_version"):
        if key in order and order[key] < 1:
            raise OrderError(f"{key} must be 1 or more.")
    for item in order["adjustments"]:
        _check_shape("Each adjustment", item, {"rule", "before", "after"})
    if "feedback_on_parent" in order:
        _check_shape("feedback_on_parent", order["feedback_on_parent"], {"user_verdict", "caller_assessment"})
    for item in order["references"]:
        _check_shape("Each reference", item, {"source", "label"})
    cost = order["cost_estimate"]
    amount = cost.get("amount_usd")
    if (
        set(cost) != {"amount_usd", "basis"} or not isinstance(cost["basis"], str)
        or not (_is(amount, int) or _is(amount, float)) or not math.isfinite(amount) or amount < 0
    ):
        raise OrderError("cost_estimate must be {amount_usd: a number of 0 or more, basis: text}.")
    for key, pattern in _PATTERNS.items():
        if key in order and not pattern.fullmatch(order[key]):
            raise OrderError(f"{key} {_show(order[key])} does not match its name pattern.")


def _inside(path: str, workspace: Path) -> Path:
    resolved = (workspace / path).resolve()
    if not resolved.is_relative_to(workspace):
        raise OrderError(f"{_show(path)} is outside the caller workspace.")
    return resolved


def _read_reference(source: str, workspace: Path) -> tuple[Path, bytes]:
    resolved = _inside(source, workspace)
    try:
        fd = os.open(resolved, os.O_RDONLY)
    except OSError:
        raise OrderError(f"Reference {_show(source)} can't be opened.") from None
    with os.fdopen(fd, "rb") as f:
        # Checked on the open handle, so the file read is the file checked.
        if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
            raise OrderError(f"Reference {_show(source)} is not a regular file.")
        data = f.read(MAX_REFERENCE_BYTES + 1)
    if len(data) > MAX_REFERENCE_BYTES:
        raise OrderError(f"Reference {_show(source)} is larger than 20 MB.")
    return resolved, data


def _references(order: dict, workspace: Path) -> tuple[Reference, ...]:
    provider = order["provider"]
    if provider not in VALID_PROVIDERS:
        raise OrderError(f"Unknown provider {_show(provider)}. Valid: {', '.join(VALID_PROVIDERS)}.")
    if not order["references"] and provider in NEEDS_REFERENCE:
        raise OrderError(f"Provider '{provider}' needs at least one reference in references.")
    result = []
    for item in order["references"]:
        name = Path(item["source"]).name
        if not _REFERENCE_NAME.fullmatch(name) or ".." in name:
            raise OrderError(f"Reference name {_show(name)} does not match its name pattern.")
        if Path(name).suffix.lower() not in SUPPORTED_EXTENSIONS[provider]:
            raise OrderError(f"Reference {_show(name)} is not a type '{provider}' accepts.")
        source, data = _read_reference(item["source"], workspace)
        result.append(Reference(name, item["label"], source, data))
    return tuple(result)


def _check_store(order: dict, references, store) -> None:
    project, phase = order["project"], order["phase"]
    version = order.get("version")
    if version is not None:
        if not catalog.version_in_phase(store, project, phase, version):
            raise OrderError(f"Version {version} does not exist in phase {phase}.")
        if catalog.read_version_prompt(store, project, phase, version) != order["prompt"].encode("utf-8"):
            raise OrderError(f"The prompt differs from version {version}; send it as a new version.")
    parent = order.get("parent_version")
    if parent is not None:
        if not catalog.version_phases(store, project, parent):
            raise OrderError(f"parent_version {parent} does not exist in the project.")
        if version is not None and parent >= version:
            raise OrderError("parent_version must be lower than version.")
    catalog.check_references(store, project, [(ref.name, ref.data) for ref in references])


def parse_fields(raw: bytes) -> dict:
    """The order's JSON, with every field-level rule checked; references, paths and the store come next."""
    order = _load(raw)
    _check_fields(order)
    return order


def parse_order(raw: bytes, workspace: Path, store) -> Order:
    """workspace is the resolved caller workspace, already checked by the CLI to hold no store."""
    order = parse_fields(raw)
    aspect_ratio = order["settings"].get("aspect_ratio")
    if set(order["settings"]) - {"aspect_ratio"}:
        raise OrderError("settings may only contain aspect_ratio.")
    references = _references(order, workspace)
    return_dir = _inside(order["return_dir"], workspace)
    if not return_dir.is_dir():
        raise OrderError("return_dir must be an existing folder.")
    if aspect_ratio is not None:
        try:
            aspect_ratio = check_aspect_ratio(aspect_ratio, order["provider"])
        except AspectError as e:
            raise OrderError(str(e)) from None
    try:
        _check_store(order, references, store)
    except (CatalogError, StoreError) as e:
        raise OrderError(str(e)) from None
    return Order(
        fields=order, project=order["project"], phase=order["phase"], version=order.get("version"),
        parent_version=order.get("parent_version"), prompt=order["prompt"], provider=order["provider"],
        aspect_ratio=aspect_ratio, references=references, return_dir=return_dir,
        caller_name=order.get("caller_name"),
    )
