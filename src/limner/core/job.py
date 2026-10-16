"""One validated order becomes one job in the store (spec Design 4-6, ADR-0004 section 2 steps 2-8).

Everything goes through the store and the catalogue, so a cloud worker can call run_job unchanged.
"""
import json
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from limner.core import catalog
from limner.core.catalog import CatalogError
from limner.core.copies import FAILED, RESULTS
from limner.core.placeholder import render_placeholder
from limner.core.receipt import build_receipt, new_job_id, redact_error, serialise_receipt, utc_now
from limner.core.store import KeyExists, StoreError
from limner.providers.result import ProviderError


class JobError(Exception):
    """A job that ended early; written lists (label, key) for every file already in the store, copies the
    caller copies made before the failure."""

    def __init__(self, message: str, written: list[tuple[str, str]], copies: list[dict] | None = None):
        super().__init__(message)
        self.written = written
        self.copies = copies or []


@dataclass(frozen=True)
class JobResult:
    written: list[tuple[str, str]]
    copies: list[dict] = field(default_factory=list)


class _Failed(Exception):
    """A failure after vNN.txt exists or is matched, so it ends with a failed receipt."""

    def __init__(self, original: Exception, called: dict | None = None):
        super().__init__(str(original))
        self.original = original
        self.called = called or {}


def _order_form(order, job_id: str, received_at: str, number: int) -> bytes:
    form = dict(order.fields)
    form["references"] = [
        {**item, "source": str(ref.source)} for item, ref in zip(order.fields["references"], order.references)
    ]
    form.update(return_dir=str(order.return_dir), job_id=job_id, caller_workspace=str(order.workspace),
                received_at=received_at, version=number)
    return (json.dumps(form, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _call_provider(order, generate):
    # Providers take file paths; the copies come from the held bytes, never from the caller's files again.
    with tempfile.TemporaryDirectory(prefix="limner-refs-") as folder:
        paths = []
        for ref in order.references:
            path = Path(folder) / ref.name
            if not path.exists():
                path.write_bytes(ref.data)
            paths.append(path)
        extra = {"aspect_ratio": order.aspect_ratio} if order.aspect_ratio else {}
        try:
            return generate(order.prompt, paths, **extra)
        except Exception as e:
            original = e.__cause__ if isinstance(e, ProviderError) and e.__cause__ else e
            called = (
                dict(endpoint=e.endpoint, model=e.model, settings_sent=e.settings_sent,
                     provider_response=e.provider_response)
                if isinstance(e, ProviderError) else {}
            )
            raise _Failed(original, called) from e


def _well_formed(records, count: int) -> bool:
    return isinstance(records, list) and len(records) == count and all(
        isinstance(r, dict) and set(r) == {"path", "result", "detail"} and isinstance(r["path"], str)
        and r["result"] in RESULTS and (r["detail"] is None or isinstance(r["detail"], str))
        for r in records
    )


def _deliver(copy, files: list[tuple[str, bytes]]) -> list[dict]:
    # The original is already stored, so nothing the copy step does may fail the job.
    try:
        records = copy(files)
        if _well_formed(records, len(files)):
            return records
        detail = "invalid records"
    except Exception as e:
        detail = type(e).__name__
    return [{"path": name, "result": FAILED, "detail": detail} for name, _ in files]


def _claim(store, order, prompt: bytes, written: list) -> int:
    project, phase = order.project, order.phase
    if order.version is not None:
        if catalog.read_version_prompt(store, project, phase, order.version) != prompt:
            raise CatalogError(f"The prompt differs from version {order.version}.")
        return order.version
    number = catalog.claim_version(store, project)
    key = catalog.version_key(project, phase, number)
    try:
        store.create(key, prompt)
    except KeyExists:
        raise CatalogError(f"{catalog.version_name(number)}.txt already exists in phase {phase}.") from None
    written.append(("Prompt", key))
    return number


def run_job(store, order, mode: str, generate, copy=None) -> JobResult:
    """Runs steps 2-8 for a validated order; mode "test" renders the placeholder and never calls generate.
    copy, when given, delivers vNN.txt and the image to the caller (step 7).
    Returns (label, key) for every file written and the copy records; raises JobError on failure."""
    now = utc_now()
    job_id, received_at = new_job_id(now), now.isoformat()
    project, phase, provider = order.project, order.phase, order.provider
    written: list[tuple[str, str]] = []
    try:
        number = _claim(store, order, order.prompt.encode("utf-8"), written)
    except (CatalogError, StoreError) as e:
        raise JobError(str(e), written) from None

    stored = []
    receipt_fields = dict(
        job_id=job_id, provider=provider, prompt=order.prompt, started_at=now, mode=mode, project=project,
        phase=phase, version_name=catalog.version_name(number), prompt_file=f"{catalog.version_name(number)}.txt",
        references=stored,
    )
    receipt = catalog.receipt_key(project, phase, number, provider, job_id)
    start = time.time()
    try:
        try:
            for ref in order.references:
                if catalog.store_reference(store, project, ref.name, ref.data) == "written":
                    written.append(("Reference", catalog.reference_key(project, ref.name)))
                stored.append({"stored": f"references/{ref.name}", "sha256": ref.sha256})
            key = catalog.order_key(project, phase, number, job_id)
            try:
                store.create(key, _order_form(order, job_id, received_at, number))
            except KeyExists:
                # The receipt would be named after the same job id, so it may collide too.
                raise JobError(f"The job id {job_id} is already taken; send the order again.", written) from None
            written.append(("Order", key))
            if mode == "test":
                result = None
                image_bytes = render_placeholder(provider, order.aspect_ratio)
            else:
                start = time.time()
                result = _call_provider(order, generate)
                image_bytes = result.image
            image = catalog.image_key(project, phase, number, provider, job_id)
            store.create(image, image_bytes)
            written.append(("Image", image))
        except (JobError, _Failed):
            raise
        except Exception as e:
            # Any failure once the prompt exists, expected or not, must leave a receipt.
            raise _Failed(e) from e
    except _Failed as failure:
        _fail_with_receipt(store, receipt, receipt_fields, failure, time.time() - start, written)

    copies = []
    if copy is not None:
        copies = _deliver(copy, [(f"{catalog.version_name(number)}.txt", order.prompt.encode("utf-8")),
                                 (image.rsplit("/", 1)[1], image_bytes)])
    called = dict(endpoint=result.endpoint, model=result.model, settings_sent=result.settings_sent,
                  provider_response=result.provider_response) if result else {}
    try:
        store.create(receipt, serialise_receipt(build_receipt(
            **receipt_fields, **called, status="succeeded", finished_at=utc_now(),
            duration_s=time.time() - start, image=image.rsplit("/", 1)[1],
            caller_copies=[{"path": r["path"], "result": r["result"]} for r in copies],
        )))
    except StoreError as e:
        raise JobError(f"The image is stored, but the receipt could not be written: {e}", written, copies) from None
    written.append(("Receipt", receipt))
    return JobResult(written, copies)


def _fail_with_receipt(store, key, receipt_fields, failure: _Failed, elapsed: float, written: list) -> None:
    original = failure.original
    message = f"{type(original).__name__}: {original}"
    try:
        store.create(key, serialise_receipt(build_receipt(
            **receipt_fields, **failure.called, status="failed", finished_at=utc_now(), duration_s=elapsed,
            error={"type": type(original).__name__, "message": redact_error(str(original))},
        )))
    except StoreError as e:
        raise JobError(f"{message} (the failed receipt could not be written: {e})", written) from None
    written.append(("Receipt", key))
    raise JobError(message, written)
