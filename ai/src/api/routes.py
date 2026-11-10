from typing import Literal

from fastapi import APIRouter, Request

from src.core.runtime import digest, json_bytes
from src.embeddings.tensors import serialize
from src.extraction.candidates import Mention, Relation
from src.schemas.contracts import Artifact, Batch, Contract, Manifest, Page, Passage, Process, Query


class Vector(Contract):
    vector: list[float]
    metadata: dict
    chunk_id: str | None = None
    document_version_id: str | None = None


class CandidateOrigin(Contract):
    tenant_id: str
    document_id: str
    document_version_id: str
    page_number: int
    chunk_id: str
    extraction_method: str
    model: str
    prompt_version: str


class EntityCandidate(Mention, CandidateOrigin):
    normalized_name: str


class RelationshipCandidate(Relation, CandidateOrigin):
    pass


class CandidatesResponse(Contract):
    candidates: list[EntityCandidate | RelationshipCandidate]
    usage: dict[str, int]
    prompt_version: str


class Extraction(Contract):
    manifest: Manifest
    pages: list[dict]


def routes() -> APIRouter:
    router = APIRouter()

    @router.post("/process")
    def process(body: Process, request: Request) -> Manifest:
        """Execute the requested stages and return the persisted page-level manifest."""
        return request.app.state.runtime.pipeline.run(body)

    def extract(kind, body, request):
        pipe = request.app.state.runtime.pipeline
        body = body.model_copy(
            update={"stages": {"extraction"}, "force_ocr": kind == "ocr" or body.force_ocr}
        )
        manifest = pipe.run(body)
        pages = []
        for p in manifest.pages:
            if ref := p.artifacts.get("extraction"):
                page = Page.model_validate_json(pipe.read_artifact(ref))
                value = page.model_dump(
                    include={"text", "extraction_method", "confidence", "quality"}
                    if kind in {"text", "ocr"}
                    else {"tables"}
                    if kind == "tables"
                    else {"elements", "width", "height"}
                )
                pages.append({"page_number": p.page_number, "source_ref": ref.key, **value})
        return Extraction(manifest=manifest, pages=pages)

    def extraction_endpoint(kind):
        def endpoint(body: Process, request: Request) -> Extraction:
            return extract(kind, body, request)

        return endpoint

    for kind in ("text", "ocr", "tables", "layout"):
        router.add_api_route(
            "/extraction/" + kind,
            extraction_endpoint(kind),
            methods=["POST"],
            name="extract_" + kind,
            description=f"Extract page-level {kind} from a version-scoped storage object.",
        )

    def dense(items, request):
        vectors, metadata = request.app.state.runtime.models.run(
            "text", [p.text for p in items], "document"
        )
        return [
            Vector(
                vector=v.tolist(),
                metadata=metadata,
                chunk_id=p.chunk_id,
                document_version_id=p.document_version_id,
            )
            for p, v in zip(items, vectors, strict=True)
        ]

    @router.post("/embeddings/text")
    def embed_text(body: Passage, request: Request) -> Vector:
        """Encode a source passage using the configured dense model."""
        return dense([body], request)[0]

    @router.post("/embeddings/text/batch")
    def embed_batch(body: Batch, request: Request) -> list[Vector]:
        """Encode an ordered batch of passages from one document version."""
        return dense(body.items, request)

    @router.post("/embeddings/query")
    def embed_query(body: Query, request: Request) -> Vector:
        """Encode a retrieval query using the dense model's query path."""
        vectors, metadata = request.app.state.runtime.models.run("text", [body.text], "query")
        return Vector(vector=vectors[0].tolist(), metadata=metadata)

    @router.post("/embeddings/visual/pages")
    def visual_pages(body: Process, request: Request) -> Manifest:
        """Encode selected pages and return immutable multi-vector artifact references."""
        return request.app.state.runtime.pipeline.run(
            body.model_copy(update={"stages": {"visual_embeddings"}})
        )

    @router.post("/embeddings/visual/query")
    def visual_query(body: Query, request: Request) -> Artifact:
        """Encode a query as a token-by-dimension tensor in tenant storage."""
        from src.storage.objects import save

        rt = request.app.state.runtime
        values, meta = rt.models.run("colpali", [body.text], "query")
        key = f"tenant/{body.tenant_id}/queries/derived/" + digest(
            json_bytes([body.text, meta["model_id"], meta["revision"]])
        )
        return save(
            rt.store,
            key,
            "npy",
            serialize(values[0]),
            "application/x-npy",
            **meta,
            shape=list(values[0].shape),
            format_version=1,
        )

    def candidates(kind, body, request):
        result = request.app.state.runtime.provider.extract(body)
        return CandidatesResponse(
            candidates=result[kind], usage=result["usage"], prompt_version=result["prompt_version"]
        )

    @router.post("/entities/extract")
    def entities(body: Passage, request: Request) -> CandidatesResponse:
        """Extract evidence-grounded entity candidates from one identified passage."""
        return candidates("entities", body, request)

    @router.post("/relationships/extract")
    def relationships(body: Passage, request: Request) -> CandidatesResponse:
        """Extract evidence-grounded relationship candidates from one identified passage."""
        return candidates("relationships", body, request)

    @router.get("/models")
    def models(request: Request) -> dict:
        """List registered models and their current runtime state."""
        from src.models.registry import hardware

        return {"models": request.app.state.runtime.models.status(), "hardware": hardware()}

    @router.get("/models/{model_id}")
    @router.get("/models/{model_id}/status")
    def model_info(model_id: Literal["text", "colpali"], request: Request) -> dict:
        """Inspect model state without triggering a load."""
        return request.app.state.runtime.models.status()[model_id]

    return router
