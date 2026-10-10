"""The store layout of ADR-0004 (version numbers, session file names, stored references), on top of the
store's primitives. Callers build keys only through this module."""
import re

from limner.core.store import KeyExists

MAX_CLAIMS = 100
_RESERVATION = re.compile(r"v([0-9]{2,})")
_VERSION_FILE = re.compile(r"v([0-9]{2,})\.txt")


class CatalogError(Exception):
    pass


def version_name(number: int) -> str:
    return f"v{number:02d}"


def _session(project: str, phase: str, number: int) -> str:
    return f"{project}/sessions/{phase}/{version_name(number)}"


def version_key(project: str, phase: str, number: int) -> str:
    return f"{_session(project, phase, number)}.txt"


def order_key(project: str, phase: str, number: int, job_id: str) -> str:
    return f"{_session(project, phase, number)}_job-{job_id}.order.json"


def image_key(project: str, phase: str, number: int, provider: str, job_id: str) -> str:
    return f"{_session(project, phase, number)}_{provider}_{job_id}.png"


def receipt_key(project: str, phase: str, number: int, provider: str, job_id: str) -> str:
    return f"{_session(project, phase, number)}_{provider}_{job_id}.run.json"


def reference_key(project: str, name: str) -> str:
    return f"{project}/references/{name}"


def _version_files(store, project: str):
    """(phase, number) for every vNN.txt directly in a phase folder."""
    for key in store.list(f"{project}/sessions/"):
        parts = key.split("/")
        match = len(parts) == 4 and _VERSION_FILE.fullmatch(parts[3])
        if match:
            yield parts[2], int(match.group(1))


def _numbers(store, project: str):
    for key in store.list(f"{project}/.versions/"):
        match = _RESERVATION.fullmatch(key.rsplit("/", 1)[1])
        if match:
            yield int(match.group(1))
    for _, number in _version_files(store, project):
        yield number


def claim_version(store, project: str) -> int:
    # The reservation, not vNN.txt, owns the number: vNN.txt sits in a phase folder, so two phases could
    # otherwise both create the same number.
    number = max(_numbers(store, project), default=0) + 1
    for _ in range(MAX_CLAIMS):
        try:
            store.create(f"{project}/.versions/{version_name(number)}", b"")
            return number
        except KeyExists:
            number += 1
    raise CatalogError(f"Could not claim a version number in {MAX_CLAIMS} tries.")


def version_phases(store, project: str, number: int) -> list[str]:
    """Every phase holding vNN.txt; legacy projects reuse numbers across phases."""
    return sorted(phase for phase, n in _version_files(store, project) if n == number)


def version_in_phase(store, project: str, phase: str, number: int) -> bool:
    return phase in version_phases(store, project, number)


def read_version_prompt(store, project: str, phase: str, number: int) -> bytes:
    return store.read(version_key(project, phase, number))


def _stored_names(store, project: str) -> dict[str, tuple[str, bool]]:
    """Lower-cased name -> (stored name, is a file directly under references/)."""
    names = {}
    for key in store.list(f"{project}/references/"):
        parts = key.split("/")
        names[parts[2].lower()] = (parts[2], len(parts) == 3)
    return names


def _check_name(name: str) -> None:
    if not name or "/" in name:
        raise CatalogError(f"Invalid reference name {name[:40]!r}.")


def check_references(store, project: str, references: list[tuple[str, bytes]]) -> None:
    """Refuses, before anything is written, every reference that store_reference would refuse later."""
    seen = {}
    for name, data in references:
        _check_name(name)
        earlier_name, earlier_data = seen.setdefault(name.lower(), (name, data))
        # Names differing only in case would land on one file on macOS and on two in S3.
        if earlier_name != name:
            raise CatalogError(f"References {earlier_name!r} and {name!r} differ only in case.")
        if earlier_data != data:
            raise CatalogError(f"Two references named {name!r} differ.")
    stored = _stored_names(store, project)
    for name, data in references:
        key = reference_key(project, name)
        if name.lower() not in stored:
            if store.exists(key):
                raise CatalogError(f"Stored reference {name!r} is not a regular file.")
            continue
        stored_name, is_file = stored[name.lower()]
        if stored_name != name or not is_file:
            raise CatalogError(f"Reference {name!r} clashes with stored {stored_name!r}.")
        if store.read(key) != data:
            raise CatalogError(f"A different reference named {name!r} is already stored.")


def store_reference(store, project: str, name: str, data: bytes) -> str:
    _check_name(name)
    clash = _stored_names(store, project).get(name.lower())
    if clash and clash[0] != name:
        raise CatalogError(f"Reference {name!r} clashes with stored {clash[0]!r}.")
    key = reference_key(project, name)
    try:
        store.create(key, data)
        return "written"
    except KeyExists:
        # A concurrent job may have stored a case variant; only the exact name counts as a reuse.
        exact = _stored_names(store, project).get(name.lower())
        if exact == (name, True) and store.read(key) == data:
            return "reused"
        raise CatalogError(f"A different reference named {name!r} is already stored.") from None
