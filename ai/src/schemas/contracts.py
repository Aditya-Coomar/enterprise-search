from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.core.config import Strategy

ID = Annotated[str, Field(pattern=r"^[a-zA-Z0-9_-]{1,128}$")]
Text = Annotated[str, Field(min_length=1, max_length=64000, pattern=r"\S")]
Stage = Literal[
    "render", "extraction", "chunks", "text_embeddings", "visual_embeddings", "entities", "relationships"
]
Box = tuple[float, float, float, float]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Context(Contract):
    tenant_id: ID
    document_id: ID
    document_version_id: ID

    @property
    def prefix(self) -> str:
        return (
            f"tenant/{self.tenant_id}/documents/{self.document_id}/versions/{self.document_version_id}/"
        )


class Source(Contract):
    key: str = Field(max_length=1024)
    mime_type: Literal["application/pdf", "image/png", "image/jpeg"]
    sha256: str | None = Field(None, pattern="^[0-9a-f]{64}$")


class Process(Context):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "tenant_id": "acme",
                    "document_id": "report",
                    "document_version_id": "v1",
                    "source": {
                        "key": "tenant/acme/documents/report/versions/v1/original/report.pdf",
                        "mime_type": "application/pdf",
                    },
                    "stages": ["render", "chunks"],
                }
            ]
        }
    )
    source: Source
    stages: set[Stage] = {"render", "extraction", "chunks", "text_embeddings", "visual_embeddings"}
    strategy: Strategy | None = None
    idempotency_key: ID | None = None
    pages: set[Annotated[int, Field(gt=0)]] | None = Field(None, min_length=1, max_length=1000)
    force_ocr: bool = False

    @model_validator(mode="after")
    def scoped_source(self):
        prefix = self.prefix
        if not self.source.key.startswith(prefix) or self.source.key[len(prefix) :].startswith(
            "derived/"
        ):
            raise ValueError("source must belong to this document version outside derived/")
        if not self.stages:
            raise ValueError("select at least one processing stage")
        return self


class Passage(Context):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "tenant_id": "acme",
                    "document_id": "report",
                    "document_version_id": "v1",
                    "page_number": 1,
                    "chunk_id": "c1",
                    "text": "Ada approved Project Mercury.",
                }
            ]
        }
    )
    text: Text
    page_number: int = Field(ge=1)
    chunk_id: ID


class Batch(Contract):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "items": [
                        {
                            "tenant_id": "acme",
                            "document_id": "report",
                            "document_version_id": "v1",
                            "page_number": 1,
                            "chunk_id": "c1",
                            "text": "Ada approved Project Mercury.",
                        }
                    ]
                }
            ]
        }
    )
    items: list[Passage] = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def same_version(self):
        if len({p.prefix for p in self.items}) != 1:
            raise ValueError("batch items must share tenant and document version")
        return self


class Query(Contract):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"tenant_id": "acme", "text": "Who approved Mercury?"}]}
    )
    tenant_id: ID
    text: Text


class Element(Contract):
    paragraph_id: int | None = None
    kind: str
    bbox: Box
    text: str = ""
    font: str | None = None
    size: float | None = None


class Table(Contract):
    table_id: str
    page_number: int
    bbox: Box
    rows: list[list[str]]
    columns: int
    text: str
    method: str = "pymupdf-lines"


class Page(Contract):
    page_id: str
    page_number: int
    width: float
    height: float
    classification: Literal["native", "scanned", "mixed", "image"]
    extraction_method: str
    confidence: float | None = None
    text: str
    elements: list[Element]
    tables: list[Table]
    image_coverage: float
    quality: dict[str, float]
    warnings: list[str]
    processed_at: str


class Chunk(Context):
    chunk_id: str
    page_number: int
    start: int
    end: int
    section_title: str | None
    parent_section: str | None
    strategy: Strategy
    text: str
    token_count: int
    character_count: int
    source_ref: str
    table_id: str | None = None


class Artifact(Contract):
    key: str
    sha256: str
    size: int
    media_type: str
    created_at: str
    metadata: dict = {}


class Issue(Contract):
    code: str
    message: str
    stage: str
    retryable: bool


class PageResult(Contract):
    page_number: int
    classification: str | None = None
    stages: dict[str, str] = {}
    artifacts: dict[str, Artifact] = {}
    errors: list[Issue] = []
    warnings: list[str] = []


class Manifest(Context):
    source_metadata: dict = {}
    processing_run_id: str
    pipeline_version: str
    source_sha256: str
    configuration: dict
    model_versions: dict
    started_at: str
    completed_at: str
    total_pages: int
    classification: str
    successful_pages: list[int]
    failed_pages: list[int]
    pages: list[PageResult]
    status: Literal["success", "partial", "failed"]
    manifest_key: str
