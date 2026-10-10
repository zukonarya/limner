"""Version numbers and stored references, on top of the store's primitives."""
import re

from limner.core.store import KeyExists

MAX_CLAIMS = 100
_VERSION = re.compile(r"v([0-9]{2,})")


class CatalogError(Exception):
    pass


def version_name(number: int) -> str:
    return f"v{number:02d}"


def _numbers(store, project: str):
    for key in store.list(f"{project}/.versions/"):
        match = _VERSION.fullmatch(key.rsplit("/", 1)[1])
        if match:
            yield int(match.group(1))
    for key in store.list(f"{project}/sessions/"):
        parts = key.split("/")
        match = len(parts) == 4 and re.fullmatch(r"v([0-9]{2,})\.txt", parts[3])
        if match:
            yield int(match.group(1))


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


def find_version(store, project: str, number: int) -> str | None:
    """The phase that holds vNN.txt, or None."""
    for key in store.list(f"{project}/sessions/"):
        parts = key.split("/")
        if len(parts) == 4 and parts[3] == f"{version_name(number)}.txt":
            return parts[2]
    return None


def _stored_names(store, project: str) -> dict[str, tuple[str, bool]]:
    """Lower-cased name -> (stored name, is a file directly under references/)."""
    names = {}
    for key in store.list(f"{project}/references/"):
        parts = key.split("/")
        names[parts[2].lower()] = (parts[2], len(parts) == 3)
    return names


def check_references(store, project: str, references: list[tuple[str, bytes]]) -> None:
    """Refuses, before anything is written, every reference that store_reference would refuse later."""
    seen = {}
    for name, data in references:
        earlier = seen.setdefault(name.lower(), (name, data))
        if earlier != (name, data):
            raise CatalogError(f"Two references named {name!r} differ.")
    stored = _stored_names(store, project)
    for name, data in references:
        if name.lower() not in stored:
            continue
        stored_name, is_file = stored[name.lower()]
        if stored_name != name or not is_file:
            raise CatalogError(f"Reference {name!r} clashes with stored {stored_name!r}.")
        if store.read(f"{project}/references/{name}") != data:
            raise CatalogError(f"A different reference named {name!r} is already stored.")


def store_reference(store, project: str, name: str, data: bytes) -> str:
    key = f"{project}/references/{name}"
    try:
        store.create(key, data)
        return "written"
    except KeyExists:
        if store.read(key) == data:
            return "reused"
        raise CatalogError(f"A different reference named {name!r} is already stored.") from None
