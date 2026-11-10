from collections import Counter
from collections.abc import Callable
from contextlib import contextmanager
from io import BytesIO
from threading import Lock

import structlog
from PIL import Image

from src.chunking.splitter import chunk_page, normalize
from src.core.config import Settings
from src.core.runtime import Metrics, ServiceError, digest, json_bytes, log, now, record_metrics
from src.embeddings.tensors import serialize
from src.extraction.candidates import PROMPT_VERSION, Provider
from src.ingestion.parsers import Document, encode, open_document
from src.models.registry import Registry
from src.schemas.contracts import Artifact, Manifest, Page, PageResult, Passage, Process
from src.storage.objects import Store, save

VERSION = "1.0.0"
# PyMuPDF does not support concurrent threads. One document occupies a process at a time.
DOCUMENT_SLOT = Lock()


@contextmanager
def document_slot():
    if not DOCUMENT_SLOT.acquire(blocking=False):
        raise ServiceError(
            "processing_busy", "This worker is processing another document.", "processing", 429, True
        )
    try:
        yield
    finally:
        DOCUMENT_SLOT.release()


class Pipeline:
    def __init__(
        self, cfg: Settings, store: Store, models: Registry, provider: Provider, metrics: Metrics
    ):
        self.cfg, self.store, self.models, self.provider, self.metrics = (
            cfg,
            store,
            models,
            provider,
            metrics,
        )

    def config(self, r: Process) -> dict:
        fields = (
            "max_pages",
            "max_upload_bytes",
            "text_embedding_batch_size",
            "colpali_batch_size",
            "render_dpi",
            "render_format",
            "max_image_side",
            "max_image_pixels",
            "ocr_languages",
            "ocr_psm",
            "ocr_deskew",
            "ocr_min_confidence",
            "native_min_chars",
            "chunk_size",
            "chunk_overlap",
            "text_embedding_model_id",
            "text_embedding_revision",
            "text_embedding_normalize",
            "colpali_model_id",
            "colpali_revision",
            "colpali_precision",
            "colpali_device",
            "text_embedding_device",
            "ai_device",
            "ai_allow_device_fallback",
            "llm_model",
            "llm_provider",
            "llm_response_format",
        )
        return {
            **self.cfg.model_dump(include=set(fields)),
            "supported_mime_types": sorted(self.cfg.supported_mime_types),
            "provider_endpoint_digest": digest((self.cfg.llm_endpoint or "").encode())
            if r.stages & {"entities", "relationships"}
            else None,
            "strategy": r.strategy or self.cfg.chunk_strategy,
            "force_ocr": r.force_ocr,
            "stages": sorted(r.stages),
            "pages": sorted(r.pages) if r.pages else None,
            "prompt_version": PROMPT_VERSION,
        }

    def source(self, r: Process) -> tuple[bytes, str]:
        data = self.store.read(r.source.key, self.cfg.max_upload_bytes)
        checksum = digest(data)
        if r.source.sha256 and checksum != r.source.sha256:
            raise ServiceError("checksum_mismatch", "Source checksum mismatch.", "validation")
        return data, checksum

    def run(self, r: Process) -> Manifest:
        with document_slot(), record_metrics(self.metrics), self.metrics.measure("processing"):
            try:
                result = self._run(r)
            except Exception:
                self.metrics.add("processing_failed_total")
                raise
            self.metrics.add("processing_" + result.status + "_total")
            return result

    def _run(self, r: Process) -> Manifest:
        cfg = self.cfg
        data, checksum = self.source(r)
        config = self.config(r)
        run = digest(
            json_bytes(
                [
                    VERSION,
                    r.prefix,
                    r.source.key,
                    r.source.mime_type,
                    checksum,
                    config,
                    r.idempotency_key,
                ]
            )
        )
        structlog.contextvars.bind_contextvars(
            tenant_id=r.tenant_id,
            document_id=r.document_id,
            document_version_id=r.document_version_id,
            processing_run_id=run,
        )
        base = r.prefix + "derived/" + VERSION + "/" + run
        done = base + "/manifest.json"
        if self.store.exists(done):
            cached = Manifest.model_validate_json(self.store.read(done, 64_000_000))
            keys = {a.key for page in cached.pages for a in page.artifacts.values()}
            if all(self.store.exists(key) for key in keys):
                return cached
        started = now()
        with open_document(data, r.source, cfg) as doc:
            indices = sorted(r.pages or range(1, doc.count + 1))
            if indices[-1] > doc.count:
                raise ServiceError("invalid_page", "Requested page is outside document.", "validation")
            results = [PageResult(page_number=i) for i in indices]
            headers = Counter()
            batch_size = cfg.colpali_batch_size
            for offset in range(0, len(results), batch_size):
                group = results[offset : offset + batch_size]
                for page in group:
                    self._first_pass(doc, page, r, base, headers)
                if "visual_embeddings" in r.stages:
                    self._visual(group, base)
            if r.stages & {"chunks", "text_embeddings", "entities", "relationships"}:
                repeated = {v for v, count in headers.items() if count >= 2}
                for page in results:
                    self._second_pass(page, r, base, repeated)
            total = doc.count
            source_metadata = doc.metadata
        failed = [p.page_number for p in results if p.errors]
        success = [p.page_number for p in results if not p.errors]
        kinds = {p.classification for p in results if p.classification}
        classification = next(iter(kinds)) if len(kinds) == 1 else "mixed" if kinds else "unknown"
        status = (
            "partial"
            if failed and any(r.stages.intersection(p.artifacts) for p in results)
            else "failed"
            if failed
            else "success"
        )
        if failed:
            done = (
                base
                + "/attempts/"
                + digest(json_bytes([started, [p.model_dump() for p in results]]))
                + ".json"
            )
        manifest = Manifest(
            **r.model_dump(include={"tenant_id", "document_id", "document_version_id"}),
            processing_run_id=run,
            pipeline_version=VERSION,
            source_sha256=checksum,
            source_metadata=source_metadata,
            configuration=config,
            model_versions={
                name: {"model_id": s.model_id, "revision": s.revision}
                for name, s in self.models.slots.items()
            },
            started_at=started,
            completed_at=now(),
            total_pages=total,
            classification=classification,
            successful_pages=success,
            failed_pages=failed,
            pages=results,
            status=status,
            manifest_key=done,
        )
        self.store.put(done, manifest.model_dump_json().encode(), "application/json")
        self.metrics.add("pages_total", len(results))
        log.info("processing_completed", status=status, pages=len(results))
        return manifest

    def _stage(
        self, p: PageResult, base: str, name: str, fn: Callable[[], Artifact], inputs: str = ""
    ) -> Artifact | None:
        checkpoint = f"{base}/checkpoints/{p.page_number}/{name}-{digest(inputs.encode())}.json"
        try:
            with self.metrics.measure(name):
                if self.store.exists(checkpoint):
                    artifact = Artifact.model_validate_json(self.store.read(checkpoint, 1_000_000))
                    if self.store.exists(artifact.key):
                        p.stages[name] = "cached"
                        p.artifacts[name] = artifact
                        return artifact
                artifact = fn()
                self.store.put(checkpoint, artifact.model_dump_json().encode(), "application/json")
                p.stages[name] = "success"
                p.artifacts[name] = artifact
                return artifact
        except Exception as exc:  # noqa: BLE001 - stage boundary records failure in the manifest
            self._failure(p, name, exc)
            return None

    def _failure(self, p, name, exc):
        error = (
            exc
            if isinstance(exc, ServiceError)
            else ServiceError("stage_failed", "Processing stage failed.", name, 500)
        )
        log.warning(
            "page_stage_failed",
            page=p.page_number,
            stage=name,
            code=error.detail["code"],
            exception=type(exc).__name__,
        )
        from src.schemas.contracts import Issue

        p.errors.append(Issue(**error.detail))
        p.stages[name] = "failed"

    def read_artifact(self, artifact: Artifact) -> bytes:
        data = self.store.read(artifact.key, artifact.size)
        if digest(data) != artifact.sha256:
            raise ServiceError(
                "checksum_mismatch", "Derived artifact failed integrity check.", "storage", 502
            )
        return data

    def _first_pass(self, doc: Document, p: PageResult, r: Process, base: str, headers: Counter):
        index = p.page_number - 1
        stem = f"{base}/pages/{p.page_number}"
        image = None

        def render():
            nonlocal image
            if image is None:
                image = doc.render(index)
            return image

        try:
            if r.stages & {"render", "visual_embeddings"}:
                fmt = self.cfg.render_format
                self._stage(
                    p,
                    base,
                    "render",
                    lambda: save(
                        self.store,
                        stem + "/render",
                        fmt.lower(),
                        encode(render(), fmt),
                        "image/" + fmt.lower(),
                        page_number=p.page_number,
                    ),
                )
                for n, region in enumerate(doc.images(index), 1):

                    def embedded(region=region, n=n):
                        ext, data = doc.extract_image(region)
                        return save(
                            self.store,
                            stem + f"/image-{n}",
                            ext,
                            data,
                            Image.MIME.get(ext.upper(), "application/octet-stream"),
                            source_xref=region,
                        )

                    self._stage(p, base, f"image_{n}", embedded)
            if r.stages - {"render", "visual_embeddings"}:

                def extract():
                    page = doc.extract(
                        index, digest(json_bytes([r.prefix, p.page_number]))[:24], r.force_ocr, render
                    )
                    return save(
                        self.store,
                        stem + "/extracted",
                        "json",
                        page.model_dump_json().encode(),
                        "application/json",
                    )

                artifact = self._stage(p, base, "extraction", extract)
                if artifact:
                    page = Page.model_validate_json(self.read_artifact(artifact))
                    headers.update(
                        {normalize(e.text) for e in page.elements if e.kind in {"header", "footer"}}
                    )
                    p.classification = page.classification
                    p.warnings.extend(page.warnings)
                    p.stages["ocr"] = "success" if "ocr" in page.extraction_method else "skipped"
                else:
                    p.stages["ocr"] = "failed" if any(e.stage == "ocr" for e in p.errors) else "unknown"
        finally:
            if image is not None:
                image.close()

    def _visual(self, group: list[PageResult], base: str):
        # Batch only pages missing their checkpoint. Retry individual pages on a batch failure.
        pending = []
        for p in group:
            ref = p.artifacts.get("render")
            if ref is None:
                p.stages["visual_embeddings"] = "blocked"
                continue
            key = f"{base}/checkpoints/{p.page_number}/visual_embeddings-{digest(ref.sha256.encode())}.json"
            if self.store.exists(key):
                a = Artifact.model_validate_json(self.store.read(key, 1_000_000))
                if self.store.exists(a.key):
                    p.artifacts["visual_embeddings"] = a
                    p.stages["visual_embeddings"] = "cached"
                    continue
            pending.append(p)
        if not pending:
            return
        images = []
        try:
            for p in pending:
                with Image.open(BytesIO(self.read_artifact(p.artifacts["render"]))) as src:
                    images.append(src.convert("RGB"))
            values, meta = self.models.run("colpali", images, "document")
            for p, value in zip(pending, values, strict=True):
                self._stage(
                    p,
                    base,
                    "visual_embeddings",
                    lambda p=p, value=value: save(
                        self.store,
                        f"{base}/embeddings/visual/{p.page_number}",
                        "npy",
                        serialize(value),
                        "application/x-npy",
                        **meta,
                        shape=list(value.shape),
                        format_version=1,
                        page_number=p.page_number,
                    ),
                    p.artifacts["render"].sha256,
                )
        except Exception as exc:  # noqa: BLE001 - stage boundary records failure in the manifest
            if len(pending) > 1:
                for page in pending:
                    self._visual([page], base)
            else:
                self._failure(pending[0], "visual_embeddings", exc)
        finally:
            for im in images:
                im.close()

    def _second_pass(self, p: PageResult, r: Process, base: str, repeated: set[str]):
        stages = r.stages & {"chunks", "text_embeddings", "entities", "relationships"}
        ref = p.artifacts.get("extraction")
        if ref is None:
            p.stages.update(dict.fromkeys(stages, "blocked"))
            return
        page = Page.model_validate_json(self.read_artifact(ref))
        stem = f"{base}/pages/{p.page_number}"

        def chunks():
            normalized, items = chunk_page(
                r, page, ref.key, self.cfg, r.strategy or self.cfg.chunk_strategy, repeated
            )
            return save(
                self.store,
                stem + "/chunks",
                "json",
                json_bytes({"normalized_text": normalized, "chunks": [i.model_dump() for i in items]}),
                "application/json",
            )

        chunk_ref = self._stage(
            p, base, "chunks", chunks, ref.sha256 + digest(json_bytes(sorted(repeated)))
        )
        if chunk_ref is None:
            p.stages.update(dict.fromkeys(stages - {"chunks"}, "blocked"))
            return
        import json

        items = json.loads(self.read_artifact(chunk_ref))["chunks"]

        def text_vectors():
            rows = []
            for i in range(0, len(items), self.cfg.text_embedding_batch_size):
                batch = items[i : i + self.cfg.text_embedding_batch_size]
                vectors, meta = self.models.run("text", [item["text"] for item in batch], "document")
                rows.extend(
                    {
                        "chunk_id": item["chunk_id"],
                        "document_version_id": r.document_version_id,
                        "page_number": p.page_number,
                        "vector": v.tolist(),
                        "metadata": meta,
                    }
                    for item, v in zip(batch, vectors, strict=True)
                )
            return save(
                self.store, stem + "/text_embeddings", "json", json_bytes(rows), "application/json"
            )

        if "text_embeddings" in stages:
            self._stage(p, base, "text_embeddings", text_vectors, chunk_ref.sha256)
        wanted = stages & {"entities", "relationships"}
        if wanted:

            def candidates():
                extracted = []
                for item in items:
                    passage = Passage.model_validate({k: item[k] for k in Passage.model_fields})
                    extracted.append(self.provider.extract(passage))
                return save(
                    self.store, stem + "/candidates", "json", json_bytes(extracted), "application/json"
                )

            result = self._stage(p, base, "candidates", candidates, chunk_ref.sha256)
            for name in wanted:
                p.stages[name] = p.stages["candidates"]
                if result:
                    p.artifacts[name] = result
