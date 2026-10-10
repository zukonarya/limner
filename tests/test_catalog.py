import pytest

from limner.core.catalog import (
    CatalogError, check_references, claim_version, image_key, order_key, read_version_prompt, receipt_key,
    reference_key, store_reference, version_in_phase, version_key, version_name, version_phases,
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


def test_version_lookup_handles_numbers_reused_across_legacy_phases(store):
    store.create("p/sessions/01-a/v01.txt", b"first")
    store.create("p/sessions/02-b/v01.txt", b"second")
    assert version_phases(store, "p", 1) == ["01-a", "02-b"]
    assert version_in_phase(store, "p", "02-b", 1)
    assert not version_in_phase(store, "p", "03-c", 1)
    assert read_version_prompt(store, "p", "02-b", 1) == b"second"
    assert version_phases(store, "p", 2) == []


def test_three_digit_versions_are_counted(store):
    store.create("p/sessions/01-a/v100.txt", b"x")
    assert claim_version(store, "p") == 101


def test_keys_follow_the_adr_layout():
    assert version_key("p", "01-a", 3) == "p/sessions/01-a/v03.txt"
    assert order_key("p", "01-a", 3, "J") == "p/sessions/01-a/v03_job-J.order.json"
    assert image_key("p", "01-a", 3, "fal", "J") == "p/sessions/01-a/v03_fal_J.png"
    assert receipt_key("p", "01-a", 3, "fal", "J") == "p/sessions/01-a/v03_fal_J.run.json"
    assert reference_key("p", "a.png") == "p/references/a.png"


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
        [("x.png", b"1"), ("X.png", b"1")],
        [("crops", b"x")],
        [("sub/a.png", b"x")],
    ],
)
def test_check_references_refuses_conflicts(store, refs):
    store.create("p/references/a.png", b"img")
    store.create("p/references/crops/one.png", b"x")
    with pytest.raises(CatalogError):
        check_references(store, "p", refs)


def test_same_name_twice_with_same_bytes_is_fine(store):
    check_references(store, "p", [("x.png", b"1"), ("x.png", b"1")])


@pytest.mark.parametrize("make", ["empty folder", "broken link"])
def test_stored_name_that_is_not_a_file_is_refused(tmp_path, make):
    store = open_store(tmp_path, must_exist=True)
    refs = tmp_path / "p" / "references"
    refs.mkdir(parents=True)
    if make == "empty folder":
        (refs / "a.png").mkdir()
    else:
        (refs / "a.png").symlink_to(tmp_path / "nowhere")
    with pytest.raises(CatalogError):
        check_references(store, "p", [("a.png", b"x")])


def test_store_reference_refuses_a_case_variant_of_a_stored_name(store):
    store.create("p/references/a.png", b"img")
    with pytest.raises(CatalogError):
        store_reference(store, "p", "A.png", b"img")
