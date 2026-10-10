import pytest

from limner.core.catalog import (
    CatalogError, check_references, claim_version, find_version, store_reference, version_name,
)
from limner.core.store import KeyExists, StoreError, open_store


@pytest.fixture
def store(tmp_path):
    return open_store(tmp_path, must_exist=True)


def test_version_name_has_at_least_two_digits():
    assert version_name(7) == "v07" and version_name(100) == "v100"


def test_first_version_is_one(store):
    assert claim_version(store, "p") == 1
    assert store.exists("p/.versions/v01")


def test_next_version_counts_all_phases_and_reservations(store):
    store.create("p/sessions/01-a/v07.txt", b"x")
    store.create("p/sessions/02-b/v13.txt", b"x")
    store.create("p/sessions/02-b/v13-red-wings-fal_2026.png", b"x")
    store.create("p/sessions/02-b/v99_notes.md", b"x")
    assert claim_version(store, "p") == 14
    assert claim_version(store, "p") == 15


def test_crashed_reservation_keeps_its_number(store):
    store.create("p/.versions/v03", b"")
    assert claim_version(store, "p") == 4


class _RacingStore:
    """Reports 'already exists' for the first reservation, as if another job won the race."""

    def __init__(self, inner):
        self.inner, self.raced = inner, False

    def create(self, key, data):
        if ".versions/" in key and not self.raced:
            self.raced = True
            raise KeyExists(key)
        return self.inner.create(key, data)

    def __getattr__(self, name):
        return getattr(self.inner, name)


def test_lost_race_moves_to_next_number(store):
    assert claim_version(_RacingStore(store), "p") == 2


def test_write_failure_is_not_retried(store):
    class Failing:
        calls = 0

        def list(self, prefix):
            return []

        def create(self, key, data):
            Failing.calls += 1
            raise StoreError("permission denied")

    with pytest.raises(StoreError):
        claim_version(Failing(), "p")
    assert Failing.calls == 1


def test_endless_exists_is_bounded():
    class AlwaysTaken:
        calls = 0

        def list(self, prefix):
            return []

        def create(self, key, data):
            AlwaysTaken.calls += 1
            raise KeyExists(key)

    with pytest.raises(CatalogError):
        claim_version(AlwaysTaken(), "p")
    assert AlwaysTaken.calls == 100


def test_find_version_returns_its_phase(store):
    store.create("p/sessions/02-b/v05.txt", b"x")
    assert find_version(store, "p", 5) == "02-b"
    assert find_version(store, "p", 6) is None


def test_store_reference_writes_then_reuses(store):
    assert store_reference(store, "p", "a.png", b"img") == "written"
    assert store_reference(store, "p", "a.png", b"img") == "reused"
    with pytest.raises(CatalogError):
        store_reference(store, "p", "a.png", b"other")


def test_check_references_accepts_new_and_identical(store):
    store.create("p/references/a.png", b"img")
    check_references(store, "p", [("a.png", b"img"), ("b.png", b"new")])


@pytest.mark.parametrize(
    "refs",
    [
        [("a.png", b"other")],
        [("A.png", b"img")],
        [("x.png", b"1"), ("X.png", b"2")],
        [("crops", b"x")],
    ],
)
def test_check_references_refuses_conflicts(store, refs):
    store.create("p/references/a.png", b"img")
    store.create("p/references/crops/one.png", b"x")
    with pytest.raises(CatalogError):
        check_references(store, "p", refs)


def test_same_name_twice_with_same_bytes_is_fine(store):
    check_references(store, "p", [("x.png", b"1"), ("x.png", b"1")])
